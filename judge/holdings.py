"""5. 손실 한도, 6. 매도 판단, 7. 매수 이유 점검, 3번의 신규 매수 분할 계획."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .common import SPEC, band, excel_round, fmt_won, is_num


@dataclass
class Reason:
    """매수 이유 한 줄."""

    code: str
    no: int | None = None
    text: str = ""
    core: bool = False  # 핵심 이유
    evidence: str = ""  # 확인할 근거
    break_rule: str = ""  # 무너짐 기준
    checked: dt.date | None = None  # 최근 점검일
    result: str = ""  # 점검 결과: "유지" / "무너짐"


def record_status(code: str, reasons: list[Reason]) -> str:
    """7. 이유 1~3개, 핵심 1개, 이유마다 근거와 무너짐 기준. '기록 완료'가 아니면 사지 않는다."""
    rows = [r for r in reasons if r.code == code]
    if not rows:
        return "기록 없음"
    if len(rows) > 3:
        return "이유 3개 초과"
    if sum(r.core for r in rows) != 1:
        return "핵심 1개 표시 필요"
    if any(not r.evidence or not r.break_rule for r in rows):
        return "근거·기준 미기재"
    return "기록 완료"


def reason_note(r: Reason, earnings: dict) -> str:
    """매수이유 시트의 행별 안내. earnings: 종목코드 → 최근 실적 발표일(보유 종목)."""
    if not r.code:
        return ""
    if not r.evidence or not r.break_rule:
        return "근거·무너짐 기준을 채우세요"
    if r.core and r.result == "무너짐":
        return "핵심 이유 무너짐 → 매도 검토"
    last = earnings.get(r.code)
    if last is not None and (r.checked is None or r.checked < last):
        return "실적 발표 뒤 점검 필요"
    return ""


def core_broken(code: str, reasons: list[Reason]) -> bool:
    return any(r.code == code and r.core and r.result == "무너짐" for r in reasons)


def earnings_check(code: str, reasons: list[Reason], last_earnings: dt.date | None) -> str:
    """실적 발표 뒤에 점검하지 않은 이유가 있으면 '점검 필요'."""
    if last_earnings is None:
        return ""
    rows = [r for r in reasons if r.code == code]
    if not rows:
        return "이유 기록 없음"
    if any(r.checked is None or r.checked < last_earnings for r in rows):
        return "점검 필요"
    return "점검 완료"


@dataclass
class Account:
    total_krw: float  # 전체 투자 계좌 평가액(지수 몫 포함)
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
    last_earnings: dt.date | None = None  # 최근 실적 발표일


@dataclass
class HoldingResult:
    holding: Holding
    value_krw: float | None
    loss_krw: float | None
    loss_ratio: float | None
    price_change: float | None
    loss_hit: bool
    record: str
    core_broken: bool
    earnings: str
    weight: float | None
    conc_hit: bool
    excess_krw: float | None
    score: float | None
    best_text: str
    replace_hit: bool
    action: str


def evaluate_holdings(account: Account, holdings: list[Holding], reasons: list[Reason], pools: dict):
    """pools: 국가 → (stocks.evaluate_pool 결과 목록, 최고 미보유 후보)."""
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
        loss_hit = (loss_ratio is not None and loss_ratio >= SPEC["loss_account"]) or (
            chg is not None and chg <= SPEC["loss_price"]
        )
        weight = value / total if value is not None and total > 0 else None
        conc_hit = n_held >= SPEC["conc_min_holdings"] and weight is not None and weight > SPEC["conc_max"]
        excess = value - SPEC["conc_max"] * total if conc_hit else None

        results, best = pools.get(h.country, ([], None))
        mine = next((r for r in results if r.stock.code == h.code), None)
        score = mine.score if mine is not None and mine.scored else None
        best_text = f"{best.stock.name} ({best.score:.1f})" if best is not None else ""
        replace_hit = (
            score is not None
            and score < SPEC["replace_below"]
            and best is not None
            and excel_round(best.score - score, 1) >= SPEC["replace_gap"]
        )
        broken = core_broken(h.code, reasons)

        if loss_hit:
            action = "① 손실 한도 도달 → 매도"
        elif broken:
            action = "② 핵심 매수 이유 붕괴 → 매도 검토"
        elif conc_hit:
            action = f"③ 비중 초과 → 초과분 {fmt_won(excess)}원 매도"
        elif replace_hit:
            action = f"④ 교체 제안 → {best.stock.name}"
        else:
            action = "유지"

        out.append(
            HoldingResult(
                holding=h,
                value_krw=value,
                loss_krw=loss,
                loss_ratio=loss_ratio,
                price_change=chg,
                loss_hit=loss_hit,
                record=record_status(h.code, reasons),
                core_broken=broken,
                earnings=earnings_check(h.code, reasons, h.last_earnings),
                weight=weight,
                conc_hit=conc_hit,
                excess_krw=excess,
                score=score,
                best_text=best_text,
                replace_hit=replace_hit,
                action=action,
            )
        )
    return out


@dataclass
class BuyPlan:
    country: str
    code: str
    name: str = ""
    amount_krw: float | None = None
    start: dt.date | None = None


def plan_purchase(plan: BuyPlan, sentiment_score, stock_score, record: str) -> dict:
    """3. 신규 종목 매수를 몇 번에 나눌지. 금액은 똑같이 나눈다."""
    out = {"band": "", "times": None, "weeks": None, "each": None, "dates": []}
    if is_num(sentiment_score):
        out["band"], out["times"], out["weeks"] = band(sentiment_score)
    if is_num(sentiment_score) and record == "기록 완료":  # 사지 않을 종목에는 금액·날짜를 내지 않는다
        if is_num(plan.amount_krw):
            out["each"] = plan.amount_krw / out["times"]
        if plan.start is not None:
            out["dates"] = [plan.start + dt.timedelta(days=7 * out["weeks"] * k) for k in range(out["times"])]

    if stock_score is None:
        candidate = "점수 없음"
    elif stock_score >= SPEC["candidate_score"]:
        candidate = "예"
    else:
        candidate = "아니오(70 미만)"
    out["candidate"] = candidate

    if record != "기록 완료":
        out["advice"] = "매수하지 않음: 매수 이유 " + record
    elif not is_num(sentiment_score):
        out["advice"] = "심리 점수 없음"
    else:
        if out["times"] == 1:
            how = "1회에 전부"
            each = f", {fmt_won(out['each'])}원" if out["each"] is not None else ""
        else:
            how = f"{out['times']}회, {out['weeks']}주 간격"
            each = f", 1회 {fmt_won(out['each'])}원" if out["each"] is not None else ""
        warn = " · 주의: 편입 후보 아님" if candidate != "예" else ""
        out["advice"] = f"{how}{each}{warn}"
    return out
