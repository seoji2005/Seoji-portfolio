"""새 사전(docs/spec.md)의 바뀐 규칙: 7 매수 이유 카드, 6 매도 판단 ②, 4 수출 전년비, 1 12-1 수익률은 배당 미반영 종가."""

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


def test_macro_panel_shows_the_raw_values_it_used():
    """화면의 '계산에 쓴 값'만으로 현재값을 다시 계산할 수 있어야 한다(출처 대조용)."""
    from judge.macro import panel

    exports = [(D(2025, m, 1), 100.0 + m) for m in range(1, 13)] + [(D(2026, 1, 1), 202.0), (D(2026, 2, 1), ".")]
    days = pd.bdate_range("2026-01-02", "2026-04-30").date
    rates = [(d, 4.0 + i / 100) for i, d in enumerate(days)]
    items = {it["key"]: it for it in panel({"exports": exports, "dgs10": rates, "jpy": rates, "sahm": [(D(2026, 3, 1), 0.3)]})}
    ex = items["exports"]
    assert ex["basis"] == [(D(2026, 1, 1), 202.0), (D(2025, 1, 1), 101.0)]
    assert ex["current"] == pytest.approx(202.0 / 101.0 - 1)
    (d, v), (bd, bv) = items["dgs10"]["basis"]
    assert d == days[-1] and bd <= D(2026, 1, 30) and items["dgs10"]["current"] == pytest.approx(v - bv)
    (d, v), (bd, bv) = items["jpy"]["basis"]
    assert items["jpy"]["current"] == pytest.approx(v / bv - 1)
    assert items["sahm"]["basis"] == [(D(2026, 3, 1), 0.3)]
    assert items["t10y3m"]["basis"] == []


def test_momentum_uses_close_without_dividends():
    """사전 1번: 수정종가 = 분할·병합·증자 반영, 현금배당 미반영. 배당까지 반영한 adj_close를 쓰면 안 된다."""
    from market.pool import Entry, collect
    from market.sample import SampleProvider

    items = collect(SampleProvider(), [Entry("미국", "AAPL", "애플")], set(), workers=1)
    h, s = items[0].history, items[0].stock
    assert not h["close"].equals(h["adj_close"])  # 예시 자료는 배당만큼 두 값이 다름
    p12, p1, _ = momentum_prices(h["close"])
    assert (s.price_12m, s.price_1m) == (p12, p1)
    assert (s.price_12m, s.price_1m) != momentum_prices(h["adj_close"])[:2]


# ---------------------------------------------------------------- 1 12-1 수익률: 권리락 보정 미확인 → 결측


def test_rights_issues_that_cause_ex_rights():
    from market import dart

    rows = [
        {"rcept_no": "20260105000123", "ic_mthn": "제3자배정증자"},  # 권리락 없음
        {"rcept_no": "20260210000456", "ic_mthn": "주주배정후 실권주 일반공모"},
        {"rcept_no": "20260301000789", "ic_mthn": ""},  # 방식을 모르면 남긴다
    ]
    got = dart.parse_rights("piicDecsn", "유상증자", rows)
    assert [e.filed for e in got] == [D(2026, 2, 10), D(2026, 3, 1)] and all(e.record_date is None for e in got)
    bonus = dart.parse_rights("fricDecsn", "무상증자", [{"rcept_no": "20260402000001", "nstk_asstd": "2026년 04월 20일"}])
    assert bonus[0].record_date == D(2026, 4, 20) and "신주배정기준일 2026-04-20" in bonus[0].text
    both = dart.parse_rights("pifricDecsn", "유무상증자", [{"rcept_no": "20260402000002", "piic_ic_mthn": "제3자배정", "fric_nstk_asstd": "2026.05.04"}])
    assert both[0].record_date == D(2026, 5, 4)  # 유무상증자는 무상 부분 때문에 항상 권리락


def test_rights_events_reads_all_three_reports_and_reports_errors():
    from market import dart

    class Http:
        def __init__(self, bodies):
            self.bodies, self.urls = bodies, []

        def get(self, url, params=None, timeout=None):
            self.urls.append(url.rsplit("/", 1)[1])
            body = self.bodies.get(self.urls[-1], {"status": "013"})
            return type("R", (), {"json": lambda self: body, "raise_for_status": lambda self: None})()

    http = Http({"fricDecsn.json": {"status": "000", "list": [{"rcept_no": "20260402000001", "nstk_asstd": "2026-04-20"}]}})
    got = dart.rights_events("5930", "key", {"005930": "001"}, D(2025, 3, 1), D(2026, 9, 15), http)
    assert http.urls == ["piicDecsn.json", "fricDecsn.json", "pifricDecsn.json"] and len(got) == 1
    with pytest.raises(dart.DartError):
        dart.rights_events("5930", "key", {"005930": "001"}, D(2025, 3, 1), D(2026, 9, 15), Http({"piicDecsn.json": {"status": "020", "message": "한도 초과"}}))
    with pytest.raises(dart.DartError):
        dart.rights_events("999999", "key", {}, D(2025, 3, 1), D(2026, 9, 15), Http({}))

    class Down:
        def get(self, url, params=None, timeout=None):
            raise ConnectionError(f"{url}?crtfc_key={params['crtfc_key']}")

    with pytest.raises(dart.DartError) as err:
        dart.rights_events("5930", "SECRET123", {"005930": "001"}, D(2025, 3, 1), D(2026, 9, 15), Down())
    assert "SECRET123" not in str(err.value)  # 오류 문구에 인증키가 남지 않음


