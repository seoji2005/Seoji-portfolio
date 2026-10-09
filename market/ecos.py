"""한국은행 ECOS(무료, 인증키 필요): 시장금리(일별) 817Y002.

회사채(3년, AA-)와 국고채(3년)는 연 %, 일별. 금리차 = AA- − 국고채(%p)로 사전 3번과 같은 정의다.
"""

from __future__ import annotations

import datetime as dt

URL = "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100000/{table}/D/{start}/{end}/{item}"
ITEMS = {"aa": ("817Y002", "010300000", "회사채(3년, AA-)"), "ktb": ("817Y002", "010200000", "국고채(3년)")}


class EcosError(RuntimeError):
    pass


def parse(data: dict) -> list[tuple[dt.date, float | None]]:
    block = data.get("StatisticSearch")
    if block is None:
        err = data.get("RESULT", {})
        raise EcosError(f"{err.get('CODE', '')} {err.get('MESSAGE', '')}".strip() or "ECOS 응답 형식이 다름")
    out = []
    for row in block.get("row", []):
        try:
            d = dt.datetime.strptime(row["TIME"], "%Y%m%d").date()
        except (KeyError, ValueError):
            continue
        try:
            v = float(row.get("DATA_VALUE", ""))
        except ValueError:
            v = None
        out.append((d, v))
    return out


def fetch(key: str, which: str, start: dt.date, end: dt.date, session=None):
    import requests

    table, item, _ = ITEMS[which]
    http = session or requests
    r = http.get(URL.format(key=key, table=table, start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"), item=item), timeout=30)
    r.raise_for_status()
    return parse(r.json())
