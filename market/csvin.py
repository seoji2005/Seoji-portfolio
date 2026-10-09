"""내려받은 CSV(KRX, 금융투자협회, 한국은행) → (날짜, 값) 목록.

세로형(한 줄에 날짜 하나)과 가로형(머리글에 날짜가 늘어선 ECOS 표) 둘 다 읽는다. 어느 열·줄을 쓸지는 사람이 고른다.
"""

from __future__ import annotations

import datetime as dt
import io
import re

import pandas as pd

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S")


def read_table(data: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc, dtype=str, keep_default_na=False)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError("CSV를 읽지 못했습니다(인코딩 또는 형식).")


def to_date(s) -> dt.date | None:
    s = str(s).strip().rstrip(".")
    for f in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def to_number(s) -> float | None:
    s = re.sub(r"[,%\s]", "", str(s))
    try:
        return float(s)
    except ValueError:
        return None


def date_columns(df: pd.DataFrame) -> list[str]:
    """값의 80% 이상이 날짜인 열."""
    out = []
    for c in df.columns:
        vals = [v for v in df[c] if str(v).strip()]
        if vals and sum(to_date(v) is not None for v in vals) >= 0.8 * len(vals):
            out.append(c)
    return out


def is_wide(df: pd.DataFrame) -> bool:
    """머리글에 날짜가 10개 넘게 있으면 가로형."""
    return sum(to_date(c) is not None for c in df.columns) > 10


def long_series(df: pd.DataFrame, date_col: str, value_col: str) -> list[tuple[dt.date, float]]:
    out = []
    for d, v in zip(df[date_col], df[value_col]):
        d, v = to_date(d), to_number(v)
        if d and v is not None:
            out.append((d, v))
    return sorted(set(out))


def wide_series(df: pd.DataFrame, row: int) -> list[tuple[dt.date, float]]:
    out = []
    for c in df.columns:
        d = to_date(c)
        if d:
            v = to_number(df.iloc[row][c])
            if v is not None:
                out.append((d, v))
    return sorted(out)


def to_frame(series: list[tuple[dt.date, float]]) -> pd.DataFrame:
    """저장 형식: date, value."""
    return pd.DataFrame([{"date": d.isoformat(), "value": f"{v:g}"} for d, v in series], columns=["date", "value"])


def from_frame(df: pd.DataFrame) -> list[tuple[dt.date, float]]:
    return [(d, v) for d, v in ((to_date(a), to_number(b)) for a, b in zip(df.get("date", []), df.get("value", []))) if d and v is not None]
