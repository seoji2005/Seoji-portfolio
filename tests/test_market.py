"""자료 계층: SEC·OpenDART 응답 해석과 관심 종목 → 점수 입력 변환. 네트워크 없이 실제 응답 모양의 가짜 자료로."""

import datetime as dt

import pandas as pd
import pytest

from market import dart, sec
from market.models import Profile, Quote
from market.pool import Entry, collect, financial_flag, momentum_prices, score, to_stock
from market.sample import SampleProvider

D = dt.date


# ---------------------------------------------------------------- SEC


def fact(start, end, val, form="10-Q", filed="2026-08-01"):
    row = {"end": end, "val": val, "form": form, "filed": filed}
    if start:
        row["start"] = start
    return row


def facts(**tags):
    return {"facts": {"us-gaap": {t: {"units": {"USD": rows}} for t, rows in tags.items()}}}


SEC_FACTS = facts(
    StockholdersEquity=[fact(None, "2025-09-27", 600, "10-K", "2025-11-01"), fact(None, "2026-06-27", 650)],
    LiabilitiesAndStockholdersEquity=[fact(None, "2026-06-27", 2000)],
    RevenueFromContractWithCustomerExcludingAssessedTax=[
        fact("2024-09-29", "2025-09-27", 400, "10-K", "2025-11-01"),
        fact("2025-09-28", "2026-06-27", 330),  # 올해 9개월 누적
        fact("2026-03-29", "2026-06-27", 100),  # 3개월(쓰지 않음)
        fact("2024-09-29", "2025-06-28", 290, "10-Q", "2025-08-01"),
        fact("2024-09-29", "2025-06-28", 300, "10-Q", "2026-08-01"),  # 같은 기간을 나중에 고쳐 실음 → 이 값
        fact("2021-09-26", "2022-09-24", 350, "10-K", "2022-11-01"),
        fact("2022-09-25", "2023-07-01", 270, "10-Q", "2023-08-01"),
        fact("2021-09-26", "2022-06-25", 260, "10-Q", "2022-08-01"),
        fact("2025-09-28", "2026-06-27", 999, "8-K"),  # 10-K·10-Q가 아니면 무시
    ],
    OperatingIncomeLoss=[
        fact("2024-09-29", "2025-09-27", 120, "10-K", "2025-11-01"),
        fact("2025-09-28", "2026-06-27", 100),
        fact("2024-09-29", "2025-06-28", 90),
    ],
    NetIncomeLoss=[
        fact("2024-09-29", "2025-09-27", 100, "10-K", "2025-11-01"),
        fact("2025-09-28", "2026-06-27", 80),
        fact("2024-09-29", "2025-06-28", 75),
    ],
    LongTermDebtCurrent=[fact(None, "2026-06-27", 20)],
    LongTermDebtNoncurrent=[fact(None, "2026-06-27", 180)],
    CommercialPaper=[fact(None, "2026-06-27", 10)],
    CashAndCashEquivalentsAtCarryingValue=[fact(None, "2026-06-27", 50)],
    MarketableSecuritiesCurrent=[fact(None, "2026-06-27", 30)],
)


def test_sec_ttm_and_balance_sheet():
    f = sec.parse_companyfacts(SEC_FACTS)
    assert f.as_of == D(2026, 6, 27)
    assert f.revenue == 400 + 330 - 300  # 직전 연간 + 올해 누적 − 작년 같은 기간 누적
    assert f.revenue_3y_ago == 350 + 270 - 260
    assert f.op_income == 120 + 100 - 90
    assert f.net_income == 100 + 80 - 75  # ProfitLoss가 없으면 NetIncomeLoss
    assert f.equity == 650
    assert f.liabilities == 2000 - 650  # 부채총계가 없으면 부채와자본총계 − 자본
    assert f.debt == 210 and f.debt_parts == {"유동성장기부채": 20, "장기부채": 180, "기업어음": 10}
    assert f.cash == 80


def test_sec_annual_report_is_ttm():
    f = sec.parse_companyfacts(
        facts(
            StockholdersEquity=[fact(None, "2025-12-31", 10, "10-K")],
            Revenues=[fact("2025-01-01", "2025-12-31", 500, "10-K")],
            ProfitLoss=[fact("2025-01-01", "2025-12-31", 50, "10-K")],
            LongTermDebt=[fact(None, "2025-12-31", 7, "10-K")],
            LongTermDebtNoncurrent=[fact(None, "2025-12-31", 6, "10-K")],
        )
    )
    assert f.revenue == 500 and f.net_income == 50
    assert f.debt_parts == {"장기부채(유동 포함)": 7}  # 합계가 있으면 비유동을 또 더하지 않음
    assert f.revenue_3y_ago is None and "revenue_3y_ago 없음" in f.notes


def test_sec_foreign_filer_has_no_equity():
    f = sec.parse_companyfacts({"facts": {"ifrs-full": {}}})
    assert f.equity is None and "20-F" in f.notes[0]


