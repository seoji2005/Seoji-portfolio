"""주가·지수·환율: Yahoo Finance (yfinance, 무료·비공식). 미국은 실시간에 가깝고 한국은 지연될 수 있다."""

from __future__ import annotations

import pandas as pd

from .models import Profile, Quote

FX_USDKRW = "KRW=X"  # 1달러당 원


def symbol(country: str, code: str, market: str = "") -> str:
    """앱의 종목코드 → Yahoo 심볼. 한국은 코스피 .KS, 코스닥 .KQ."""
    code = str(code).strip()
    if country == "미국":
        return code.upper().replace(".", "-")
    suffix = ".KQ" if market.upper() in ("KOSDAQ", "KQ", "코스닥") else ".KS"
    return code.zfill(6) + suffix


def _frame(raw: pd.DataFrame, sym: str) -> pd.DataFrame:
    """yf.download 결과에서 한 종목만 꺼내 날짜 색인의 close(분할 반영)·adj_close(배당까지 반영)로."""
    try:
        close, adj = raw["Close"][sym], raw["Adj Close"][sym]
    except KeyError:
        return pd.DataFrame(columns=["close", "adj_close"])
    df = pd.DataFrame({"close": close, "adj_close": adj}).dropna(subset=["close"])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


def histories(symbols: list[str], years: int = 11) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    symbols = sorted(set(symbols))
    if not symbols:
        return {}
    raw = yf.download(symbols, period=f"{years}y", auto_adjust=False, group_by="column", progress=False, threads=True, multi_level_index=True)
    return {s: _frame(raw, s) for s in symbols}


def quote(sym: str) -> Quote:
    import yfinance as yf

    fi = yf.Ticker(sym).fast_info
    out = Quote()
    for attr, key in (("price", "last_price"), ("previous_close", "previous_close"), ("market_cap", "market_cap")):
        try:
            v = getattr(fi, key)
            setattr(out, attr, float(v) if v is not None else None)
        except Exception:  # noqa: BLE001 — Yahoo가 일부 값을 주지 않을 때
            pass
    try:
        out.currency = fi.currency or ""
    except Exception:  # noqa: BLE001
        pass
    return out


def profile(sym: str) -> Profile:
    import yfinance as yf

    try:
        info = yf.Ticker(sym).info or {}
    except Exception:  # noqa: BLE001
        info = {}
    return Profile(
        name=info.get("shortName") or info.get("longName") or "",
        sector=info.get("sector") or "",
        industry=info.get("industry") or "",
    )
