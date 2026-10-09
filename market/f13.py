"""8. 참고지수 대비 비중 차이·보유 중첩에 쓰는 13F(미국 기관 운용사의 분기 보유 보고).

13F 비중은 '공개 보유분 안의 비중'이다(13F에 실리는 미국 상장 증권만, 옵션 줄 제외). 운용사의 전체 자산 대비가 아니다.
13F에는 티커가 없어서 SEC 등록 회사명과 13F 발행사명을 정리해 같은지로 찾는다(찾은 이름을 함께 보여 준다).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

DROP = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LLC", "LP", "NV", "SA", "AG", "SE",
        "THE", "NEW", "DEL", "DE", "COM", "CL", "CLASS", "A", "B", "C", "SHS", "ORD"}


def norm(name: str) -> str:
    s = name.upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t not in DROP)


@dataclass
class Row:
    issuer: str
    title: str
    cusip: str
    value: float
    put_call: str


@dataclass
class Hit:
    manager: str
    period: str  # 보고 기준일
    weight: float  # 공개 보유분(옵션 제외) 안 비중
    matched: list  # 찾은 (발행사명, 증권 종류)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_infotable(xml_text: str) -> list[Row]:
    root = ET.fromstring(xml_text)
    out = []
    for el in root.iter():
        if _local(el.tag) != "infoTable":
            continue
        f = {_local(c.tag): (c.text or "").strip() for c in el}
        try:
            value = float(f.get("value", "") or 0)
        except ValueError:
            value = 0.0
        out.append(Row(f.get("nameOfIssuer", ""), f.get("titleOfClass", ""), f.get("cusip", ""), value, f.get("putCall", "")))
    return out


def weight_of(rows: list[Row], company_name: str) -> tuple[float, list]:
    """company_name(SEC 등록명)과 같은 발행사의 비중. 못 찾으면 (0, [])."""
    stocks = [r for r in rows if not r.put_call]
    total = sum(r.value for r in stocks)
    key = norm(company_name)
    hits = [r for r in stocks if key and norm(r.issuer) == key]
    if not hits or total <= 0:
        return 0.0, []
    return sum(r.value for r in hits) / total, [(r.issuer, r.title) for r in hits]


# ---------------------------------------------------------------- 네트워크


def latest_13f(cik: int, user_agent: str, session=None) -> tuple[str, list[Row]]:
    """운용사의 가장 최근 13F-HR → (보고 기준일, 보유 줄)."""
    from . import sec
    from .insider import SUBMISSIONS

    subs = sec._get_json(SUBMISSIONS.format(cik=cik), user_agent, session)
    r = subs.get("filings", {}).get("recent", {})
    for form, acc, period in zip(r.get("form", []), r.get("accessionNumber", []), r.get("reportDate", [])):
        if form != "13F-HR":
            continue
        folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
        index = sec._get_json(folder + "index.json", user_agent, session)
        names = [it["name"] for it in index.get("directory", {}).get("item", []) if it["name"].lower().endswith(".xml")]
        table = next((n for n in names if n.lower() != "primary_doc.xml"), None)
        if table is None:
            return period, []
        return period, parse_infotable(sec.get_text(folder + table, user_agent, session))
    return "", []