def test_sec_ticker_lookup():
    f = sec.fetch_fundamentals("ZZZZ", "ua", {"AAPL": 1})
    assert "없음" in f.notes[0]


# ---------------------------------------------------------------- OpenDART


def row(sj, name, cur="", add="", prev_add="", acc_id="-표준계정코드 미사용-", **kw):
    r = {"sj_div": sj, "account_nm": name, "account_id": acc_id, "thstrm_amount": cur, "thstrm_add_amount": add, "frmtrm_add_amount": prev_add}
    r.update(kw)
    return r


LATEST = [  # 2026년 반기보고서
    row("IS", "매출액", "310", "600", "500", "ifrs-full_Revenue"),
    row("IS", "영업이익(손실)", "35", "60", "50"),
    row("CIS", "반기순이익", "25", "45", "40"),  # 손익계산서 없이 포괄손익계산서에만
    row("BS", "자본총계", "1,000"),
    row("BS", "부채총계", "800", acc_id="ifrs-full_Liabilities"),
    row("BS", "현금및현금성자산", "120", acc_id="ifrs-full_CashAndCashEquivalents"),
    row("BS", "단기금융상품", "30"),
    row("BS", "단기 차입금", "50"),
    row("BS", "유동성장기부채", "20"),
    row("BS", "사채", "100"),
    row("BS", "사채할인발행차금", "-1"),  # 포함하지 않음
    row("BS", "장기차입금", "-"),  # 값 없음
    row("CF", "단기차입금의 증가", "10"),  # 현금흐름표는 보지 않음
]
ANNUAL_2025 = [row("IS", "매출액", "1100"), row("IS", "영업이익", "110"), row("IS", "당기순이익", "80")]
OLD_2023_HALF = [row("IS", "수익(매출액)", "", "450", "400")]
OLD_2023_ANNUAL = [row("IS", "수익(매출액)", "900", frmtrm_amount="850")]


def test_dart_half_year_ttm():
    f = dart.parse(2026, dart.HALF, LATEST, ANNUAL_2025, OLD_2023_HALF, OLD_2023_ANNUAL)
    assert f.as_of == D(2026, 6, 30)
    assert f.revenue == 1100 + 600 - 500
    assert f.op_income == 110 + 60 - 50
    assert f.net_income == 80 + 45 - 40
    assert f.revenue_3y_ago == 850 + 450 - 400
    assert (f.equity, f.liabilities) == (1000, 800)
    assert f.debt_parts == {"단기차입금": 50, "유동성장기부채": 20, "사채": 100} and f.debt == 170
    assert f.cash_parts == {"현금및현금성자산": 120, "단기금융상품": 30} and f.cash == 150


def test_dart_first_quarter_and_annual():
    q1 = [row("IS", "매출액", "300", "", "", frmtrm_q_amount="250"), row("BS", "자본총계", "1")]
    assert dart.ttm("revenue", dart.Q1, q1, ANNUAL_2025) == 1100 + 300 - 250
    f = dart.parse(2025, dart.ANNUAL, ANNUAL_2025, old_annual=[row("IS", "매출액", "700")])
    assert f.revenue == 1100 and f.revenue_3y_ago == 700 and f.as_of == D(2025, 12, 31)


def test_dart_num():
    assert dart.num("-1,234") == -1234 and dart.num("") is None and dart.num("-") is None


