"""미국 재무: SEC EDGAR XBRL companyfacts (무료, 키 없음, User-Agent 필요).

us-gaap 기준으로 보고하는 회사만 다룬다(10-K·10-Q). 20-F를 내는 외국 회사는 결측이 된다.
"최근 1년"은 최근 4개 분기 합(TTM)이다: 연간 값이 있으면 그 값, 없으면 직전 연간 + 올해 누적 − 작년 같은 기간 누적.
"""

from __future__ import annotations

import datetime as dt

from judge.common import add_months

from .models import Fundamentals

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT"}

# 같은 개념의 태그를 우선순위대로. 앞의 태그로 계산이 안 되면 다음 태그를 쓴다.
TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
    ],
    "op_income": ["OperatingIncomeLoss"],
    "net_income": ["ProfitLoss", "NetIncomeLoss"],
    "equity": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
    "liabilities": ["Liabilities"],
    "liab_and_equity": ["LiabilitiesAndStockholdersEquity"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "short_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
}
DEBT_TAGS = (  # (태그, 표시 이름). LongTermDebt(유동 포함 합계)가 있으면 유동·비유동 따로 쓰지 않는다.
    ("ShortTermBorrowings", "단기차입금"),
    ("CommercialPaper", "기업어음"),
)


def entries(facts: dict, tag: str, unit: str = "USD") -> list[dict]:
    """한 태그의 값들. 같은 기간을 여러 보고서가 다시 실으면 가장 나중에 낸 값만 남긴다."""
    try:
        items = facts["facts"]["us-gaap"][tag]["units"][unit]
    except KeyError:
        return []
    out = {}
    for it in items:
        if it.get("form") not in FORMS or "end" not in it or "val" not in it:
            continue
        start = dt.date.fromisoformat(it["start"]) if it.get("start") else None
        end = dt.date.fromisoformat(it["end"])
        row = {"start": start, "end": end, "val": float(it["val"]), "filed": it.get("filed", ""), "form": it["form"]}
        key = (start, end)
        if key not in out or row["filed"] > out[key]["filed"]:
            out[key] = row
    return list(out.values())


def _days(e):
    return (e["end"] - e["start"]).days


def _closest(rows, end, tol):
    rows = [e for e in rows if abs((e["end"] - end).days) <= tol]
    return min(rows, key=lambda e: abs((e["end"] - end).days)) if rows else None


def ttm_at(rows: list[dict], end: dt.date, tol: int = 12) -> float | None:
    """end에 끝나는 최근 1년 합. 계산할 수 없으면 None."""
    flows = [e for e in rows if e["start"] is not None]
    at_end = [e for e in flows if abs((e["end"] - end).days) <= tol]
    annual = [e for e in at_end if 350 <= _days(e) <= 380]
    if annual:
        return min(annual, key=lambda e: abs((e["end"] - end).days))["val"]
    ytd = [e for e in at_end if 80 <= _days(e) < 350]
    if not ytd:
        return None
    cur = max(ytd, key=_days)  # 누적(YTD)이 가장 긴 것
    prev_fy = _closest([e for e in flows if 350 <= _days(e) <= 380], cur["start"] - dt.timedelta(days=1), tol)
    same_len = [e for e in flows if abs(_days(e) - _days(cur)) <= 15]
    prev_ytd = _closest(same_len, add_months(cur["end"], -12), 15)
    if prev_fy is None or prev_ytd is None:
        return None
    return prev_fy["val"] + cur["val"] - prev_ytd["val"]


def instant_at(rows: list[dict], end: dt.date, tol: int = 12) -> float | None:
    hit = _closest([e for e in rows if e["start"] is None], end, tol)
    return hit["val"] if hit else None


def _first(facts, tags, fn, end):
    for tag in tags:
        v = fn(entries(facts, tag), end)
        if v is not None:
            return v, tag
    return None, None


