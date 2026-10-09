"""판단 기준(judge)을 손으로 계산한 값과 대조한다."""

import datetime as dt

import pytest

from builder import example
from judge.common import add_months, band, excel_round, percentile, top_share
from builder.v1_holdings import BuyPlan, Reason, earnings_check, evaluate_holdings, plan_purchase, record_status  # 이전 명세(시트)
from builder.v1_macro import panel, transform  # 이전 명세(시트)
from judge.sentiment import compute
from judge.stocks import Stock, evaluate_pool, filter_reasons, metrics

D = dt.date


# ---------------------------------------------------------------- 공통


def test_percentile_mid_rank_and_single():
    assert percentile(1, [1, 2, 3]) == 0
    assert percentile(3, [1, 2, 3]) == 100
    assert percentile(2, [1, 2, 2, 3]) == 50  # 동점은 평균 순위 2.5 → (2.5-1)/3
    assert percentile(7, [7]) == 50
    assert top_share(3, [1, 2, 3]) == pytest.approx(100 / 3)


def test_excel_round_half_away_from_zero():
    assert excel_round(56.25, 1) == 56.3
    assert excel_round(2.675, 2) == 2.68
    assert excel_round(-0.5, 0) == -1


def test_add_months_matches_edate():
    assert add_months(D(2024, 3, 31), -1) == D(2024, 2, 29)
    assert add_months(D(2026, 9, 30), -60) == D(2021, 9, 30)


@pytest.mark.parametrize(
    "score,expected",
    [(0, "극단 공포"), (9.9, "극단 공포"), (10, "공포"), (29.9, "공포"), (30, "중립"), (70, "탐욕"), (89.9, "탐욕"), (90, "극단 탐욕"), (100, "극단 탐욕")],
)
def test_band_boundaries(score, expected):
    assert band(score)[0] == expected


def test_band_actions():
    assert band(5)[1:] == (1, 0)
    assert band(20)[1:] == (2, 2)
    assert band(50)[1:] == (2, 4)
    assert band(80)[1:] == (3, 4)
    assert band(95)[1:] == (4, 4)


# ---------------------------------------------------------------- 1·2. 종목


def ok_stock(**kw):
    base = dict(code="X", net_income=10, equity=100, liabilities=100, op_income=20, revenue=200, revenue_3y_ago=100,
                market_cap=6000, debt=50, cash=30, price_12m=100, price_1m=120)
    base.update(kw)
    return Stock(**base)


def test_filter_reasons():
    assert filter_reasons(ok_stock(), "한국") == []
    assert filter_reasons(ok_stock(op_income=0), "한국") == ["영업적자"]
    assert filter_reasons(ok_stock(liabilities=200), "한국") == []  # 200%는 통과
    assert filter_reasons(ok_stock(liabilities=201), "한국") == ["부채비율 초과"]
    assert filter_reasons(ok_stock(equity=-1), "한국") == ["자본잠식"]
    assert filter_reasons(ok_stock(market_cap=4999), "한국") == ["시총 미달"]
    assert filter_reasons(ok_stock(market_cap=1999), "미국") == ["시총 미달"]
    assert filter_reasons(ok_stock(market_cap=None, op_income=None), "미국") == ["영업이익 없음", "시총 없음"]
    assert filter_reasons(ok_stock(excluded_sector=True), "한국") == ["금융·리츠"]


def test_metrics_formulas():
    m = metrics(ok_stock())
    assert m["roe"] == pytest.approx(0.10)
    assert m["growth"] == pytest.approx(2 ** (1 / 3) - 1)
    assert m["ey"] == pytest.approx(20 / (6000 + 50 - 30))
    assert m["mom"] == pytest.approx(0.20)
    assert metrics(ok_stock(revenue_3y_ago=0))["growth"] is None
    assert metrics(ok_stock(market_cap=10, debt=0, cash=20))["ey"] is None  # 기업가치 0 이하
    assert metrics(ok_stock(debt=None))["ey"] is None


def scores(country):
    stocks = example.KR if country == "한국" else example.US
    results, best = evaluate_pool(stocks, country)
    return {r.stock.code: r.score for r in results}, best


def test_example_scores_by_hand():
    # 지표별 순위 합(0부터): K02 1, K08 7, K12 9, K10 14, K11 14, K01 19, K07 20 → 순위를 다시 백분위로
    kr, best = scores("한국")
    assert kr == {
        "K01": 83.3, "K02": 0, "K03": None, "K04": None, "K05": None, "K06": None, "K07": 100,
        "K08": 16.7, "K09": None, "K10": 58.3, "K11": 58.3, "K12": 33.3,
    }
    assert best.stock.code == "K07"
    us, best = scores("미국")
    assert {k: v for k, v in us.items() if v is not None} == {"U01": 100, "U02": 0, "U03": 80, "U05": 20, "U06": 60, "U08": 40}
    assert best.stock.code == "U03"


