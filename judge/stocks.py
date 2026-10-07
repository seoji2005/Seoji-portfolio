"""1. 종목 점수, 2. 종목 거름망."""

from __future__ import annotations

from dataclasses import dataclass, field

from .common import IMPL, SPEC, excel_round, fmt_pct, is_num, percentile, top_share

# (키, 이름, 강점 문구, 약점 문구, 보통일 때 이름)
METRICS = (
    ("roe", "ROE", "수익성 높음", "수익성 낮음", "수익성"),
    ("growth", "매출성장률", "성장 빠름", "성장 느림", "성장"),
    ("ey", "이익수익률", "가격 쌈", "가격 비쌈", "가격"),
    ("mom", "12-1 수익률", "추세 좋음", "추세 약함", "추세"),
)


@dataclass
class Stock:
    """종목 시트 한 줄. 금액은 한국 억 원, 미국 백만 달러. 주가는 현지 통화(수정주가)."""

    code: str
    name: str = ""
    held: bool = False
    excluded_sector: bool = False  # 금융(은행·보험·증권)·리츠
    basis: str = ""  # 재무 기준 시점(메모)
    net_income: float | None = None  # 최근 1년 당기순이익
    equity: float | None = None  # 자본총계
    liabilities: float | None = None  # 부채총계
    op_income: float | None = None  # 최근 1년 영업이익
    revenue: float | None = None  # 최근 1년 매출
    revenue_3y_ago: float | None = None  # 3년 전 같은 1년 매출
    market_cap: float | None = None
    debt: float | None = None  # 이자부부채
    cash: float | None = None  # 현금성자산
    price_12m: float | None = None  # 12개월 전 주가
    price_1m: float | None = None  # 1개월 전 주가


@dataclass
class StockResult:
    stock: Stock
    debt_ratio: float | None
    filter_reasons: list[str]
    metrics: dict
    missing: list[str]
    scored: bool = False
    pct: dict = field(default_factory=dict)
    top: dict = field(default_factory=dict)
    avg: float | None = None
    score: float | None = None
    summary: str = ""
    decision: str = ""
    cards: dict = field(default_factory=dict)

    @property
    def filter_text(self) -> str:
        return "통과" if not self.filter_reasons else "제외: " + ", ".join(self.filter_reasons)

    @property
    def status(self) -> str:
        if self.filter_reasons:
            return "점수 없음(거름망)"
        if self.missing:
            return "점수 없음(결측: " + ", ".join(self.missing) + ")"
        return "채점"


def debt_ratio(s: Stock):
    if is_num(s.liabilities) and is_num(s.equity) and s.equity > 0:
        return s.liabilities / s.equity
    return None


def filter_reasons(s: Stock, country: str) -> list[str]:
    """2. 거름망. 하나라도 걸리면 점수를 매기지 않는다. 자료가 없으면 통과로 보지 않는다."""
    reasons = []
    if s.excluded_sector:
        reasons.append("금융·리츠")
    if not is_num(s.op_income):
        reasons.append("영업이익 없음")
    elif s.op_income <= 0:
        reasons.append("영업적자")
    if not (is_num(s.equity) and is_num(s.liabilities)):
        reasons.append("부채비율 자료 없음")
    elif s.equity <= 0:
        reasons.append("자본잠식")
    elif s.liabilities / s.equity > SPEC["debt_ratio_max"]:
        reasons.append("부채비율 초과")
    if not is_num(s.market_cap):
        reasons.append("시총 없음")
    elif s.market_cap < SPEC["mcap_min"][country]:
        reasons.append("시총 미달")
    return reasons


def metrics(s: Stock) -> dict:
    """1. 지표 4개. 분모가 0 이하이거나 자료가 없으면 None(결측)."""
    m = {"roe": None, "growth": None, "ey": None, "mom": None}
    if is_num(s.net_income) and is_num(s.equity) and s.equity > 0:
        m["roe"] = s.net_income / s.equity
    if is_num(s.revenue) and is_num(s.revenue_3y_ago) and s.revenue > 0 and s.revenue_3y_ago > 0:
        m["growth"] = (s.revenue / s.revenue_3y_ago) ** (1 / 3) - 1
    if all(is_num(v) for v in (s.op_income, s.market_cap, s.debt, s.cash)):
        ev = s.market_cap + s.debt - s.cash
        if ev > 0:
            m["ey"] = s.op_income / ev
    if is_num(s.price_12m) and is_num(s.price_1m) and s.price_12m > 0 and s.price_1m > 0:
        m["mom"] = s.price_1m / s.price_12m - 1
    return m


def summary_text(pct: dict) -> str:
    strong = [p[2] for p in METRICS if pct[p[0]] >= IMPL["strong_pct"]]
    weak = [p[3] for p in METRICS if pct[p[0]] < IMPL["weak_pct"]]
    mid = [p[4] for p in METRICS if IMPL["weak_pct"] <= pct[p[0]] < IMPL["strong_pct"]]
    parts = [", ".join(strong), ", ".join(weak), ("보통: " + "·".join(mid)) if mid else ""]
    return ". ".join(p for p in parts if p)


def evaluate_pool(stocks: list[Stock], country: str):
    """같은 국가 풀 전체를 평가한다. (결과 목록, 최고 미보유 후보 결과 또는 None)을 돌려준다."""
    results = []
    for s in stocks:
        m = metrics(s)
        r = StockResult(
            stock=s,
            debt_ratio=debt_ratio(s),
            filter_reasons=filter_reasons(s, country),
            metrics=m,
            missing=[p[1] for p in METRICS if m[p[0]] is None],
        )
        r.scored = not r.filter_reasons and not r.missing
        results.append(r)

    pool = [r for r in results if r.scored]
    for r in pool:
        for key, *_ in METRICS:
            vals = [q.metrics[key] for q in pool]
            r.pct[key] = percentile(r.metrics[key], vals)
            r.top[key] = top_share(r.metrics[key], vals)
        r.avg = excel_round(sum(r.pct[k] for k, *_ in METRICS) / 4, IMPL["tie_digits"])
    for r in pool:
        r.score = excel_round(percentile(r.avg, [q.avg for q in pool]), 1)

    candidates = [r for r in pool if not r.stock.held]
    best = None
    for r in candidates:  # 동점이면 시트 위쪽(먼저 입력한) 종목
        if best is None or r.score > best.score:
            best = r

    for r in results:
        s = r.stock
        if r.scored:
            r.summary = summary_text(r.pct)
        elif r.filter_reasons:
            r.summary = r.filter_text
        else:
            r.summary = r.status

        if s.held and r.scored:
            if (
                r.score < SPEC["replace_below"]
                and best is not None
                and excel_round(best.score - r.score, 1) >= SPEC["replace_gap"]
            ):
                r.decision = f"교체 제안 → {best.stock.name} ({best.score:.1f})"
            else:
                r.decision = "보유 유지"
        elif s.held:
            r.decision = "보유 · 점수 없음"
        elif r.scored and r.score >= SPEC["candidate_score"]:
            r.decision = "편입 후보"

        for key, *_ in METRICS:
            v = r.metrics[key]
            if r.scored:
                r.cards[key] = f"{fmt_pct(v)} · 상위 {excel_round(r.top[key], 0):.0f}%"
            else:
                r.cards[key] = "결측" if v is None else fmt_pct(v)
    return results, best