def parse_companyfacts(facts: dict) -> Fundamentals:
    """companyfacts JSON → Fundamentals. 순수 함수(네트워크 없음)."""
    f = Fundamentals(source="SEC EDGAR")
    eq_rows = [e for tag in TAGS["equity"] for e in entries(facts, tag) if e["start"] is None]
    if not eq_rows:
        f.notes.append("SEC 자료에 us-gaap 자본 항목이 없음(외국 회사 20-F 등)")
        return f
    # 재무상태표 기준일 후보: 최근 것부터. 순이익 1년 합이 계산되는 첫 날짜를 쓴다.
    for end in sorted({e["end"] for e in eq_rows}, reverse=True)[:4]:
        ni, _ = _first(facts, TAGS["net_income"], ttm_at, end)
        if ni is not None:
            break
    else:
        end = max(e["end"] for e in eq_rows)
        f.notes.append("최근 1년 순이익을 계산할 수 없음")
    f.as_of = end
    f.net_income, _ = _first(facts, TAGS["net_income"], ttm_at, end)
    f.op_income, _ = _first(facts, TAGS["op_income"], ttm_at, end)
    f.revenue, _ = _first(facts, TAGS["revenue"], ttm_at, end)
    f.revenue_3y_ago, _ = _first(facts, TAGS["revenue"], lambda rows, e: ttm_at(rows, e, 15), add_months(end, -36))
    f.equity, eq_tag = _first(facts, TAGS["equity"], instant_at, end)
    f.liabilities, _ = _first(facts, TAGS["liabilities"], instant_at, end)
    if f.liabilities is None:
        total, _ = _first(facts, TAGS["liab_and_equity"], instant_at, end)
        if total is not None and f.equity is not None:
            f.liabilities = total - f.equity
            f.notes.append("부채총계 = 부채와자본총계 − 자본총계")

    parts = {}
    ltd = instant_at(entries(facts, "LongTermDebt"), end)
    if ltd is not None:
        parts["장기부채(유동 포함)"] = ltd
    else:
        for tag, label in (("LongTermDebtCurrent", "유동성장기부채"), ("LongTermDebtNoncurrent", "장기부채")):
            v = instant_at(entries(facts, tag), end)
            if v is not None:
                parts[label] = v
    for tag, label in DEBT_TAGS:
        v = instant_at(entries(facts, tag), end)
        if v is not None:
            parts[label] = v
    if not parts:
        v = instant_at(entries(facts, "DebtCurrent"), end)
        if v is not None:
            parts["유동 차입금"] = v
    f.debt_parts = parts
    f.debt = sum(parts.values())
    if not parts:
        f.notes.append("이자부부채 항목이 없어 0으로 봄")

    cash, _ = _first(facts, TAGS["cash"], instant_at, end)
    sti, sti_tag = _first(facts, TAGS["short_investments"], instant_at, end)
    if cash is not None:
        f.cash_parts["현금및현금성자산"] = cash
    if sti is not None:
        f.cash_parts["단기투자자산"] = sti
    f.cash = sum(f.cash_parts.values()) if cash is not None else None
    f.source = f"SEC EDGAR {end.isoformat()} 기준"
    for key in ("net_income", "op_income", "revenue", "revenue_3y_ago", "equity", "liabilities", "cash"):
        if getattr(f, key) is None:
            f.notes.append(f"{key} 없음")
    return f


# ---------------------------------------------------------------- 네트워크


def _get_json(url: str, user_agent: str, session=None):
    import requests

    http = session or requests
    r = http.get(url, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}, timeout=30)
    r.raise_for_status()
    return r.json()


def ticker_map(user_agent: str, session=None) -> dict[str, int]:
    """티커 → CIK."""
    data = _get_json(TICKERS_URL, user_agent, session)
    return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}


def fetch_fundamentals(ticker: str, user_agent: str, cik_map: dict, session=None) -> Fundamentals:
    cik = cik_map.get(ticker.upper().replace(".", "-"))
    if cik is None:
        return Fundamentals(source="SEC EDGAR", notes=[f"SEC 목록에 {ticker} 없음"])
    return parse_companyfacts(_get_json(FACTS_URL.format(cik=cik), user_agent, session))
