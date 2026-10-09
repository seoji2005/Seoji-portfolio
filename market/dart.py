"""한국 재무: 금융감독원 OpenDART (무료, 인증키 필요).

단일회사 전체 재무제표(fnlttSinglAcntAll)의 연결(CFS) 값을 쓰고, 연결이 없으면 별도(OFS)를 쓴다.
"최근 1년"은 최근 4개 분기 합(TTM): 사업보고서면 그 연간 값, 분기·반기보고서면
직전 사업연도 값 + 올해 누적 − 작년 같은 기간 누적. 12월 결산을 가정한다.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

from .models import Fundamentals

BASE = "https://opendart.fss.or.kr/api"
ANNUAL, Q1, HALF, Q3 = "11011", "11013", "11012", "11014"
PERIOD_END = {Q1: (3, 31), HALF: (6, 30), Q3: (9, 30), ANNUAL: (12, 31)}
REPORT_NAME = {Q1: "1분기보고서", HALF: "반기보고서", Q3: "3분기보고서", ANNUAL: "사업보고서"}

# 항목: (account_id 후보, 계정명 후보(공백 제거), 재무제표 구분)
IS = ("IS", "CIS")
ITEMS = {
    "revenue": (("ifrs-full_Revenue", "ifrs_Revenue"), ("매출액", "수익(매출액)", "영업수익", "매출", "수익", "매출액(영업수익)"), IS),
    "op_income": (("dart_OperatingIncomeLoss",), ("영업이익", "영업이익(손실)", "영업손익", "영업손실"), IS),
    "net_income": (
        ("ifrs-full_ProfitLoss", "ifrs_ProfitLoss"),
        ("당기순이익", "당기순이익(손실)", "분기순이익", "분기순이익(손실)", "반기순이익", "반기순이익(손실)", "연결당기순이익", "당기순손익"),
        IS,
    ),
    "equity": (("ifrs-full_Equity", "ifrs_Equity"), ("자본총계",), ("BS",)),
    "liabilities": (("ifrs-full_Liabilities", "ifrs_Liabilities"), ("부채총계",), ("BS",)),
    "cash": (("ifrs-full_CashAndCashEquivalents", "ifrs_CashAndCashEquivalents"), ("현금및현금성자산",), ("BS",)),
}
DEBT_NAME = re.compile(r"^(단기차입금|장기차입금|유동성장기차입금|유동성장기부채|사채|유동성사채|장기사채|단기사채|전환사채|교환사채|신주인수권부사채)$")
SHORT_INVEST_NAME = re.compile(r"^단기금융상품$")


def num(s) -> float | None:
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _name(row) -> str:
    return re.sub(r"\s", "", row.get("account_nm", ""))


def find(rows: list[dict], item: str) -> dict | None:
    """항목에 해당하는 첫 줄. account_id로 먼저 찾고, 없으면 계정명으로 찾는다."""
    ids, names, sj = ITEMS[item]
    for kind in sj:
        cand = [r for r in rows if r.get("sj_div") == kind]
        for r in cand:
            if r.get("account_id") in ids:
                return r
        for r in cand:
            if _name(r) in names:
                return r
    return None


def amount(rows, item, field="thstrm_amount") -> float | None:
    if not rows:
        return None
    r = find(rows, item)
    return num(r.get(field)) if r else None


def ttm(item: str, code: str, latest: list, annual_prev: list | None) -> float | None:
    """최근 보고서 기준 1년 합."""
    if code == ANNUAL:
        return amount(latest, item)
    cur = amount(latest, item, "thstrm_add_amount")
    prev = amount(latest, item, "frmtrm_add_amount")
    if code == Q1:  # 1분기는 3개월이 곧 누적
        cur = cur if cur is not None else amount(latest, item)
        prev = prev if prev is not None else amount(latest, item, "frmtrm_q_amount")
    fy = amount(annual_prev, item)
    if None in (cur, prev, fy):
        return None
    return fy + cur - prev


def revenue_3y(code: str, old: list | None, old_annual: list | None) -> float | None:
    """3년 전 같은 1년 매출. old: 3년 전 같은 보고서, old_annual: 3년 전 사업보고서."""
    if code == ANNUAL:
        return amount(old_annual, "revenue")
    cur = amount(old, "revenue", "thstrm_add_amount")
    prev = amount(old, "revenue", "frmtrm_add_amount")
    if code == Q1:
        cur = cur if cur is not None else amount(old, "revenue")
        prev = prev if prev is not None else amount(old, "revenue", "frmtrm_q_amount")
    fy = amount(old_annual, "revenue", "frmtrm_amount")  # 3년 전 사업보고서의 전기 = 4년 전 연간
    if None in (cur, prev, fy):
        return None
    return fy + cur - prev


def parse(year: int, code: str, latest: list, annual_prev=None, old=None, old_annual=None) -> Fundamentals:
    """보고서 묶음 → Fundamentals. 순수 함수(네트워크 없음)."""
    m, d = PERIOD_END[code]
    f = Fundamentals(as_of=dt.date(year, m, d), source=f"OpenDART {year}년 {REPORT_NAME[code]}")
    f.net_income = ttm("net_income", code, latest, annual_prev)
    f.op_income = ttm("op_income", code, latest, annual_prev)
    f.revenue = ttm("revenue", code, latest, annual_prev)
    f.revenue_3y_ago = revenue_3y(code, old, old_annual)
    f.equity = amount(latest, "equity")
    f.liabilities = amount(latest, "liabilities")
    bs = [r for r in latest if r.get("sj_div") == "BS"]
    for r in bs:
        name, v = _name(r), num(r.get("thstrm_amount"))
        if v is None:
            continue
        if DEBT_NAME.match(name) and name not in f.debt_parts:
            f.debt_parts[name] = v
        elif SHORT_INVEST_NAME.match(name) and name not in f.cash_parts:
            f.cash_parts[name] = v
    f.debt = sum(f.debt_parts.values())
    if not f.debt_parts:
        f.notes.append("차입금·사채 항목이 없어 0으로 봄")
    cash = amount(latest, "cash")
    if cash is not None:
        f.cash_parts = {"현금및현금성자산": cash, **f.cash_parts}
        f.cash = sum(f.cash_parts.values())
    for key in ("net_income", "op_income", "revenue", "revenue_3y_ago", "equity", "liabilities", "cash"):
        if getattr(f, key) is None:
            f.notes.append(f"{key} 없음")
    return f


# ---------------------------------------------------------------- 네트워크


class DartError(RuntimeError):
    pass


def _get(http, path: str, params: dict, timeout: int):
    """요청 주소에 인증키가 들어가므로, 오류 문구에 주소를 남기지 않는다."""
    try:
        r = http.get(f"{BASE}/{path}", params=params, timeout=timeout)
        r.raise_for_status()
    except Exception as ex:  # noqa: BLE001
        code = getattr(getattr(ex, "response", None), "status_code", "")
        raise DartError(f"OpenDART {path} 접속 오류 {type(ex).__name__} {code}".strip()) from None
    return r


def corp_codes(key: str, session=None) -> dict[str, str]:
    """종목코드(6자리) → 고유번호(corp_code)."""
    import requests

    http = session or requests
    r = _get(http, "corpCode.xml", {"crtfc_key": key}, 60)
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        raise DartError(r.text[:200]) from None
    root = ET.fromstring(z.read(z.namelist()[0]))
    out = {}
    for el in root.iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if stock:
            out[stock] = el.findtext("corp_code").strip()
    return out


def statements(key: str, corp: str, year: int, code: str, session=None) -> list | None:
    """보고서 하나의 전체 재무제표. 없으면 None. 연결 → 별도 순서로 찾는다."""
    import requests

    http = session or requests
    for fs in ("CFS", "OFS"):
        params = {"crtfc_key": key, "corp_code": corp, "bsns_year": str(year), "reprt_code": code, "fs_div": fs}
        r = _get(http, "fnlttSinglAcntAll.json", params, 30)
        data = r.json()
        status = data.get("status")
        if status == "000" and data.get("list"):
            return data["list"]
        if status not in ("000", "013"):  # 013 = 조회된 데이터 없음
            raise DartError(f"{status} {data.get('message')}")
    return None


def candidates(today: dt.date):
    """최근 것부터 찾아볼 (사업연도, 보고서) 순서."""
    y = today.year
    return [(y, Q3), (y, HALF), (y, Q1), (y - 1, ANNUAL), (y - 1, Q3), (y - 1, HALF), (y - 1, Q1), (y - 2, ANNUAL)]


def fetch_fundamentals(stock_code: str, key: str, corp_map: dict, today: dt.date | None = None, session=None) -> Fundamentals:
    corp = corp_map.get(stock_code.zfill(6))
    if corp is None:
        return Fundamentals(source="OpenDART", notes=[f"OpenDART 목록에 {stock_code} 없음"])
    today = today or dt.date.today()
    for year, code in candidates(today):
        if dt.date(year, *PERIOD_END[code]) > today:
            continue
        latest = statements(key, corp, year, code, session)
        if latest:
            break
    else:
        return Fundamentals(source="OpenDART", notes=["최근 2년 보고서를 찾지 못함"])
    if code == ANNUAL:
        old_annual = statements(key, corp, year - 3, ANNUAL, session)
        return parse(year, code, latest, old_annual=old_annual)
    annual_prev = statements(key, corp, year - 1, ANNUAL, session)
    old = statements(key, corp, year - 3, code, session)
    old_annual = statements(key, corp, year - 3, ANNUAL, session)
    return parse(year, code, latest, annual_prev, old, old_annual)


# ---------------------------------------------------------------- 권리락(사전 1번 12-1 수익률)
# 시세(Yahoo)가 증자 권리락을 보정했는지 확인할 수 없으므로, 권리락이 12-1 구간에 걸리면 그 종목의 12-1은 판단 불가(결측).
# 권리락이 생기는 증자: 무상증자, 유무상증자, 주주배정 방식 유상증자(제3자배정·일반공모는 권리락 없음).
RIGHTS_APIS = (("piicDecsn", "유상증자"), ("fricDecsn", "무상증자"), ("pifricDecsn", "유무상증자"))
DATE_TEXT = re.compile(r"(\d{4})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})")


@dataclass
class RightsEvent:
    kind: str  # 유상증자 / 무상증자 / 유무상증자
    filed: dt.date  # 공시 접수일
    record_date: dt.date | None  # 신주배정기준일(공시 항목에 있을 때만: 무상증자)
    method: str  # 증자방식(유상증자)
    rcept_no: str

    @property
    def text(self) -> str:
        when = f"신주배정기준일 {self.record_date}" if self.record_date else f"{self.filed} 결정 공시(기준일 항목 없음)"
        return f"{self.kind}{f'({self.method})' if self.method else ''} {when}, 접수번호 {self.rcept_no}"


def _date(s) -> dt.date | None:
    m = DATE_TEXT.search(s or "")
    try:
        return dt.date(*map(int, m.groups())) if m else None
    except ValueError:
        return None


def parse_rights(api: str, kind: str, rows: list[dict]) -> list[RightsEvent]:
    """증자 결정 공시 → 권리락이 생기는 것만."""
    out = []
    for row in rows:
        method = next((v.strip() for k, v in row.items() if k.endswith("ic_mthn") and v and v.strip() not in ("-",)), "")
        if kind == "유상증자" and method and "주주배정" not in method:
            continue  # 제3자배정·일반공모는 권리락 없음. 방식을 모르면 남긴다(확인 불가)
        record = next((_date(v) for k, v in row.items() if k.endswith("nstk_asstd") and _date(v)), None)
        no = row.get("rcept_no", "")
        out.append(RightsEvent(kind, dt.date(int(no[:4]), int(no[4:6]), int(no[6:8])), record, method, no))
    return out


def rights_events(stock_code: str, key: str, corp_map: dict, start: dt.date, end: dt.date, session=None) -> list[RightsEvent]:
    """start~end에 접수된 증자 결정 중 권리락이 생기는 것. 조회 실패는 예외로 알린다."""
    import requests

    corp = corp_map.get(stock_code.zfill(6))
    if corp is None:
        raise DartError(f"OpenDART 목록에 {stock_code} 없음")
    http = session or requests
    out = []
    for api, kind in RIGHTS_APIS:
        params = {"crtfc_key": key, "corp_code": corp, "bgn_de": f"{start:%Y%m%d}", "end_de": f"{end:%Y%m%d}"}
        r = _get(http, f"{api}.json", params, 30)
        data = r.json()
        if data.get("status") == "013":  # 조회된 데이터 없음
            continue
        if data.get("status") != "000":
            raise DartError(f"{api} {data.get('status')} {data.get('message')}")
        out += parse_rights(api, kind, data.get("list") or [])
    return sorted(out, key=lambda e: e.filed)
