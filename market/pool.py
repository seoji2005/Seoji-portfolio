"""관심 종목 목록 → 명세 1·2의 점수 계산 입력(judge.stocks.Stock)."""

from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd

from judge.common import add_months
from judge.stocks import Stock, StockResult, evaluate_pool

from . import yahoo
from .models import Fundamentals, Profile, Quote

RIGHTS_LOOKBACK_MONTHS = 6  # 기준일 항목이 없는 유상증자 결정: 공시 뒤 이 기간 안 어디서든 권리락이 날 수 있다고 본다
UNIT = {"한국": 1e8, "미국": 1e6}  # 시트와 같은 단위: 억 원, 백만 달러
UNIT_NAME = {"한국": "억 원", "미국": "백만 달러"}
CURRENCY = {"한국": "KRW", "미국": "USD"}
FIN_INDUSTRY = re.compile(r"bank|insurance|capital markets|reit", re.I)  # 은행·보험·증권·리츠


@dataclass
class Entry:
    """관심 종목 또는 보유 종목 한 줄."""

    country: str
    code: str
    name: str = ""
    market: str = ""  # 한국: KOSPI / KOSDAQ (비우면 코스피로 먼저 찾음)
    fin: str = ""  # 금융·리츠: Y(맞음) / N(아님) / 비움(업종으로 자동 판단)


@dataclass
class StockData:
    entry: Entry
    symbol: str
    history: pd.DataFrame
    quote: Quote
    profile: Profile
    fundamentals: Fundamentals
    fin: bool
    fin_reason: str
    price_asof: dt.date | None
    stock: Stock = None
    result: StockResult | None = None
    held: bool = False
    notes: list = field(default_factory=list)
    mom_block: str = ""  # 12-1 판단 불가 이유(권리락 보정 미확인 등). 있으면 12-1은 결측

    @property
    def name(self) -> str:
        return self.entry.name or self.profile.name or self.entry.code

    @property
    def data_problem(self) -> str:
        """재무를 하나도 받지 못했으면 그 이유(설정 누락·접속 오류). 받았으면 빈 글자."""
        f = self.fundamentals
        if any(v is not None for v in (f.equity, f.op_income, f.revenue, f.net_income)):
            return ""
        return f.notes[0] if f.notes else "재무 자료 없음"


def momentum_points(close: pd.Series):
    """((12개월 전 날짜, 종가), (1개월 전 날짜, 종가), 기준일). 없으면 (None, None). 기준일은 마지막 거래일.

    넘기는 값은 분할·병합을 반영하고 현금배당은 반영하지 않은 종가(close, 사전 1번). 배당까지 반영한 adj_close가 아님.
    """
    close = close.dropna()
    if close.empty:
        return (None, None), (None, None), None
    asof = close.index[-1].date()

    def at(months):
        target = pd.Timestamp(add_months(asof, months))
        before = close[close.index <= target]
        if before.empty or (target - before.index[-1]).days > 10:
            return None, None
        return before.index[-1].date(), float(before.iloc[-1])

    return at(-12), at(-1), asof


def momentum_prices(close: pd.Series):
    """(12개월 전, 1개월 전 종가, 기준일)."""
    (_, p12), (_, p1), asof = momentum_points(close)
    return p12, p1, asof


def rights_window(d12: dt.date, d1: dt.date) -> tuple[dt.date, dt.date]:
    """12-1 구간(d12, d1]에 권리락이 걸칠 수 있는 증자 결정 공시를 찾을 기간."""
    return add_months(d12, -RIGHTS_LOOKBACK_MONTHS), d1 + dt.timedelta(days=7)


def rights_block(events, d12: dt.date, d1: dt.date) -> str:
    """권리락이 12-1 구간(d12, d1]에 걸치면 판단 불가 이유. 시세가 보정했는지 확인할 수 없으므로 보수적으로 본다.

    - 신주배정기준일이 있으면: 권리락일은 기준일 전 영업일 → d12 < 기준일 ≤ d1 + 7일이면 걸침(휴장 여유 포함).
    - 기준일 항목이 없으면(유상증자): 결정 공시 뒤 RIGHTS_LOOKBACK_MONTHS 안의 권리락으로 보고 구간과 겹치면 걸침.
    """
    hits = []
    for e in events:
        if e.record_date:
            hit = d12 < e.record_date <= d1 + dt.timedelta(days=7)
        else:
            hit = e.filed <= d1 and add_months(e.filed, RIGHTS_LOOKBACK_MONTHS) > d12
        if hit:
            hits.append(e.text)
    return ("12-1 판단 불가: 권리락 보정 미확인 — " + "; ".join(hits)) if hits else ""


