"""실제 API 점검. 인터넷이 되는 곳(GitHub Actions의 '실제 자료 점검')에서만 돈다: ONLINE=1 python -m pytest tests/test_online.py -s

값을 출력해 두므로 실행 기록에서 숫자가 그럴듯한지 눈으로도 확인할 수 있다.
"""

import datetime as dt
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("ONLINE") != "1", reason="ONLINE=1일 때만(실제 API 호출)")

RECENT = dt.date.today() - dt.timedelta(days=200)


def show(label, f):
    print(f"\n[{label}] {f.source} as_of={f.as_of}")
    for k in ("revenue", "revenue_3y_ago", "op_income", "net_income", "equity", "liabilities", "debt", "cash"):
        print(f"  {k:15s} {getattr(f, k)}")
    print("  debt_parts", f.debt_parts, "\n  cash_parts", f.cash_parts, "\n  notes", f.notes)


def test_yahoo_prices_quotes_profile():
    from market import yahoo

    h = yahoo.histories(["AAPL", "005930.KS", "SPY", "069500.KS", "KRW=X"], 3)
    for s, df in h.items():
        print(s, len(df), df.index.min().date() if len(df) else None, df.index.max().date() if len(df) else None, df.tail(1).to_dict("records"))
        assert len(df) > 500 and (df["close"] > 0).all(), s
        assert df.index.max().date() > dt.date.today() - dt.timedelta(days=10), s
    q = yahoo.quote("AAPL")
    print("AAPL", q)
    assert q.price > 0 and q.market_cap > 1e11 and q.currency == "USD"
    k = yahoo.quote("005930.KS")
    print("005930.KS", k)
    assert k.price > 0 and k.currency == "KRW" and k.market_cap > 1e13
    p = yahoo.profile("JPM")
    print("JPM", p)
    assert "Bank" in p.industry


@pytest.mark.skipif(not os.environ.get("SEC_USER_AGENT"), reason="SEC_USER_AGENT 없음")
@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA"])
def test_sec_fundamentals(ticker):
    from market import sec
    from market.provider import LiveProvider

    lp = LiveProvider()
    f = sec.fetch_fundamentals(ticker, lp.sec_ua, lp._maps("미국"))
    show(ticker, f)
    assert f.as_of and f.as_of > RECENT
    assert f.revenue > 1e10 and f.revenue_3y_ago > 1e9
    assert f.op_income > 0 and f.net_income > 0
    assert f.equity > 0 and f.liabilities > 0 and f.cash > 0


@pytest.mark.skipif(not os.environ.get("OPENDART_API_KEY"), reason="OPENDART_API_KEY 없음")
@pytest.mark.parametrize("code", ["005930", "000660", "005380"])
def test_dart_fundamentals(code):
    from market.provider import LiveProvider

    f = LiveProvider().fundamentals("한국", code)
    show(code, f)
    assert f.as_of and f.as_of > RECENT
    assert f.revenue > 1e12 and f.revenue_3y_ago > 1e12
    assert f.equity > 0 and f.liabilities > 0 and f.cash > 0
    assert f.op_income is not None and f.net_income is not None


def test_full_pool_live():
    from market.pool import Entry, collect, score
    from market.provider import LiveProvider

    entries = [Entry("미국", c) for c in ("AAPL", "MSFT", "NVDA", "JPM", "COST")]
    if os.environ.get("OPENDART_API_KEY"):
        entries += [Entry("한국", c) for c in ("005930", "000660", "005380")]
    out = score(collect(LiveProvider(), entries, {("미국", "AAPL")}))
    for country, (group, best) in out.items():
        for d in group:
            r = d.result
            print(country, d.symbol, d.name, r.score, r.decision, "|", r.summary, "|", d.fin_reason, d.notes)
    us, _ = out["미국"]
    if not os.environ.get("SEC_USER_AGENT"):
        assert all("SEC_USER_AGENT" in d.data_problem for d in us)  # 원인을 알려 줌
        return
    assert sum(d.result.scored for d in us) >= 3
    assert next(d for d in us if d.symbol == "JPM").result.filter_reasons == ["금융·리츠"]
