"""4. 거시 참고 패널. 표시만 한다. 어떤 규칙의 입력도 아니고 합산 점수도 없다.

원자료는 FRED 형식(날짜 오름차순, 빈 값은 '.' 또는 빈칸)을 가정한다.
"""

from __future__ import annotations

import bisect
import datetime as dt

from .common import IMPL, SPEC, add_months, is_num, percentile

# (키, 지표, 보는 것, 계산 방식, 단위, 출처)
SERIES = (
    ("sahm", "실시간 Sahm 지표", "미국 경기 둔화", "level", "%p", "FRED SAHMREALTIME"),
    ("dgs10", "미 10년물 금리 3개월 변화", "금리 급등", "diff", "%p", "FRED DGS10"),
    ("t10y3m", "10년물 − 3개월물 금리차", "장단기 역전", "level", "%p", "FRED T10Y3M"),
    ("jpy", "엔/달러 3개월 변화율", "엔 캐리 청산 압력", "ratio", "%", "FRED DEXJPUS"),
    ("exports", "한국 수출 3개월 전년비", "한국 경기", "yoy3", "%", "FRED XTEXVA01KRM667N"),
)


def transform(kind: str, rows) -> list:
    """원자료 줄마다 패널에 쓸 값(없으면 None)."""
    rows = [(d, v) for d, v in rows if isinstance(d, dt.date)]
    dates = [d for d, _ in rows]
    m = SPEC["change_months"]
    out = []
    if kind == "level":
        return [(d, float(v) if is_num(v) else None) for d, v in rows]
    if kind in ("diff", "ratio"):
        filled, last = [], None
        for _, v in rows:
            if is_num(v):
                last = float(v)
            filled.append(last)
        for d, v in rows:
            x = None
            pos = bisect.bisect_right(dates, add_months(d, -m)) - 1
            if is_num(v) and pos >= 0 and filled[pos] is not None:
                if kind == "diff":
                    x = v - filled[pos]
                elif filled[pos] != 0:
                    x = v / filled[pos] - 1
            out.append((d, x))
        return out
    if kind == "yoy3":
        nums = [(d, float(v)) for d, v in rows if is_num(v)]

        def window(lo, hi):
            vals = [v for d, v in nums if lo < d <= hi]
            return len(vals), sum(vals)

        for d, v in rows:
            x = None
            if is_num(v):
                n1, s1 = window(add_months(d, -3), d)
                n0, s0 = window(add_months(d, -15), add_months(d, -12))
                if n1 == 3 and n0 == 3 and s0 != 0:
                    x = s1 / s0 - 1
            out.append((d, x))
        return out
    raise ValueError(kind)


def panel(raw: dict) -> list[dict]:
    result = []
    for key, label, what, kind, unit, source in SERIES:
        rows = raw.get(key, [])
        xs = transform(kind, rows)
        have = [(d, x) for d, x in xs if x is not None]
        item = {"key": key, "label": label, "what": what, "unit": unit, "source": source}
        item.update(current=None, last_date=None, pct=None, n=0, first=None)
        issues = []
        dates = [d for d, _ in rows if isinstance(d, dt.date)]
        if any(b <= a for a, b in zip(dates, dates[1:])):
            issues.append("날짜 정렬 오류")
        if have:
            last = max(d for d, _ in have)
            current = next(x for d, x in have if d == last)
            cutoff = add_months(last, -SPEC["macro_months"])
            window = [(d, x) for d, x in have if d > cutoff]
            item.update(
                current=current,
                last_date=last,
                pct=percentile(current, [x for _, x in window]),
                n=len(window),
                first=min(d for d, _ in window),
            )
            if item["first"] > cutoff + dt.timedelta(days=IMPL["coverage_slack_days"]):
                issues.append("10년 자료 부족")
        else:
            issues.insert(0, "자료 없음")
        item["issues"] = ", ".join(issues) if issues else "이상 없음"
        result.append(item)
    return result