def financial_flag(entry: Entry, profile: Profile) -> tuple[bool, str]:
    if entry.fin.upper() == "Y":
        return True, "직접 표시(Y)"
    if entry.fin.upper() == "N":
        return False, "직접 표시(N)"
    if profile.industry and FIN_INDUSTRY.search(profile.industry):
        return True, f"업종 자동 판단: {profile.industry}"
    return False, f"업종: {profile.industry or '알 수 없음'}"


def to_stock(entry: Entry, held: bool, f: Fundamentals, q: Quote, close: pd.Series, fin: bool, mom_block: str = "") -> Stock:
    unit = UNIT[entry.country]

    def u(v):
        return None if v is None else v / unit

    p12, p1, _ = momentum_prices(close)
    if mom_block:  # 12-1 판단 불가 → 결측(사전 1번: 결측 있으면 풀에서 제외)
        p12 = p1 = None
    mcap = q.market_cap if q.currency in ("", CURRENCY[entry.country]) else None
    return Stock(
        code=entry.code, name=entry.name, held=held, excluded_sector=fin,
        basis=f.as_of.isoformat() if f.as_of else "",
        net_income=u(f.net_income), equity=u(f.equity), liabilities=u(f.liabilities), op_income=u(f.op_income),
        revenue=u(f.revenue), revenue_3y_ago=u(f.revenue_3y_ago), market_cap=u(mcap),
        debt=u(f.debt), cash=u(f.cash), price_12m=p12, price_1m=p1,
    )


def collect(provider, entries: list[Entry], held_codes: set, years: int = 11, workers: int = 8, wrap=None) -> list[StockData]:
    """종목마다 주가·시세·업종·재무를 모은다(재무와 시세는 동시에 여러 개 받음).

    wrap: 일꾼 스레드에서 돌 함수를 감싸는 함수(Streamlit 실행 맥락을 붙일 때).
    """
    syms = {(e.country, e.code): yahoo.symbol(e.country, e.code, e.market) for e in entries}
    hist = provider.histories(list(syms.values()), years)
    for e in entries:  # 한국 종목이 코스피에 없으면 코스닥으로 다시
        key = (e.country, e.code)
        if e.country == "한국" and not e.market and hist.get(syms[key], pd.DataFrame()).empty:
            alt = yahoo.symbol("한국", e.code, "KOSDAQ")
            got = provider.histories([alt], years).get(alt)
            if got is not None and not got.empty:
                syms[key], hist[alt] = alt, got

    def one(e: Entry) -> StockData:
        sym = syms[(e.country, e.code)]
        notes = []
        try:
            q = provider.quote(sym)
        except Exception as ex:  # noqa: BLE001
            q, notes = Quote(), notes + [f"시세 오류: {ex}"]
        try:
            p = provider.profile(sym)
        except Exception as ex:  # noqa: BLE001
            p, notes = Profile(), notes + [f"업종 오류: {ex}"]
        try:
            f = provider.fundamentals(e.country, e.code)
        except Exception as ex:  # noqa: BLE001
            f = Fundamentals(notes=[f"재무 오류: {ex}"])
        h = hist.get(sym, pd.DataFrame(columns=["close", "adj_close"]))
        fin, why = financial_flag(e, p)
        held = (e.country, e.code) in held_codes
        close = h["close"] if "close" in h else pd.Series(dtype=float)  # 12-1 수익률: 배당 미반영 종가(사전 1번)
        (d12, _), (d1, _), asof = momentum_points(close)
        block = ""
        if e.country == "한국" and d12 and d1:
            try:
                block = rights_block(provider.rights_events(e.code, *rights_window(d12, d1)), d12, d1)
            except Exception as ex:  # noqa: BLE001 — 확인을 못 했으면 판단 불가
                block = f"12-1 판단 불가: 권리락 여부를 확인하지 못함({ex})"
        stock = to_stock(e, held, f, q, close, fin, block)
        return StockData(e, sym, h, q, p, f, fin, why, asof, stock, held=held, notes=notes, mom_block=block)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(wrap(one) if wrap else one, entries))


def score(items: list[StockData]) -> dict:
    """국가별로 점수를 매긴다. 국가 → (StockData 목록, 최고 미보유 후보 StockData 또는 None)."""
    out = {}
    for country in ("미국", "한국"):
        group = [d for d in items if d.entry.country == country]
        for d in group:  # 이름이 비어 있으면 Yahoo 이름으로
            d.stock.name = d.name
        results, best = evaluate_pool([d.stock for d in group], country)
        for d, r in zip(group, results):
            d.result = r
        best_d = next((d for d in group if best is not None and d.result is best), None)
        out[country] = (group, best_d)
    return out
