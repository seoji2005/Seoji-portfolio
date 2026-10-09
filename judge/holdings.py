"""5. 손실 한도, 6. 매도 판단. 매수 이유 카드는 judge/reasons.py."""

from __future__ import annotations

from dataclasses import dataclass

from .common import SPEC, excel_round, fmt_won, is_num


@dataclass
class Account:
    total_krw: float  # 계좌 전체 평가액(지수 몫 포함)
    cash_krw: float  # 개별 몫 대기 현금
    usdkrw: float  # 현재 원/달러 환율


@dataclass
class Holding:
    country: str
    code: str
    name: str = ""
    qty: float | None = None
    avg_price: float | None = None  # 매수 평균가(현지 통화)
    cost_krw: float | None = None  # 원화 매수원가 합계
    price: float | None = None  # 현재가(현지 통화)


@dataclass
class HoldingResult:
    holding: Holding
    value_krw: float | None
    loss_krw: float | None
    loss_ratio: float | None
    price_change: float | None
    loss_hit: bool
    card_status: str  # 매수 이유 카드 상태(통과/보류/무너짐, 없으면 "")
    weight: float | None
    conc_hit: bool
    excess_krw: float | None
    score: float | None
    best_text: str
    replace_hit: bool
    signals: list  # 걸린 신호 전부(우선순위 순)
    action: str  # 가장 앞선 신호 하나, 없으면 "유지"


def evaluate_holdings(account: Account, holdings: list[Holding], card_status: dict, pools: dict) -> list[HoldingResult]:
    """card_status: 종목코드 → 매수 이유 카드 상태. pools: 국가 → (StockResult 목록, 최고 미보유 후보 StockResult)."""
    values = []
    for h in holdings:
        if is_num(h.qty) and is_num(h.price):
            values.append(h.qty * h.price * (account.usdkrw if h.country == "미국" else 1))
        else:
            values.append(None)
    n_held = sum(v is not None for v in values)
    total = sum(v for v in values if v is not None) + account.cash_krw

    out = []
    for h, value in zip(holdings, values):
        loss = h.cost_krw - value if is_num(h.cost_krw) and value is not None else None
        loss_ratio = loss / account.total_krw if loss is not None and account.total_krw > 0 else None
        chg = h.price / h.avg_price - 1 if is_num(h.price) and is_num(h.avg_price) and h.avg_price > 0 else None
        loss_hit = (loss_ratio is not None and loss_ratio >= SPEC["loss_account"]) or (chg is not None and chg <= SPEC["loss_price"])
        weight = value / total if value is not None and total > 0 else None
        conc_hit = n_held >= SPEC["conc_min_holdings"] and weight is not None and weight > SPEC["conc_max"]
        excess = value - SPEC["conc_max"] * total if conc_hit else None

        results, best = pools.get(h.country, ([], None))
        mine = next((r for r in results if r.stock.code == h.code), None)
        score = mine.score if mine is not None and mine.scored else None
        best_text = f"{best.stock.name} ({best.score:.1f})" if best is not None else ""
        replace_hit = (
            score is not None and score < SPEC["replace_below"] and best is not None
            and excel_round(best.score - score, 1) >= SPEC["replace_gap"]
        )
        status = card_status.get(h.code, "")

        signals = []
        if loss_hit:
            why = []
            if loss_ratio is not None and loss_ratio >= SPEC["loss_account"]:
                why.append(f"손실액이 계좌의 {loss_ratio:.1%}")
            if chg is not None and chg <= SPEC["loss_price"]:
                why.append(f"매수가 대비 {chg:.1%}")
            signals.append(f"① 손실 한도 도달({', '.join(why)}) → 매도")
        if status == "무너짐":
            signals.append("② 매수 이유 무너짐 → 매도 검토")
        if conc_hit:
            signals.append(f"③ 비중 {weight:.0%} > 40% → 초과분 {fmt_won(excess)}원 매도")
        if replace_hit:
            signals.append(f"④ 교체 제안 → {best.stock.name} ({best.score:.1f}점, 보유 {score:.1f}점)")

        out.append(HoldingResult(h, value, loss, loss_ratio, chg, loss_hit, status, weight, conc_hit, excess, score,
                                 best_text, replace_hit, signals, signals[0] if signals else "유지"))
    return out
