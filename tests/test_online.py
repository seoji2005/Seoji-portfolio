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


# ---------------------------------------------------------------- 사전 3·4·8에 쓰는 자료


def test_fred_series_for_sentiment_and_macro():
    from judge import macro, sentiment
    from market import fred

    start = dt.date.today() - dt.timedelta(days=int(365.25 * 6.5))
    raw = {k: fred.fetch(sid, start) for k, sid in {"sp500": "SP500", "vix": "VIXCLS", "baa": "BAA10Y"}.items()}
    for k, rows in raw.items():
        print(k, len(rows), rows[-1])
        assert len(rows) > 1000
    res = sentiment.compute("미국", raw)
    print("미국 심리", res.score, res.band, res.message, [(i["label"], i["latest"], i["last_date"]) for i in res.indicators])
    assert res.score is not None and 0 <= res.score <= 100
    mstart = dt.date.today() - dt.timedelta(days=int(365.25 * 11.5))
    ids = {"sahm": "SAHMREALTIME", "dgs10": "DGS10", "t10y3m": "T10Y3M", "jpy": "DEXJPUS", "exports": "XTEXVA01KRM667N"}
    items = macro.panel({k: fred.fetch(sid, mstart) for k, sid in ids.items()})
    for it in items:
        print(it["label"], it["current"], it["last_date"], it["pct"], it["issues"])
    assert sum(it["current"] is not None for it in items) >= 4


@pytest.mark.skipif(not os.environ.get("ECOS_API_KEY"), reason="ECOS_API_KEY 없음")
def test_ecos_rates():
    from market import ecos

    end = dt.date.today()
    for which in ("aa", "ktb"):
        rows = ecos.fetch(os.environ["ECOS_API_KEY"], which, end - dt.timedelta(days=60), end)
        print(which, len(rows), rows[-3:])
        assert rows and all(v is None or 0 < v < 20 for _, v in rows)


@pytest.mark.skipif(not os.environ.get("SEC_USER_AGENT"), reason="SEC_USER_AGENT 없음")
def test_form4_and_13f_live():
    from market import f13, insider, sec

    ua = os.environ["SEC_USER_AGENT"]
    titles = sec.company_titles(ua)
    for t in ("AAPL", "JPM"):
        cik, title = titles[t]
        s = insider.fetch(cik, ua)
        print(t, title, "확인", [(p.date, p.owner, p.shares, p.evidence[:80]) for p in s.confirmed],
              "미확인", len(s.unconfirmed), "10b5-1 제외", len(s.excluded))
    period, rows = f13.latest_13f(1067983, ua)  # 버크셔 해서웨이
    print("13F", period, len(rows), sorted(((r.value, r.issuer) for r in rows), reverse=True)[:5])
    assert period and len(rows) > 10
    w, matched = f13.weight_of(rows, titles["AAPL"][1])
    print("AAPL in Berkshire 13F", w, matched)
