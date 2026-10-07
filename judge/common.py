"""공통 상수와 계산 도구.

명세(docs/spec.md)의 확정값은 SPEC, 구현하는 쪽이 정한 값은 IMPL에 둔다.
시트의 '설정' 탭도 이 값들로 만든다.
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from numbers import Real

COUNTRIES = ("한국", "미국")

# 명세 확정값
SPEC = {
    "candidate_score": 70,  # 1. 편입 후보: 점수 70 이상
    "replace_below": 50,  # 1·6. 교체 제안: 보유 종목 점수 50 미만
    "replace_gap": 10,  # 1·6. 같은 국가에 10점 이상 높은 후보
    "debt_ratio_max": 2.0,  # 2. 부채비율 200% 이하
    "mcap_min": {"한국": 5000, "미국": 2000},  # 2. 5,000억 원 / 20억 달러 (억 원, 백만 달러 단위)
    "loss_account": 0.02,  # 5. 계좌 평가액의 2%
    "loss_price": -0.25,  # 5. 매수 평균가 대비 -25%
    "conc_max": 0.40,  # 6. 개별 몫의 40% 초과
    "conc_min_holdings": 3,  # 6. 3종목 이상 보유 시
    "sentiment_months": 60,  # 3. 최근 5년
    "ma_days": 125,  # 3. 125일 이동평균
    "credit_lag": 20,  # 3. 신용융자잔고 20일 증감률
    "macro_months": 120,  # 4. 최근 10년
    "change_months": 3,  # 4. 3개월 변화
}

# 3. 시장 심리 구간: (하한, 구간, 횟수, 간격(주)). 하한 이상 ~ 다음 하한 미만.
BANDS = (
    (0, "극단 공포", 1, 0),
    (10, "공포", 2, 2),
    (30, "중립", 2, 4),
    (70, "탐욕", 3, 4),
    (90, "극단 탐욕", 4, 4),
)

# 구현하는 쪽이 정한 값
IMPL = {
    "strong_pct": 70,  # 한 줄 요약: 백분위 70 이상이면 강점
    "weak_pct": 30,  # 한 줄 요약: 백분위 30 미만이면 약점
    "stale_days": 7,  # 심리 지표 자료가 기준일보다 7일 넘게 오래되면 경고
    "coverage_slack_days": 45,  # 거시 지표 10년 창의 첫 자료가 이만큼 늦으면 '자료 부족'
    "calendar_rows": 1500,  # 심리 계산에 쓰는 최근 거래일 수(5년 + 125일을 덮음)
    "tie_digits": 6,  # 평균값은 소수 6자리로 반올림한 뒤 동점이면 평균 순위
}


def is_num(x) -> bool:
    return isinstance(x, Real) and not isinstance(x, bool) and x == x


def excel_round(x: float, digits: int) -> float:
    """스프레드시트 ROUND와 같은 반올림(0.5는 0에서 먼 쪽)."""
    q = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))


def _rank(x, vals):
    less = sum(1 for v in vals if v < x)
    equal = sum(1 for v in vals if v == x)
    return less + (equal + 1) / 2  # 동점은 평균 순위


def percentile(x: float, values) -> float:
    """풀 안 백분위(0~100). 가장 낮으면 0, 가장 높으면 100, 동점은 평균 순위, 값이 하나면 50.

    시트 수식: (RANK.AVG(x, 범위, 1) - 1) / (개수 - 1) * 100
    """
    vals = [v for v in values if is_num(v)]
    n = len(vals)
    if n == 0:
        raise ValueError("빈 풀")
    if n == 1:
        return 50.0
    return (_rank(x, vals) - 1) / (n - 1) * 100


def top_share(x: float, values) -> float:
    """'상위 몇 %'인지. 풀에서 가장 높으면 100/n."""
    vals = [v for v in values if is_num(v)]
    n = len(vals)
    return (n - _rank(x, vals) + 1) / n * 100


def add_months(d: dt.date, months: int) -> dt.date:
    """스프레드시트 EDATE와 같다(말일은 그 달 말일로 맞춘다)."""
    m = d.month - 1 + months
    year, month = d.year + m // 12, m % 12 + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def band(score: float):
    """심리 점수 → (구간, 횟수, 간격(주))."""
    chosen = BANDS[0]
    for b in BANDS:
        if score >= b[0]:
            chosen = b
    return chosen[1], chosen[2], chosen[3]


def fmt_pct(v: float) -> str:
    """TEXT(v, "0.0%")"""
    return f"{excel_round(v * 100, 1):.1f}%"


def fmt_won(v: float) -> str:
    """TEXT(v, "#,##0")"""
    return f"{int(excel_round(v, 0)):,}"