def test_decisions_and_summary():
    results, _ = evaluate_pool(example.KR, "한국")
    by = {r.stock.code: r for r in results}
    assert by["K02"].decision == "교체 제안 → 예시소프트 (100.0)"
    assert by["K01"].decision == "보유 유지"
    assert by["K07"].decision == "편입 후보"
    assert by["K10"].decision == ""
    assert by["K07"].summary == "수익성 높음, 성장 빠름, 추세 좋음. 보통: 가격"
    assert by["K09"].status == "점수 없음(결측: 12-1 수익률)"
    assert by["K04"].filter_text == "제외: 금융·리츠, 부채비율 초과"
    assert by["K01"].cards["roe"] == "15.0% · 상위 29%"


def test_replace_needs_gap_of_ten():
    # 지표 4개가 모두 같은 순서인 11종목: 점수 0, 10, …, 100. 보유(40점)보다 10점 이상 높은 후보가 있다.
    pool = [ok_stock(code=str(i), name=str(i), net_income=i, revenue=100 + i, op_income=20 + i, price_1m=100 + i) for i in range(11)]
    pool[4].held = True
    results, best = evaluate_pool(pool, "한국")
    held = next(r for r in results if r.stock.held)
    assert held.score == 40 and best.score == 100
    assert held.decision.startswith("교체 제안")


# ---------------------------------------------------------------- 5·6·7. 보유, 매도, 매수 이유


def test_record_status():
    full = [Reason("A", 1, "x", True, "e", "b")]
    assert record_status("A", full) == "기록 완료"
    assert record_status("B", full) == "기록 없음"
    assert record_status("A", [Reason("A", 1, "x", False, "e", "b")]) == "핵심 1개 표시 필요"
    assert record_status("A", [Reason("A", 1, "x", True, "e", "")]) == "근거·기준 미기재"
    assert record_status("A", [Reason("A", i, "x", i == 1, "e", "b") for i in range(1, 5)]) == "이유 3개 초과"


def test_earnings_check():
    rs = [Reason("A", 1, "x", True, "e", "b", D(2026, 8, 1)), Reason("A", 2, "y", False, "e", "b", None)]
    assert earnings_check("A", rs, None) == ""
    assert earnings_check("A", rs[:1], D(2026, 7, 30)) == "점검 완료"
    assert earnings_check("A", rs[:1], D(2026, 8, 2)) == "점검 필요"
    assert earnings_check("A", rs, D(2026, 7, 30)) == "점검 필요"  # 점검일 없는 이유


def test_example_holdings_by_hand():
    pools = {c: evaluate_pool(example.KR if c == "한국" else example.US, c) for c in ("한국", "미국")}
    out = {r.holding.code: r for r in evaluate_holdings(example.ACCOUNT, example.HOLDINGS, example.REASONS, pools)}
    # 개별 몫 = 28,152,000 + 12,200,000 + 7,500,000 + 5,313,000 + 대기 현금 7,000,000 = 60,165,000
    assert out["U01"].value_krw == 28_152_000
    assert out["U01"].weight == pytest.approx(28_152_000 / 60_165_000)
    assert out["U01"].action == "③ 비중 초과 → 초과분 4,086,000원 매도"
    assert out["K01"].action == "② 핵심 매수 이유 붕괴 → 매도 검토"
    assert out["K02"].action == "④ 교체 제안 → 예시소프트"
    assert out["U02"].price_change == pytest.approx(55 / 80 - 1)
    assert out["U02"].action == "① 손실 한도 도달 → 매도"  # 교체 조건도 맞지만 ①이 먼저
    assert out["U02"].replace_hit
    assert out["U01"].earnings == "점검 필요"


def test_loss_limit_account_rule():
    acc = example.Account(total_krw=100_000_000, cash_krw=0, usdkrw=1)
    h = example.Holding("한국", "Z", "z", qty=10, avg_price=100_000, cost_krw=3_000_000, price=99_000)
    r = evaluate_holdings(acc, [h], [], {})[0]
    assert r.loss_krw == 2_010_000 and r.loss_hit  # 2.01% ≥ 2%
    h.cost_krw = 2_980_000
    assert not evaluate_holdings(acc, [h], [], {})[0].loss_hit  # 1.99%