@pytest.mark.parametrize(
    "record,filed,blocked",
    [
        (D(2026, 4, 20), D(2026, 4, 2), True),  # 기준일이 12-1 구간 안
        (D(2025, 9, 30), D(2025, 9, 1), False),  # 12개월 전 날짜 이전 → 두 가격 모두 권리락 뒤
        (D(2025, 10, 1), D(2025, 9, 1), True),  # 12개월 전 날짜 바로 뒤
        (D(2026, 9, 7), D(2026, 8, 20), True),  # 1개월 전 날짜 + 7일 안(권리락이 그 전 영업일일 수 있음)
        (D(2026, 9, 20), D(2026, 8, 20), False),  # 구간 뒤
        (None, D(2026, 5, 1), True),  # 기준일 모름, 구간 안 공시
        (None, D(2025, 5, 1), True),  # 기준일 모름, 공시 뒤 6개월 안에 구간 시작
        (None, D(2025, 3, 31), False),  # 공시 뒤 6개월이 구간 시작 전에 끝남
        (None, D(2026, 9, 5), False),  # 1개월 전 날짜 뒤 공시 → 권리락도 그 뒤
    ],
)
def test_rights_block_window(record, filed, blocked):
    from market.dart import RightsEvent
    from market.pool import rights_block

    d12, d1 = D(2025, 9, 30), D(2026, 8, 31)
    e = RightsEvent("무상증자" if record else "유상증자", filed, record, "" if record else "주주배정", "x")
    assert bool(rights_block([e], d12, d1)) is blocked


def test_ex_rights_in_window_makes_12_1_missing_and_excludes_from_pool():
    from market.dart import DartError, RightsEvent
    from market.pool import Entry, collect, score
    from market.sample import SampleProvider

    class WithRights(SampleProvider):
        def __init__(self, events=None, error=None):
            self.events, self.error, self.calls = events or {}, error, []

        def rights_events(self, code, start, end):
            self.calls.append((code, start, end))
            if self.error:
                raise self.error
            return self.events.get(code, [])

    entries = [Entry("한국", c) for c in ("005930", "000660", "005380")] + [Entry("미국", "AAPL")]
    event = RightsEvent("무상증자", D(2026, 1, 5), None, "", "20260105000001")
    prov = WithRights({"000660": [event]})
    items = {d.entry.code: d for d in collect(prov, entries, set(), workers=1)}
    score(list(items.values()))
    hynix = items["000660"]
    assert "권리락 보정 미확인" in hynix.mom_block and "20260105000001" in hynix.mom_block
    assert hynix.result.metrics["mom"] is None and "12-1 수익률" in hynix.result.missing and not hynix.result.scored
    assert items["005930"].mom_block == "" and items["005930"].result.metrics["mom"] is not None
    assert {c for c, *_ in prov.calls} == {"005930", "000660", "005380"}  # 미국 종목은 권리락을 보지 않음
    from market.pool import momentum_points, rights_window

    (d12, _), (d1, _), _ = momentum_points(items["005930"].history["close"])
    assert ("005930", *rights_window(d12, d1)) in prov.calls  # 12개월 전 날짜 6개월 전 ~ 1개월 전 날짜 + 7일
    failed = collect(WithRights(error=DartError("OpenDART 인증키 없음")), entries[:1], set(), workers=1)[0]
    assert "확인하지 못함" in failed.mom_block and failed.stock.price_12m is None


# ---------------------------------------------------------------- 실제 자료 점검의 손계산이 맞는 잣대인지


@pytest.mark.parametrize(
    "rows",
    [
        [(0.2, 0.1, 0.05, 0.3)],  # 한 종목뿐 → 50
        [(0.2, 0.1, 0.05, 0.3), (0.1, 0.2, 0.04, 0.1)],
        [(0.2, 0.1, 0.05, 0.3), (0.2, 0.1, 0.05, 0.3), (0.1, 0.0, 0.01, -0.2)],  # 맨 위 동점 → 최고점이 100이 아님
        [(0.1, 0.1, 0.05, 0.1)] * 4,  # 모두 같음 → 모두 50
    ],
)
def test_online_hand_calculation_matches_the_program_on_ties_and_small_pools(rows):
    from types import SimpleNamespace

    from judge.stocks import Stock, evaluate_pool
    from tests.test_online import hand_scores

    stocks = []
    for i, (roe, growth, ey, mom) in enumerate(rows):
        stocks.append(Stock(code=f"S{i}", net_income=roe * 1000, equity=1000, liabilities=500, op_income=ey * 10000,
                            revenue=1000 * (1 + growth) ** 3, revenue_3y_ago=1000, market_cap=10000, debt=0, cash=0,
                            price_12m=100, price_1m=100 * (1 + mom)))
    results, _ = evaluate_pool(stocks, "미국")
    group = [SimpleNamespace(entry=SimpleNamespace(code=s.code), stock=s) for s in stocks]
    _, pcts, avg, final = hand_scores(group, "미국")
    for r in results:
        assert r.score == pytest.approx(final[r.stock.code], abs=0.05)
        assert r.avg == pytest.approx(avg[r.stock.code], abs=5e-7)
    if len(rows) == 3:
        assert max(r.score for r in results) == 75.0  # 동점 둘이 1·2위 평균 → (2.5 − 1) ÷ 2 × 100
