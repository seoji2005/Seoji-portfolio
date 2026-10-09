"""앱 전체가 함께 쓰는 것: 설정, 자료 공급자(캐시), 관심 종목 풀 점수, 내 포트폴리오."""

from __future__ import annotations

import datetime as dt
import os
import threading
from dataclasses import dataclass

import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from judge.evidence import EvidenceRow
from judge.evidence import summarize as summarize_evidence
from judge.holdings import Account, Holding, evaluate_holdings
from judge.portfolio import Position
from judge.reasons import ReasonItem, card
from market import csvin, ecos, f13, fred, insider, sec, yahoo
from market.pool import Entry, collect, score
from market.provider import LiveProvider
from market.sample import SampleProvider

from . import store

SECRETS = ("SEC_USER_AGENT", "OPENDART_API_KEY", "ECOS_API_KEY", "GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_BRANCH", "DATA_MODE")
HISTORY_YEARS = 21


def bridge_secrets() -> None:
    """Streamlit secrets → 환경변수(자료 계층은 환경변수만 본다)."""
    try:
        for k in SECRETS:
            if k in st.secrets and not os.environ.get(k):
                os.environ[k] = str(st.secrets[k])
    except Exception:  # noqa: BLE001 — secrets 파일이 없을 때
        pass


def mode() -> str:
    return "sample" if os.environ.get("DATA_MODE", "").lower() == "sample" else "live"


def dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001
        return False


@st.cache_resource
def _provider(m: str):
    return SampleProvider() if m == "sample" else LiveProvider()


# 캐시: 재무는 하루에 두 번, 주가는 15분, 시세는 5분, 업종은 일주일
@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _fundamentals(m, country, code):
    return _provider(m).fundamentals(country, code)


@st.cache_data(ttl=900, show_spinner=False)
def _histories(m, symbols: tuple, years: int):
    return _provider(m).histories(list(symbols), years)


@st.cache_data(ttl=300, show_spinner=False)
def _quote(m, sym):
    return _provider(m).quote(sym)


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def _profile(m, sym):
    return _provider(m).profile(sym)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _rights(m, code, start, end):
    return _provider(m).rights_events(code, start, end)


class Cached:
    """market.pool.collect에 넘기는 공급자. 호출을 Streamlit 캐시로 감싼다."""

    def __init__(self, m: str):
        self.m = m

    def histories(self, symbols, years=HISTORY_YEARS):
        return _histories(self.m, tuple(sorted(set(symbols))), years)

    def quote(self, sym):
        return _quote(self.m, sym)

    def profile(self, sym):
        return _profile(self.m, sym)

    def fundamentals(self, country, code):
        return _fundamentals(self.m, country, code)

    def rights_events(self, code, start, end):
        return _rights(self.m, code, start, end)

    def status(self):
        return _provider(self.m).status()


def provider() -> Cached:
    return Cached(mode())


def _with_ctx():
    ctx = get_script_run_ctx()

    def wrap(fn):
        def inner(x):
            add_script_run_ctx(threading.current_thread(), ctx)
            return fn(x)

        return inner

    return wrap


def _rows(df: pd.DataFrame):
    return [r for r in df.to_dict("records") if str(r.get("code", "")).strip()]


def entries() -> list[Entry]:
    """풀 = 관심 종목 + 보유 종목(같은 국가 안에서 순위)."""
    out, seen = [], set()
    for r in _rows(store.read("watchlist")) + _rows(store.read("portfolio")):
        key = (r["country"], str(r["code"]).strip())
        if key in seen or r["country"] not in ("미국", "한국"):
            continue
        seen.add(key)
        out.append(Entry(r["country"], key[1], str(r.get("name", "")), str(r.get("market", "")), str(r.get("fin", ""))))
    return out


def held_keys() -> set:
    return {(r["country"], str(r["code"]).strip()) for r in _rows(store.read("portfolio"))}


