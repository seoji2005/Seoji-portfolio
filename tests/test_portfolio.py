"""8. 포트폴리오 점수, 9. 과거 성과 점검 — 손으로 계산한 값과 대조."""

import math

import pandas as pd
import pytest

from judge import backtest
from judge.portfolio import Position, concentration, portfolio_score, what_if


def test_weighted_score_skips_unscored_and_reports_them():
    ps = portfolio_score(
        [
            Position("한국", "A", "가", 6_000_000, 80),
            Position("미국", "B", "나", 3_000_000, 50),
            Position("미국", "C", "다", 1_000_000, None, "거름망 제외: 영업적자"),
        ]
    )
    assert ps.total == round((6 * 80 + 3 * 50) / 9, 1)  # 70.0
    assert ps.by_country == {"한국": 80, "미국": 50}
    assert ps.weights == {"A": 0.6, "B": 0.3, "C": 0.1}
    assert ps.scored_weight == pytest.approx(0.9)
    assert ps.unscored == [("다", 0.1, "거름망 제외: 영업적자")]


def test_empty_portfolio():
    ps = portfolio_score([])
    assert ps.total is None and ps.by_country == {}


def test_concentration_rule_needs_three_and_includes_cash():
    two = [Position("한국", "A", "가", 90, 1), Position("한국", "B", "나", 10, 1)]
    assert concentration(two, 0) == []
    three = two + [Position("한국", "C", "다", 10, 1)]
    hits = concentration(three, 40)  # 개별 몫 150 → 가 60%
    assert hits == [("가", 0.6, 90 - 0.4 * 150)]


def test_what_if_adds_to_existing_and_uses_cash_first():
    pos = [Position("한국", "A", "가", 5_000_000, 40), Position("미국", "B", "나", 5_000_000, 60)]
    out = what_if(pos, 3_000_000, Position("미국", "C", "다", 5_000_000, 100))
    assert out["before"].total == 50
    assert out["after"].total == round((5 * 40 + 5 * 60 + 5 * 100) / 15, 1)
    assert out["cash_after"] == 0 and out["new_money"] == 2_000_000
    assert out["count_after"] == 3
    again = what_if(pos, 0, Position("한국", "A", "가", 1_000_000, 40))
    assert [p.value_krw for p in again["positions_after"]] == [6_000_000, 5_000_000]


# ---------------------------------------------------------------- 과거 성과


def monthly_frame(rows, start="2024-10-31"):
    idx = pd.date_range(start, periods=len(rows), freq="ME")
    return pd.DataFrame(rows, index=idx, columns=["A", "B"])


def test_buy_and_hold_vs_annual_rebalance():
    m = monthly_frame([[100, 100], [110, 90], [132, 90]], start="2025-11-30")  # 11월, 12월, 1월
    hold = backtest.simulate(m, {"A": 1, "B": 1}, "none", 1.0)
    assert list(hold.round(10)) == [1.0, 1.0, round(0.005 * 132 + 0.005 * 90, 10)]
    rebal = backtest.simulate(m, {"A": 1, "B": 1}, "annual", 1.0)
    assert rebal.iloc[-1] == pytest.approx(0.5 * 132 / 110 + 0.5 * 90 / 90)  # 12월 말에 50:50으로 다시 맞춤


def test_stats_by_hand():
    idx = pd.date_range("2025-10-31", periods=4, freq="ME")
    v = pd.Series([1.0, 1.1, 0.99, 1.21], index=idx)
    s = backtest.stats(v)
    r = [0.1, -0.1, 1.21 / 0.99 - 1]
    mean = sum(r) / 3
    sd = math.sqrt(sum((x - mean) ** 2 for x in r) / 2)
    assert s["months"] == 3
    assert s["cagr"] == pytest.approx(1.21 ** (12 / 3) - 1)
    assert s["mdd"] == pytest.approx(0.99 / 1.1 - 1)
    assert s["vol"] == pytest.approx(sd * math.sqrt(12))
    assert s["sharpe"] == pytest.approx(mean * 12 / (sd * math.sqrt(12)))
    ann = backtest.annual_returns(v)
    assert ann[2025] == pytest.approx(0.99 / 1.0 - 1)  # 시작(10월 말) → 12월 말
    assert ann[2026] == pytest.approx(1.21 / 0.99 - 1)  # 12월 말 → 마지막(1월 말)
    assert s["best_year"] == (2026, pytest.approx(1.21 / 0.99 - 1)) and s["worst_year"] == (2025, pytest.approx(-0.01))


def test_run_starts_when_all_assets_have_data_and_converts_currency():
    days = pd.bdate_range("2024-01-01", "2024-06-30")
    a = pd.Series(100.0, index=days)
    b = pd.Series(10.0, index=days).where(days >= "2024-03-01")  # 3월부터 상장
    prices = pd.DataFrame({"A": a, "B": b})
    res = backtest.run(prices, {"A": 0.5, "B": 0.5})
    assert res.values.index[0] == pd.Timestamp("2024-03-31")
    fx = pd.Series([1000.0, 1500.0], index=pd.to_datetime(["2024-01-01", "2024-05-01"]))
    krw = backtest.to_krw(prices, ["B"], fx)
    assert krw.loc["2024-04-30", "B"] == 10 * 1000 and krw.loc["2024-05-02", "B"] == 10 * 1500
    assert krw.loc["2024-04-30", "A"] == 100
    with pytest.raises(ValueError):
        backtest.run(prices.loc[:"2024-03-15"], {"A": 1, "B": 1})


def test_shares_include_cash_like_the_40_percent_rule():
    from judge.portfolio import shares

    pos = [Position("한국", "A", "가", 60, 1), Position("한국", "B", "나", 20, 1), Position("한국", "C", "다", 0, 1)]
    assert shares(pos, 20) == {"A": 0.6, "B": 0.2}
    assert shares([], 0) == {}
