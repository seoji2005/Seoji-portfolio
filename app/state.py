"""앱 전체가 함께 쓰는 것: 설정, 자료 공급자(캐시), 관심 종목 풀 점수, 내 포트폴리오."""

from __future__ import annotations

import datetime as dt
import os
import threading
from dataclasses import dataclass

import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from judge.holdings import Account, Holding, Reason, evaluate_holdings
from judge.portfolio import Position
from market import yahoo
from market.pool import Entry, collect, score
from market.provider import LiveProvider
from market.sample import SampleProvider

from . import store

SECRETS = ("SEC_USER_AGENT", "OPENDART_API_KEY", "GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_BRANCH", "DATA_MODE")
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


def reasons() -> list[Reason]:
    out = []
    for r in _rows(store.read("reasons")):
        checked = None
        try:
            checked = dt.date.fromisoformat(str(r.get("checked", "")).strip()) if str(r.get("checked", "")).strip() else None
        except ValueError:
            pass
        out.append(Reason(str(r["code"]).strip(), _num(r.get("no")), str(r.get("reason", "")), str(r.get("core", "")).upper() == "Y",
                          str(r.get("evidence", "")).strip(), str(r.get("break_rule", "")).strip(), checked, str(r.get("result", "")).strip()))
    return out


@dataclass
class Book:
    """내 포트폴리오 계산 결과."""

    positions: list  # judge.portfolio.Position
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
        price = d.quote.price if d else None
        last = None
        try:
            last = dt.date.fromisoformat(str(r.get("last_earnings", "")).strip())
        except ValueError:
            pass
        h = Holding(r["country"], str(r["code"]).strip(), (d.name if d else r.get("name", "")), _num(r.get("qty")), _num(r.get("avg_price")),
                    _num(r.get("cost_krw")), price, last)
        hs.append(h)
    pools = {c: ([d.result for d in g], b.result if b else None) for c, (g, b) in pool().items()}
    results = evaluate_holdings(Account(total, cash, fx or 0.0), hs, reasons(), pools)
    for h, res in zip(hs, results):
        d = find(h.country, h.code)
        sc = d.result.score if d and d.result and d.result.scored else None
        why = "" if sc is not None else ((d.data_problem or d.result.summary) if d and d.result else "관심 종목 자료 없음")
        ps.append(Position(h.country, h.code, h.name, res.value_krw or 0.0, sc, why))
    return Book(ps, results, cash, total, fx)


def flash(message: str) -> None:
    """다음 화면에서 한 번 보여 줄 알림(저장 후 다시 그릴 때)."""
    st.session_state["_flash"] = message


def header() -> None:
    if mode() == "sample":
        st.info("예시 자료(가상)로 보는 중입니다. 실제 시세가 아닙니다.", icon=":material/science:")
    msg = st.session_state.pop("_flash", None)
    if msg:
        st.success(msg)
