"""8. 포트폴리오 점수(2026-10-08 추가): 보유 종목 점수의 평가액 가중 평균. 표시만 한다."""

from __future__ import annotations

from dataclasses import dataclass, field

from .common import SPEC, excel_round


@dataclass
class Position:
    country: str
    code: str
    name: str
    value_krw: float  # 원화 평가액
    score: float | None = None  # 1번 종목 점수(없으면 None)
    reason: str = ""  # 점수가 없는 이유


@dataclass
class PortfolioScore:
    total: float | None
    by_country: dict
    weights: dict  # 종목코드 → 주식 합계 대비 비중
    scored_weight: float  # 점수가 있는 종목의 비중 합
    unscored: list = field(default_factory=list)  # (이름, 비중, 이유)


def _weighted(positions):
    scored = [p for p in positions if p.score is not None and p.value_krw > 0]
    total = sum(p.value_krw for p in scored)
    if total <= 0:
        return None
    return excel_round(sum(p.value_krw * p.score for p in scored) / total, 1)


def portfolio_score(positions: list[Position]) -> PortfolioScore:
    stock_total = sum(p.value_krw for p in positions if p.value_krw > 0)
    weights = {p.code: (p.value_krw / stock_total if stock_total > 0 else 0.0) for p in positions}
    by_country = {}
    for country in dict.fromkeys(p.country for p in positions):
        by_country[country] = _weighted([p for p in positions if p.country == country])
    unscored = [(p.name, weights[p.code], p.reason or "점수 없음") for p in positions if p.score is None]
    return PortfolioScore(
        total=_weighted(positions),
        by_country=by_country,
        weights=weights,
        scored_weight=sum(weights[p.code] for p in positions if p.score is not None),
        unscored=unscored,
    )


def merge(positions: list[Position], add: Position) -> list[Position]:
    """add를 더한 새 목록. 이미 가진 종목이면 평가액을 더한다."""
    out, found = [], False
    for p in positions:
        if (p.country, p.code) == (add.country, add.code):
            out.append(Position(p.country, p.code, p.name, p.value_krw + add.value_krw, add.score, add.reason))
            found = True
        else:
            out.append(p)
    if not found:
        out.append(add)
    return out


def shares(positions: list[Position], cash_krw: float) -> dict:
    """종목코드 → 개별 몫(주식 + 대기 현금) 대비 비중. 6-3번 40% 규칙과 같은 기준."""
    held = [p for p in positions if p.value_krw > 0]
    total = sum(p.value_krw for p in held) + cash_krw
    return {p.code: p.value_krw / total for p in held} if total > 0 else {}


def concentration(positions: list[Position], cash_krw: float) -> list[tuple]:
    """6-3번: 3종목 이상 보유 중 개별 몫(주식 + 대기 현금)의 40%를 넘는 종목 → (이름, 비중, 초과분)."""
    held = [p for p in positions if p.value_krw > 0]
    total = sum(p.value_krw for p in held) + cash_krw
    if len(held) < SPEC["conc_min_holdings"] or total <= 0:
        return []
    return [(p.name, p.value_krw / total, p.value_krw - SPEC["conc_max"] * total) for p in held if p.value_krw / total > SPEC["conc_max"]]


def what_if(positions: list[Position], cash_krw: float, add: Position) -> dict:
    """add.value_krw만큼 사면 어떻게 되나. 대기 현금에서 먼저 쓰고, 모자라면 새 돈으로 본다."""
    after = merge(positions, add)
    cash_after = max(cash_krw - add.value_krw, 0.0)
    return {
        "before": portfolio_score(positions),
        "after": portfolio_score(after),
        "positions_after": after,
        "cash_after": cash_after,
        "new_money": max(add.value_krw - cash_krw, 0.0),
        "concentration_before": concentration(positions, cash_krw),
        "concentration_after": concentration(after, cash_after),
        "count_after": sum(1 for p in after if p.value_krw > 0),
    }
