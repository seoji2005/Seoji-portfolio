"""숫자 표시."""

from __future__ import annotations


def won(v: float | None) -> str:
    """원화: 조·억·만 단위로 짧게."""
    if v is None:
        return "–"
    a, sign = abs(v), "-" if v < 0 else ""
    if a >= 1e12:
        return f"{sign}{a / 1e12:,.1f}조 원"
    if a >= 1e8:
        return f"{sign}{a / 1e8:,.1f}억 원"
    if a >= 1e4:
        return f"{sign}{a / 1e4:,.0f}만 원"
    return f"{sign}{a:,.0f}원"


def usd(v: float | None) -> str:
    if v is None:
        return "–"
    a, sign = abs(v), "-" if v < 0 else ""
    if a >= 1e12:
        return f"{sign}${a / 1e12:,.2f}T"
    if a >= 1e9:
        return f"{sign}${a / 1e9:,.1f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:,.0f}M"
    return f"{sign}${a:,.2f}"


def money(v: float | None, country: str) -> str:
    return won(v) if country == "한국" else usd(v)


def price(v: float | None, country: str) -> str:
    if v is None:
        return "–"
    return f"{v:,.0f}원" if country == "한국" else f"${v:,.2f}"


def pct(v: float | None, digits: int = 1, sign: bool = False) -> str:
    if v is None:
        return "–"
    return f"{v * 100:+.{digits}f}%" if sign else f"{v * 100:.{digits}f}%"


def score(v: float | None) -> str:
    return "–" if v is None else f"{v:.1f}"
