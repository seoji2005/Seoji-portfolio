"""새 사전(docs/spec.md)의 바뀐 규칙: 7 매수 이유 카드, 6 매도 판단 ②, 4 수출 전년비, 1 12-1 수정종가."""

import datetime as dt

import pandas as pd
import pytest

from judge.holdings import Account, Holding, evaluate_holdings
from judge.macro import transform
from judge.reasons import ReasonItem, card, card_status, history
from market.pool import momentum_prices

D = dt.date


def item(no, status, indicator="매출 증가율", fact="", condition="2분기 연속 0% 미만", code="A"):
    return ReasonItem(code, no, f"이유{no}", indicator, fact, condition, "", status)


# ---------------------------------------------------------------- 7 매수 이유 카드


@pytest.mark.parametrize(
    "statuses,expected",
    [(["통과", "통과"], "통과"), (["통과", "보류"], "보류"), (["보류", "무너짐", "통과"], "무너짐"), (["무너짐"], "무너짐"), ([], "")],
)
def test_card_status_order(statuses, expected):
    assert card_status([item(i, s) for i, s in enumerate(statuses, 1)]) == expected


def test_hold_never_turns_into_broken_by_itself():
    old = ReasonItem("A", 1, "이유", "지표", "", "조건", "", "보류", checked="2024-01-01")  # 2년 넘게 보류
    assert card("A", [old]).status == "보류"


def test_buy_needs_an_indicator_or_a_fact():
    assert not card("A", []).buy_ok
    no_evidence = card("A", [item(1, "통과", indicator="", fact="")])
    assert not no_evidence.buy_ok and "매수 불가" in no_evidence.buy_why
    fact_only = card("A", [item(1, "통과", indicator="", fact="핵심 고객과 10년 공급 계약 공시")])
    assert fact_only.buy_ok  # 숫자가 아니어도 확인 가능한 사실이면 됨
    mixed = card("A", [item(1, "통과", indicator="", fact=""), item(2, "통과")])
    assert mixed.buy_ok and "1번 이유: 확인 지표·사실 없음" in mixed.problems


def test_problems_listed_without_changing_status():
    c = card("A", [item(1, "통과", condition=""), item(2, ""), item(3, "통과"), item(4, "통과")])
    assert c.status == ""  # 상태를 고르지 않은 이유가 있으면 '통과'로 보지 않음
    assert "이유가 4개 — 사전은 1~3개" in c.problems
    assert "1번 이유: 무너지는 조건 없음" in c.problems
    assert "2번 이유: 상태(통과/보류/무너짐)를 고르지 않음" in c.problems


def test_history_keeps_previous_condition_and_reason():
    old = [item(1, "통과"), item(2, "통과", condition="고객 계약 해지")]
    new = [item(1, "통과", condition="3분기 연속 0% 미만"), item(3, "보류")]
    rows = history(old, new, "계절성 때문에 기간을 늘림", D(2026, 10, 9))
    assert {"changed_at": "2026-10-09", "code": "A", "no": 1, "field": "무너지는 조건", "old": "2분기 연속 0% 미만",
            "new": "3분기 연속 0% 미만", "why": "계절성 때문에 기간을 늘림"} in rows
    assert any(r["field"] == "이유 삭제" and r["no"] == 2 and "고객 계약 해지" in r["old"] for r in rows)
    with pytest.raises(ValueError):
        history(old, new, "  ", D(2026, 10, 9))
    assert history(old, [item(1, "무너짐"), item(2, "통과", condition="고객 계약 해지")], "", D(2026, 10, 9)) == []  # 상태만 바꾸면 이력 아님


# ---------------------------------------------------------------- 6 매도 판단


def test_sell_signal_two_follows_card_status():
    acc = Account(100_000_000, 0, 1.0)
    hs = [Holding("한국", "A", "가", 10, 100, 1000, 100)]
    assert evaluate_holdings(acc, hs, {"A": "보류"}, {})[0].action == "유지"  # 보류는 신호가 아님
    r = evaluate_holdings(acc, hs, {"A": "무너짐"}, {})[0]
    assert r.action == "② 매수 이유 무너짐 → 매도 검토"


def test_all_signals_listed_in_priority_order():
    acc = Account(10_000, 0, 1.0)
    hs = [Holding("한국", "A", "가", 10, 100, 1000, 70), Holding("한국", "B", "나", 1, 10, 10, 10), Holding("한국", "C", "다", 1, 10, 10, 10)]
    r = evaluate_holdings(acc, hs, {"A": "무너짐"}, {})[0]
    assert [s[0] for s in r.signals] == ["①", "②", "③"]
    assert r.action.startswith("① 손실 한도 도달(손실액이 계좌의 3.0%, 매수가 대비 -30.0%)")


# ---------------------------------------------------------------- 4 거시, 1 12-1


def test_exports_same_month_yoy():
    rows = [(D(2025, m, 1), 10.0) for m in range(1, 13)] + [(D(2026, 1, 1), 12.0), (D(2026, 2, 1), ".")]
    out = dict(transform("yoy", rows))
    assert out[D(2026, 1, 1)] == pytest.approx(0.2)
    assert out[D(2026, 2, 1)] is None and out[D(2025, 6, 1)] is None


def test_momentum_uses_adjusted_close():
    idx = pd.bdate_range("2025-09-01", "2026-09-30")
    adj = pd.Series(100.0, index=idx)
    adj[idx >= "2026-01-01"] = 110.0
    p12, p1, _ = momentum_prices(adj)
    assert (p12, p1) == (100.0, 110.0)
