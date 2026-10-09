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
    ("exports", "한국 수출 전년비", "한국 경기", "yoy", "%", "FRED XTEXVA01KRM667N"),
)
MONTHLY = {"sahm", "exports"}  # 월별 자료(날짜는 그달 1일)


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
    if kind == "yoy":  # 같은 달 전년비(월별 자료)
        by_date = {}
        for d, v in rows:
            if is_num(v):
                by_date.setdefault(d, float(v))
        for d, v in rows:
            prev = by_date.get(add_months(d, -12))
            out.append((d, v / prev - 1 if is_num(v) and prev not in (None, 0) else None))
        return out
    raise ValueError(kind)


def basis(kind: str, rows, day: dt.date) -> list[tuple]:
    """그날 값을 계산할 때 쓴 원자료 [(날짜, 원값), (비교 날짜, 원값)]. 수준 값은 하나뿐."""
    obs = [(d, float(v)) for d, v in rows if isinstance(d, dt.date) and is_num(v)]
    now = next(((d, v) for d, v in obs if d == day), None)
    if now is None or kind == "level":
        return [now] if now else []
    if kind == "yoy":
        target = add_months(day, -12)
        base = next(((d, v) for d, v in obs if d == target), None)
    else:  # diff, ratio: 3개월 전 날짜 또는 그 전 마지막 값(transform과 같음)
        target = add_months(day, -SPEC["change_months"])
        before = [(d, v) for d, v in obs if d <= target]
        base = before[-1] if before else None
    return [now, base] if base else [now]


def panel(raw: dict) -> list[dict]:
    result = []
    for key, label, what, kind, unit, source in SERIES:
        rows = raw.get(key, [])
        xs = transform(kind, rows)
        have = [(d, x) for d, x in xs if x is not None]
        item = {"key": key, "label": label, "what": what, "unit": unit, "source": source}
        item.update(current=None, last_date=None, pct=None, n=0, first=None, basis=[])
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
                basis=basis(kind, rows, last),
            )
            if item["first"] > cutoff + dt.timedelta(days=IMPL["coverage_slack_days"]):
                issues.append("10년 자료 부족")
        else:
            issues.insert(0, "자료 없음")
        item["issues"] = ", ".join(issues) if issues else "이상 없음"
        result.append(item)
    return result