def pool() -> dict:
    """국가 → (StockData 목록, 최고 미보유 후보). 같은 실행 안에서는 한 번만 계산."""
    es = entries()
    key = ("pool", mode(), tuple((e.country, e.code, e.name, e.market, e.fin) for e in es), tuple(sorted(held_keys())))
    cache = st.session_state.setdefault("_pool_cache", {})
    stamp = dt.datetime.now().strftime("%Y%m%d%H") + str(dt.datetime.now().minute // 15)
    if cache.get("key") != key or cache.get("stamp") != stamp:
        items = collect(provider(), es, held_keys(), HISTORY_YEARS, wrap=_with_ctx())
        cache.update(key=key, stamp=stamp, value=score(items))
    return cache["value"]


def find(country: str, code: str):
    group, _ = pool().get(country, ([], None))
    return next((d for d in group if d.entry.code == code), None)


def usdkrw() -> float | None:
    q = provider().quote(yahoo.FX_USDKRW)
    if q.price:
        return q.price
    h = provider().histories([yahoo.FX_USDKRW]).get(yahoo.FX_USDKRW)
    return float(h["close"].iloc[-1]) if h is not None and not h.empty else None


def _num(v):
    try:
        f = float(str(v).replace(",", ""))
        return f if f == f else None
    except ValueError:
        return None


def account() -> tuple[float, float]:
    df = store.read("account")
    if df.empty:
        return 0.0, 0.0
    r = df.iloc[0]
    return _num(r["total_krw"]) or 0.0, _num(r["cash_krw"]) or 0.0


def reason_items() -> list[ReasonItem]:
    """매수 이유 카드(my/buy_reasons.csv). 비어 있으면 이전 형식(my/reasons.csv)을 읽어 보여 준다(파일은 그대로 둠)."""
    rows = _rows(store.read("cards"))
    legacy = not rows
    if legacy:
        rows = [{"code": r["code"], "no": r.get("no"), "reason": r.get("reason", ""), "indicator": r.get("evidence", ""), "fact": "",
                 "condition": r.get("break_rule", ""), "period": "", "status": {"유지": "통과", "무너짐": "무너짐"}.get(str(r.get("result", "")).strip(), ""),
                 "note": "이전 형식에서 옮김", "checked": r.get("checked", "")} for r in _rows(store.read("reasons"))]
    out = []
    for i, r in enumerate(rows):
        no = _num(r.get("no"))
        out.append(ReasonItem(str(r["code"]).strip(), int(no) if no else i + 1, *(str(r.get(k, "") or "").strip() for k in
                              ("reason", "indicator", "fact", "condition", "period", "status", "note", "checked"))))
    return out


def cards() -> dict:
    items = reason_items()
    return {code: card(code, items) for code in dict.fromkeys(i.code for i in items)}


@dataclass
class Book:
    """보유 종목 계산 결과."""

    positions: list  # judge.portfolio.Position(사전 밖 기능에서 씀)
    holdings: list  # judge.holdings.HoldingResult
    cash: float
    total_account: float
    fx: float | None


def book() -> Book:
    fx = usdkrw()
    total, cash = account()
    hs, ps = [], []
    for r in _rows(store.read("portfolio")):
        d = find(r["country"], str(r["code"]).strip())
        h = Holding(r["country"], str(r["code"]).strip(), (d.name if d else r.get("name", "")), _num(r.get("qty")), _num(r.get("avg_price")),
                    _num(r.get("cost_krw")), d.quote.price if d else None)
        hs.append(h)
    pools = {c: ([d.result for d in g], b.result if b else None) for c, (g, b) in pool().items()}
    statuses = {code: c.status for code, c in cards().items()}
    results = evaluate_holdings(Account(total, cash, fx or 0.0), hs, statuses, pools)
    for h, res in zip(hs, results):
        d = find(h.country, h.code)
        sc = d.result.score if d and d.result and d.result.scored else None
        why = "" if sc is not None else ((d.data_problem or d.result.summary) if d and d.result else "관심 종목 자료 없음")
        ps.append(Position(h.country, h.code, h.name, res.value_krw or 0.0, sc, why))
    return Book(ps, results, cash, total, fx)


# ---------------------------------------------------------------- 시장 심리(3)·거시(4)

SENT_FRED = {"sp500": "SP500", "vix": "VIXCLS", "baa": "BAA10Y"}
KR_FILES = {"vkospi": "kr_vkospi", "aa": "kr_aa", "ktb": "kr_ktb", "credit": "kr_credit"}


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _fred(series_id: str, start: dt.date):
    return fred.fetch(series_id, start)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _ecos(key: str, which: str, start: dt.date, end: dt.date):
    return ecos.fetch(key, which, start, end)


def sentiment_raw(market: str) -> tuple[dict, dict]:
    """judge.sentiment.compute에 넣을 원자료와, 지표별 출처 설명."""
    if mode() == "sample":
        from builder.example import sentiment_raw as sample

        return sample()[market], {k: "예시 자료(가상)" for k in ("sp500", "vix", "baa", "kospi", "vkospi", "aa", "ktb", "credit")}
    today = dt.date.today()
    start = today - dt.timedelta(days=int(365.25 * 6.5))
    if market == "미국":
        return {k: _fred(sid, start) for k, sid in SENT_FRED.items()}, {k: f"FRED {sid}" for k, sid in SENT_FRED.items()}
    raw, src = {}, {}
    k = provider().histories(["^KS11"]).get("^KS11")
    raw["kospi"] = [(i.date(), float(v)) for i, v in k["close"].items()] if k is not None and not k.empty else []
    src["kospi"] = "Yahoo ^KS11(코스피 시세)"
    key = os.environ.get("ECOS_API_KEY", "")
    for name, file in KR_FILES.items():
        if name in ("aa", "ktb") and key:
            try:
                raw[name], src[name] = _ecos(key, name, start, today), f"한국은행 ECOS {ecos.ITEMS[name][2]}"
                continue
            except Exception as ex:  # noqa: BLE001
                src[name] = f"ECOS 오류({ex}) → 올린 CSV 사용"
        raw[name] = csvin.from_frame(store.read(file))
        src.setdefault(name, "올린 CSV" if raw[name] else "자료 없음")
    return raw, src


def macro_raw() -> dict:
    if mode() == "sample":
        from builder.example import macro_raw as sample

        return sample()
    start = dt.date.today() - dt.timedelta(days=int(365.25 * 11.5))
    ids = {"sahm": "SAHMREALTIME", "dgs10": "DGS10", "t10y3m": "T10Y3M", "jpy": "DEXJPUS", "exports": "XTEXVA01KRM667N"}
    return {k: _fred(sid, start) for k, sid in ids.items()}


# ---------------------------------------------------------------- 참고 근거(8)


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def _sec_titles(ua: str):
    return sec.company_titles(ua)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _insider(cik: int, ua: str):
    return insider.fetch(cik, ua)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _latest_13f(cik: int, ua: str):
    return f13.latest_13f(cik, ua)


def evidence_rows(code: str) -> list[EvidenceRow]:
    out = []
    for r in _rows(store.read("evidence")):
        if str(r["code"]).strip() == code:
            out.append(EvidenceRow(code, str(r.get("kind", "")).strip(), str(r.get("holder", "")).strip(), str(r.get("detail", "")).strip(),
                                   _num(r.get("weight_pct")), str(r.get("as_of", "")).strip(), str(r.get("source", "")).strip()))
    return out


def evidence(d) -> list:
    """종목 카드의 참고 근거 절. 점수·순위·매매 규칙에 쓰지 않는다."""
    rows = evidence_rows(d.entry.code)
    if d.entry.country == "한국":
        return summarize_evidence("한국", rows, insider_note="한국 공시(DART)는 장내 매수 여부와 사전공시 거래 여부를 자동으로 가리지 않음 — 직접 확인해 넣은 것만 표시")
    ua = os.environ.get("SEC_USER_AGENT", "")
    if mode() == "sample" or not ua:
        why = "예시 자료 모드라 SEC를 조회하지 않음" if mode() == "sample" else "SEC_USER_AGENT가 없어 SEC를 조회하지 않음"
        return summarize_evidence("미국", rows, insider_note=why, f13_note=why)
    try:
        cik, title = _sec_titles(ua).get(d.entry.code.upper().replace(".", "-"), (None, ""))
        ins = _insider(cik, ua) if cik else None
        note = "" if cik else "SEC 목록에 없음"
    except Exception as ex:  # noqa: BLE001
        ins, title, note = None, "", f"SEC 조회 오류: {ex}"
    hits, f13_note = [], "고른 운용사가 없음(설정·도움말에서 추가)"
    for m in _rows(store.read("managers")):
        cik_m = _num(m.get("cik"))
        if not cik_m:
            continue
        try:
            period, table = _latest_13f(int(cik_m), ua)
        except Exception as ex:  # noqa: BLE001
            f13_note = f"13F 조회 오류: {ex}"
            continue
        w, matched = f13.weight_of(table, title)
        f13_note = "고른 운용사의 최근 13F에서 찾지 못함(이름 대조)"
        if w > 0:
            hits.append(f13.Hit(str(m.get("name", "")) or str(int(cik_m)), period, w, matched))
    return summarize_evidence("미국", rows, ins, note, hits, f13_note)


def flash(message: str) -> None:
    """다음 화면에서 한 번 보여 줄 알림(저장 후 다시 그릴 때)."""
    st.session_state["_flash"] = message


def header() -> None:
    if mode() == "sample":
        st.info("예시 자료(가상)로 보는 중입니다. 실제 시세가 아닙니다.", icon=":material/science:")
    msg = st.session_state.pop("_flash", None)
    if msg:
        st.success(msg)
