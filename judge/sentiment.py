"""3. 시장 심리 지수.

계산(시트와 같다):
1. 지수(S&P 500, 코스피)에 값이 있는 날을 달력으로 삼는다(최근 IMPL['calendar_rows']일).
2. 다른 지표는 그날 값이 없으면 직전 값을 쓴다.
3. 기준일(마지막 거래일)부터 5년 안의 날짜마다 지표별 5년 백분위를 구한다. 공포 방향은 100에서 뺀다.
4. 그날 지표가 모두 있으면 평균한다(소수 6자리 반올림).
5. 오늘 평균값의 5년 백분위가 최종 점수다(소수 1자리).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from .common import IMPL, SPEC, add_months, band, excel_round, is_num, percentile

# 지표: (키, 이름, 공포 방향이 '높을수록'인지, 최종 자료일을 볼 원자료)
MARKETS = {
    "미국": {
        "index": "sp500",
        "raw": ("sp500", "vix", "baa"),
        "indicators": (
            ("vix", "VIX", True, ("vix",)),
            ("baa", "Baa − 미 10년물", True, ("baa",)),
            ("ma", "S&P 500 / 125일 평균", False, ("sp500",)),
        ),
    },
    "한국": {
        "index": "kospi",
        "raw": ("kospi", "vkospi", "aa", "ktb", "credit"),
        "indicators": (
            ("vkospi", "VKOSPI", True, ("vkospi",)),
            ("spread", "회사채 AA- − 국고채 3년", True, ("aa", "ktb")),
            ("ma", "코스피 / 125일 평균", False, ("kospi",)),
            ("credit", "신용융자잔고 20일 증감률", False, ("credit",)),
        ),
    },
}


@dataclass
class SentimentResult:
    last_date: dt.date | None = None
    cutoff: dt.date | None = None
    score: float | None = None
    band: str = ""
    times: int | None = None
    weeks: int | None = None
    composite: float | None = None
    indicators: list = field(default_factory=list)
    message: str = ""
    rows: list = field(default_factory=list)


def clean(rows):
    """원자료에서 날짜와 숫자 값이 모두 있는 줄만 남긴다(입력 순서 유지)."""
    return [(d, float(v)) for d, v in rows if isinstance(d, dt.date) and is_num(v)]


def _first_by_date(pairs):
    out = {}
    for d, v in pairs:
        out.setdefault(d, v)
    return out


def compute(market: str, raw: dict) -> SentimentResult:
    cfg = MARKETS[market]
    idx = clean(raw.get(cfg["index"], []))
    base = _first_by_date(idx)
    dates = sorted(d for d, _ in idx)
    n_cal = IMPL["calendar_rows"]
    cal = dates[max(len(dates) - n_cal, 0) :][:n_cal]
    res = SentimentResult()
    if not cal:
        res.message = "원자료 없음"
        return res

    others = [k for k in cfg["raw"] if k != cfg["index"]]
    lookup = {k: _first_by_date(clean(raw.get(k, []))) for k in others}
    rows, prev = [], {k: None for k in others}
    for d in cal:
        row = {"date": d, "base": base[d]}
        for k in others:
            row[k] = lookup[k].get(d, prev[k])
            prev[k] = row[k]
        rows.append(row)

    ma_n, lag = SPEC["ma_days"], SPEC["credit_lag"]
    for i, row in enumerate(rows):
        row["ma"] = None
        if i + 1 >= ma_n:
            avg = math.fsum(r["base"] for r in rows[i - ma_n + 1 : i + 1]) / ma_n
            row["ma"] = row["base"] / avg - 1
    if market == "한국":
        for row in rows:
            row["credit_level"] = row.pop("credit")
        for i, row in enumerate(rows):
            row["spread"] = (
                excel_round(row["aa"] - row["ktb"], IMPL["tie_digits"])
                if row["aa"] is not None and row["ktb"] is not None
                else None
            )
            now = row["credit_level"]
            past = rows[i - lag]["credit_level"] if i + 1 > lag else None
            row["credit"] = now / past - 1 if now is not None and past is not None and past > 0 else None

    last = cal[-1]
    cutoff = add_months(last, -SPEC["sentiment_months"])
    inw = [r["date"] > cutoff for r in rows]
    n_inw = sum(inw)

    greeds = {}
    for key, label, fear_high, _ in cfg["indicators"]:
        window = [r[key] for r, w in zip(rows, inw) if w and r[key] is not None]
        g = []
        for r, w in zip(rows, inw):
            if w and r[key] is not None:
                p = percentile(r[key], window)
                g.append(100 - p if fear_high else p)
            else:
                g.append(None)
        greeds[key] = (g, window)

    comps = []
    for i, w in enumerate(inw):
        gs = [greeds[k][0][i] for k, *_ in cfg["indicators"]]
        if w and all(v is not None for v in gs):
            comps.append(excel_round(sum(gs) / len(gs), IMPL["tie_digits"]))
        else:
            comps.append(None)
        rows[i]["composite"] = comps[-1]

    issues = []
    for key, label, fear_high, sources in cfg["indicators"]:
        g, window = greeds[key]
        latest = rows[-1][key]
        src_last = [max((d for d, _ in clean(raw.get(s, []))), default=None) for s in sources]
        last_src = None if any(x is None for x in src_last) else min(src_last)
        mine = []
        if len(window) < n_inw:
            mine.append(f"{label} 5년 자료 부족")
        if last_src is None or last_src < last - dt.timedelta(days=IMPL["stale_days"]):
            mine.append(f"{label} 자료 지연")
        issues += mine
        res.indicators.append(
            {
                "key": key,
                "label": label,
                "latest": latest,
                "last_date": last_src,
                "pct": percentile(latest, window) if latest is not None and window else None,
                "fear_high": fear_high,
                "greed": g[-1],
                "n": len(window),
                "issues": ", ".join(mine),
            }
        )

    res.last_date, res.cutoff, res.rows = last, cutoff, rows
    res.composite = comps[-1]
    if res.composite is not None:
        res.score = excel_round(percentile(res.composite, [c for c in comps if c is not None]), 1)
        res.band, res.times, res.weeks = band(res.score)
    res.message = ", ".join(issues) if issues else "이상 없음"
    return res
