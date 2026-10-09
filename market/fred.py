"""FRED 일별·월별 자료(키 없이 쓰는 CSV 내려받기)."""

from __future__ import annotations

import csv
import datetime as dt
import io

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"


def parse_csv(text: str) -> list[tuple[dt.date, float | None]]:
    """첫 열 날짜, 둘째 열 값. 빈 값('.' 또는 빈칸)은 None."""
    out = []
    reader = csv.reader(io.StringIO(text))
    next(reader, None)  # 머리글
    for row in reader:
        if len(row) < 2:
            continue
        try:
            d = dt.date.fromisoformat(row[0].strip())
        except ValueError:
            continue
        try:
            v = float(row[1])
        except ValueError:
            v = None
        out.append((d, v))
    return out


def fetch(series_id: str, start: dt.date, session=None) -> list[tuple[dt.date, float | None]]:
    import requests

    http = session or requests
    r = http.get(URL.format(id=series_id, start=start.isoformat()), timeout=30)
    r.raise_for_status()
    return parse_csv(r.text)
