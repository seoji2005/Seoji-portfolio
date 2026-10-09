"""8. 임원 장내 매수(미국): SEC Form 4.

Form 4의 매수 코드 P는 장내 매수와 사적 매수를 모두 포함한다. 그래서
- 임원(이사·집행임원)의 비파생 주식 P 거래 가운데
- 그 거래에 붙은 각주(또는 서류의 비고)가 '장내(open market)' 매수라고 밝힌 것만 '확인'으로 보고,
- 10b5-1 계획 표시(서류 체크 또는 각주)가 있으면 제외하고,
- 나머지 P 거래는 '미확인'으로 센다. 옵션 행사(M·X 등)는 P가 아니므로 처음부터 빠진다.
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

OPEN_MARKET = re.compile(r"open[\s-]+market", re.I)
NOT_OPEN_MARKET = re.compile(r"\bnot\b[^.]{0,40}open[\s-]+market|privately[\s-]+negotiated|private\s+(transaction|purchase|placement|sale)", re.I)
PLAN_10B5_1 = re.compile(r"10b5-?1", re.I)


@dataclass
class Purchase:
    date: str
    owner: str
    role: str
    shares: float | None
    price: float | None
    status: str  # 확인 / 미확인 / 제외(10b5-1)
    evidence: str = ""  # 판단에 쓴 각주 문구
    url: str = ""


@dataclass
class InsiderSummary:
    confirmed: list = field(default_factory=list)
    unconfirmed: list = field(default_factory=list)
    excluded: list = field(default_factory=list)
    since: str = ""
    note: str = ""


def _text(el, path):
    x = el.find(path)
    return (x.text or "").strip() if x is not None and x.text else ""


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _truthy(s):
    return s.strip().lower() in ("1", "true", "y", "yes")


def parse_form4(xml_text: str, url: str = "") -> list[Purchase]:
    """Form 4 XML → 임원의 P(매수) 거래 목록과 판정."""
    root = ET.fromstring(xml_text)
    notes = {fn.get("id"): " ".join((fn.text or "").split()) for fn in root.iter("footnote")}
    remarks = " ".join(_text(root, "remarks").split())
    plan_box = _truthy(_text(root, "aff10b5One"))
    owners, roles = [], []
    for ro in root.iter("reportingOwner"):
        rel = ro.find("reportingOwnerRelationship")
        if rel is None:
            continue
        is_dir, is_off = _truthy(_text(rel, "isDirector")), _truthy(_text(rel, "isOfficer"))
        if is_dir or is_off:
            owners.append(_text(ro, "reportingOwnerId/rptOwnerName"))
            roles.append(_text(rel, "officerTitle") or ("이사" if is_dir else "임원"))
    if not owners:
        return []  # 임원이 아닌 보고자(10% 주주 등)는 보지 않음
    out = []
    for tx in root.iter("nonDerivativeTransaction"):
        if _text(tx, "transactionCoding/transactionCode") != "P":
            continue
        if _text(tx, "transactionAmounts/transactionAcquiredDisposedCode/value") not in ("", "A"):
            continue
        refs = [notes.get(f.get("id"), "") for f in tx.iter("footnoteId")]
        texts = [t for t in refs + [remarks] if t]
        joined = " ".join(texts)
        p = Purchase(
            date=_text(tx, "transactionDate/value"),
            owner=", ".join(owners),
            role=", ".join(r for r in roles if r),
            shares=_num(_text(tx, "transactionAmounts/transactionShares/value")),
            price=_num(_text(tx, "transactionAmounts/transactionPricePerShare/value")),
            status="미확인",
            url=url,
        )
        if plan_box or PLAN_10B5_1.search(joined):
            p.status, p.evidence = "제외(10b5-1)", "10b5-1 계획 표시" if plan_box else next(t for t in texts if PLAN_10B5_1.search(t))
        elif any(OPEN_MARKET.search(t) and not NOT_OPEN_MARKET.search(t) for t in texts) and not NOT_OPEN_MARKET.search(joined):
            p.status, p.evidence = "확인", next(t for t in texts if OPEN_MARKET.search(t))
        out.append(p)
    return out


def summarize(purchases: list[Purchase], since: dt.date) -> InsiderSummary:
    s = InsiderSummary(since=since.isoformat())
    for p in purchases:
        {"확인": s.confirmed, "미확인": s.unconfirmed}.get(p.status, s.excluded).append(p)
    return s


# ---------------------------------------------------------------- 네트워크

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"


def recent_form4(submissions: dict, since: dt.date, limit: int = 30) -> list[tuple[str, str]]:
    """제출 목록 → (원문 XML 경로, 제출일). 최근 것부터 limit개."""
    r = submissions.get("filings", {}).get("recent", {})
    out = []
    for form, acc, filed, doc in zip(r.get("form", []), r.get("accessionNumber", []), r.get("filingDate", []), r.get("primaryDocument", [])):
        if form not in ("4", "4/A") or dt.date.fromisoformat(filed) < since:
            continue
        out.append((acc.replace("-", "") + "/" + doc.split("/")[-1], filed))  # xslF345X05/ 아래는 보기용 → 원문은 같은 이름
        if len(out) >= limit:
            break
    return out


def fetch(cik: int, user_agent: str, today: dt.date | None = None, session=None) -> InsiderSummary:
    from . import sec

    today = today or dt.date.today()
    since = today - dt.timedelta(days=365)
    subs = sec._get_json(SUBMISSIONS.format(cik=cik), user_agent, session)
    purchases = []
    for path, _ in recent_form4(subs, since):
        acc, doc = path.split("/")
        url = ARCHIVE.format(cik=cik, acc=acc, doc=doc)
        try:
            purchases += parse_form4(sec.get_text(url, user_agent, session), url)
        except ET.ParseError:
            continue
    return summarize(purchases, since)