class FakeDart:
    """OpenDART 흉내: (연도, 보고서, 연결/별도) → 응답."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def get(self, url, params=None, timeout=None):
        key = (int(params["bsns_year"]), params["reprt_code"], params["fs_div"])
        self.calls.append(key)
        rows = self.table.get(key)
        body = {"status": "000", "list": rows} if rows else {"status": "013", "message": "조회된 데이타가 없습니다."}
        return type("R", (), {"json": lambda self: body, "raise_for_status": lambda self: None})()


def test_dart_fetch_finds_latest_report_and_falls_back_to_separate():
    table = {
        (2026, dart.HALF, "OFS"): LATEST,  # 연결이 없는 회사 → 별도
        (2025, dart.ANNUAL, "OFS"): ANNUAL_2025,
        (2023, dart.HALF, "OFS"): OLD_2023_HALF,
        (2023, dart.ANNUAL, "OFS"): OLD_2023_ANNUAL,
    }
    s = FakeDart(table)
    f = dart.fetch_fundamentals("5930", "key", {"005930": "00126380"}, D(2026, 10, 8), s)
    assert f.revenue == 1200 and f.revenue_3y_ago == 900
    assert s.calls[:2] == [(2026, dart.Q3, "CFS"), (2026, dart.Q3, "OFS")]  # 3분기부터 찾음
    early = FakeDart(table)
    dart.fetch_fundamentals("005930", "key", {"005930": "x"}, D(2026, 9, 1), early)
    assert early.calls[0][1] == dart.HALF  # 9월 30일 전에는 3분기를 찾지 않음


def test_dart_error_status_raises():
    class Bad(FakeDart):
        def get(self, url, params=None, timeout=None):
            body = {"status": "020", "message": "요청 제한을 초과하였습니다."}
            return type("R", (), {"json": lambda self: body, "raise_for_status": lambda self: None})()

    with pytest.raises(dart.DartError):
        dart.fetch_fundamentals("005930", "key", {"005930": "x"}, D(2026, 10, 8), Bad({}))


# ---------------------------------------------------------------- 관심 종목 → 점수 입력


def test_momentum_prices_use_last_close_on_or_before():
    idx = pd.bdate_range("2025-09-01", "2026-09-30")
    close = pd.Series(range(len(idx)), index=idx, dtype=float)
    p12, p1, asof = momentum_prices(close)
    assert asof == D(2026, 9, 30)
    assert p12 == close[:"2025-09-30"].iloc[-1] and p1 == close[:"2026-08-30"].iloc[-1]
    assert momentum_prices(close["2026-01-01":])[0] is None  # 12개월치가 없음


def test_financial_flag():
    assert financial_flag(Entry("미국", "JPM"), Profile(industry="Banks - Diversified"))[0]
    assert financial_flag(Entry("미국", "O"), Profile(industry="REIT - Retail"))[0]
    assert not financial_flag(Entry("미국", "V"), Profile(industry="Credit Services"))[0]
    assert not financial_flag(Entry("미국", "JPM", fin="N"), Profile(industry="Banks"))[0]
    assert financial_flag(Entry("한국", "1", fin="y"), Profile())[0]


def test_to_stock_units():
    f = sec.Fundamentals(net_income=2e8, equity=1e9, liabilities=5e8, op_income=3e8, revenue=4e9, revenue_3y_ago=3e9, debt=1e8, cash=2e8)
    s = to_stock(Entry("미국", "X"), False, f, Quote(market_cap=5e9, currency="USD"), pd.Series(dtype=float), False)
    assert (s.net_income, s.market_cap, s.revenue) == (200, 5000, 4000)  # 백만 달러
    k = to_stock(Entry("한국", "1"), True, f, Quote(market_cap=6e11, currency="KRW"), pd.Series(dtype=float), False)
    assert k.market_cap == 6000 and k.held  # 억 원
    assert to_stock(Entry("한국", "1"), False, f, Quote(market_cap=1, currency="USD"), pd.Series(dtype=float), False).market_cap is None


def test_collect_and_score_with_sample_provider():
    entries = [Entry("미국", c) for c in ("AAPL", "MSFT", "NVDA", "JPM")] + [Entry("한국", "005930", "삼성전자"), Entry("한국", "105560", "KB금융")]
    items = collect(SampleProvider(), entries, {("미국", "AAPL")})
    out = score(items)
    us, best = out["미국"]
    assert [d.symbol for d in us] == ["AAPL", "MSFT", "NVDA", "JPM"]
    assert next(d for d in us if d.symbol == "JPM").result.filter_text == "제외: 금융·리츠"
    assert next(d for d in us if d.symbol == "AAPL").held
    assert best is None or not best.held
    kr, _ = out["한국"]
    assert kr[0].symbol == "005930.KS" and kr[0].name == "삼성전자"


def test_collect_tries_kosdaq_when_kospi_empty():
    class OnlyKosdaq(SampleProvider):
        def histories(self, symbols, years=11):
            got = super().histories(symbols, years)
            return {s: (v if s.endswith(".KQ") else v.iloc[0:0]) for s, v in got.items()}

    items = collect(OnlyKosdaq(), [Entry("한국", "247540")], set())
    assert items[0].symbol == "247540.KQ" and not items[0].history.empty


# ---------------------------------------------------------------- 설정 누락·접속 오류


def test_missing_keys_are_reported_without_network(monkeypatch):
    from market.provider import LiveProvider

    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    lp = LiveProvider()
    assert "SEC_USER_AGENT" in lp.fundamentals("미국", "AAPL").notes[0]
    assert "OPENDART_API_KEY" in lp.fundamentals("한국", "005930").notes[0]
    assert "없음" in lp.status()["SEC_USER_AGENT"]


def test_sec_403_explains_the_fix():
    class Forbidden:
        def get(self, url, headers=None, timeout=None):
            return type("R", (), {"status_code": 403, "raise_for_status": lambda self: None})()

    with pytest.raises(PermissionError, match="SEC_USER_AGENT"):
        sec.ticker_map("ua", Forbidden())


def test_data_problem_is_separate_from_filter():
    class NoData(SampleProvider):
        def fundamentals(self, country, code):
            raise PermissionError("SEC가 요청을 거부했습니다(403). SEC_USER_AGENT에 '이름 이메일'을 넣으세요.")

    items = collect(NoData(), [Entry("미국", "AAPL")], set())
    score(items)
    assert "SEC_USER_AGENT" in items[0].data_problem and not items[0].result.scored
    ok = collect(SampleProvider(), [Entry("미국", "AAPL")], set())
    assert ok[0].data_problem == ""