def test_concentration_needs_three_holdings():
    acc = example.Account(total_krw=100, cash_krw=0, usdkrw=1)
    two = [example.Holding("한국", c, c, 1, 1, 1, p) for c, p in (("A", 90), ("B", 10))]
    assert not any(r.conc_hit for r in evaluate_holdings(acc, two, [], {}))
    three = two + [example.Holding("한국", "C", "C", 1, 1, 1, 10)]
    assert [r.conc_hit for r in evaluate_holdings(acc, three, [], {})] == [True, False, False]


def test_plan_purchase():
    p = BuyPlan("한국", "A", "a", 9_000_000, D(2026, 10, 12))
    out = plan_purchase(p, 80, 75, "기록 완료")
    assert out["advice"] == "3회, 4주 간격, 1회 3,000,000원"
    assert out["dates"] == [D(2026, 10, 12), D(2026, 11, 9), D(2026, 12, 7)]
    assert plan_purchase(p, 5, 75, "기록 완료")["advice"] == "1회에 전부, 9,000,000원"
    assert plan_purchase(p, 50, 60, "기록 완료")["advice"].endswith("주의: 편입 후보 아님")
    no = plan_purchase(p, 50, 75, "기록 없음")
    assert no["advice"] == "매수하지 않음: 매수 이유 기록 없음"
    assert no["each"] is None and no["dates"] == [] and no["band"] == "중립"


# ---------------------------------------------------------------- 3. 시장 심리


def _us_raw(shape):
    """1,600거래일. shape='fear'면 마지막 날 지수 급락·VIX 최고·금리차 최고."""
    days, d = [], D(2020, 1, 1)
    while len(days) < 1600:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    n = len(days)
    sp = [3000 + (i % 7) for i in range(n)]
    vix = [15 + (i % 5) * 0.1 for i in range(n)]
    baa = [2 + (i % 3) * 0.01 for i in range(n)]
    if shape == "fear":
        sp[-1], vix[-1], baa[-1] = 2000, 80, 6
    else:
        sp[-1], vix[-1], baa[-1] = 4000, 9, 1
    return {"sp500": list(zip(days, sp)), "vix": list(zip(days, vix)), "baa": list(zip(days, baa))}


def test_sentiment_extremes():
    fear = compute("미국", _us_raw("fear"))
    assert fear.score == 0 and fear.band == "극단 공포" and (fear.times, fear.weeks) == (1, 0)
    greed = compute("미국", _us_raw("greed"))
    assert greed.score == 100 and greed.band == "극단 탐욕"
    assert greed.message == "이상 없음"


def test_sentiment_warns_on_stale_and_short_data():
    raw = _us_raw("greed")
    raw["vix"] = raw["vix"][:-10]  # VIX가 2주 늦음
    raw["baa"] = raw["baa"][-300:]  # 금리차는 1년 남짓
    res = compute("미국", raw)
    assert "VIX 자료 지연" in res.message
    assert "Baa − 미 10년물 5년 자료 부족" in res.message


def test_sentiment_forward_fills_and_accepts_any_order():
    raw = _us_raw("greed")
    gap = raw["vix"][-5][0]
    raw["vix"] = [(d, "." if d == gap else v) for d, v in reversed(raw["vix"])]
    res = compute("미국", raw)
    rows = {r["date"]: r for r in res.rows}
    prev = res.rows[[r["date"] for r in res.rows].index(gap) - 1]
    assert rows[gap]["vix"] == prev["vix"]


# ---------------------------------------------------------------- 4. 거시


def test_macro_transforms():
    days = [D(2026, 1, 2), D(2026, 2, 2), D(2026, 4, 2), D(2026, 4, 3)]
    diff = transform("diff", list(zip(days, [4.0, ".", 4.5, 4.6])))
    assert diff[2][1] == pytest.approx(0.5)  # 4/2의 3개월 전 = 1/2 값 4.0
    assert diff[1][1] is None
    ratio = transform("ratio", list(zip(days, [100.0, 101.0, 110.0, 99.0])))
    assert ratio[3][1] == pytest.approx(99 / 100 - 1)
    months = [D(2025, m, 1) for m in range(1, 13)] + [D(2026, m, 1) for m in range(1, 4)]
    vals = [10.0] * 12 + [11.0, 12.0, 13.0]
    yoy = transform("yoy3", list(zip(months, vals)))
    assert yoy[-1][1] == pytest.approx(36 / 30 - 1)
    assert yoy[-2][1] is None  # 1년 전 3개월이 다 있지 않음(2024-12 없음)


def test_macro_panel_flags():
    out = {p["key"]: p for p in panel({"sahm": [(D(2026, 1, 1), 0.2), (D(2025, 12, 1), 0.1)]})}
    assert out["sahm"]["issues"] == "날짜 정렬 오류, 10년 자료 부족"
    assert out["dgs10"]["issues"] == "자료 없음"
