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


BIG = {"미국": ("AAPL", "MSFT", "NVDA"), "한국": ("005930", "000660", "005380")}  # 4지표가 반드시 나와야 하는 대형주
NEEDS = {"미국": "SEC_USER_AGENT", "한국": "OPENDART_API_KEY"}
MCAP_MIN = {"한국": 5000, "미국": 2000}  # 사전 2번: 5천억 원(억 원 단위), 20억 달러(백만 달러 단위)
_POOL = {}


def pct(v):
    return "–" if v is None else f"{v:+.1%}"


def num(v, digits=0):
    return "–" if v is None else f"{v:,.{digits}f}"


def summary(text):
    """GitHub Actions 실행 결과 화면(Summary)에도 남긴다. 비밀값이 섞여 있으면 가린다."""
    for k in ("OPENDART_API_KEY", "SEC_USER_AGENT", "ECOS_API_KEY"):
        if os.environ.get(k):
            text = text.replace(os.environ[k], "***")
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


# ---- 손계산: 프로그램(judge/)을 쓰지 않고 사전 1·2번 문장 그대로 다시 계산한다


def hand_metrics(s):
    roe = s.net_income / s.equity if None not in (s.net_income, s.equity) and s.equity > 0 else None
    growth = None
    if None not in (s.revenue, s.revenue_3y_ago) and s.revenue > 0 and s.revenue_3y_ago > 0:
        growth = (s.revenue / s.revenue_3y_ago) ** (1 / 3) - 1
    ey = None
    if None not in (s.op_income, s.market_cap, s.debt, s.cash) and s.market_cap + s.debt - s.cash > 0:
        ey = s.op_income / (s.market_cap + s.debt - s.cash)
    mom = s.price_1m / s.price_12m - 1 if None not in (s.price_1m, s.price_12m) and s.price_12m > 0 and s.price_1m > 0 else None
    return {"roe": roe, "growth": growth, "ey": ey, "mom": mom}


def hand_passes(s, country):
    return (s.op_income is not None and s.op_income > 0
            and s.equity is not None and s.equity > 0 and s.liabilities is not None and s.liabilities / s.equity <= 2.0
            and s.market_cap is not None and s.market_cap >= MCAP_MIN[country] and not s.excluded_sector)


def hand_pct(x, vals):
    """작은 값부터 1, 2, 3… 순위를 매기고 같은 값은 순위 평균. (순위 − 1) ÷ (개수 − 1) × 100, 하나뿐이면 50."""
    if len(vals) == 1:
        return 50.0
    ranks = [i + 1 for i, v in enumerate(sorted(vals)) if v == x]
    return (sum(ranks) / len(ranks) - 1) / (len(vals) - 1) * 100


def hand_scores(group, country):
    m = {d.entry.code: hand_metrics(d.stock) for d in group}
    pool = [d.entry.code for d in group if hand_passes(d.stock, country) and None not in m[d.entry.code].values()]
    pcts = {c: {k: hand_pct(m[c][k], [m[q][k] for q in pool]) for k in m[c]} for c in pool}
    avg = {c: round(sum(pcts[c].values()) / 4, 6) for c in pool}  # 평균은 소수 6자리에서 동점 판단(시트와 같음)
    final = {c: hand_pct(avg[c], list(avg.values())) for c in pool}
    return m, pcts, avg, final


def live_pool():
    """관심 종목 목록 전체를 실제 자료로 한 번만 모은다(두 나라 검사가 같이 씀)."""
    if not _POOL:
        import pandas as pd

        from market.pool import Entry, collect, score
        from market.provider import LiveProvider

        wl = pd.read_csv("my/watchlist.csv", dtype=str).fillna("")
        entries = [Entry(r.country, r.code, r.name, r.market, r.fin) for r in wl.itertuples()]
        _POOL.update(score(collect(LiveProvider(), entries, set())))
    return _POOL


@pytest.mark.parametrize("country", ["미국", "한국"])
def test_watchlist_scores_live(country):
    """종목 점수의 실제 자료 검증. 결과는 셋 중 하나: 검증 미실행(설정 없음) / 검증 실패(수집·계산 문제) / 검증 통과."""
    key = NEEDS[country]
    if not os.environ.get(key):
        summary(f"## {country} 종목 점수 — 검증 미실행\n\n{key}가 설정되지 않아 재무를 받지 않았습니다. 이 검사가 통과로 끝나도 종목 점수가 실제 자료로 검증된 것은 아닙니다.\n")
        print(f"\n::warning title=종목 점수 검증 미실행({country})::{key}가 없어 실제 재무로 4지표·최종 점수를 확인하지 않았습니다")
        pytest.skip(f"검증 미실행: {key} 없음")

    group, _ = live_pool()[country]
    m, pcts, avg, final = hand_scores(group, country)
    problems = [f"{d.name}: 재무 수집 실패({d.data_problem})" for d in group if d.data_problem]
    problems += [f"{d.name}: {d.mom_block}" for d in group if "확인하지 못함" in d.mom_block]
    for d in group:
        r, c = d.result, d.entry.code
        if c in BIG[country] and None in r.metrics.values():
            problems.append(f"{d.name}: 대형주인데 4지표 중 결측 {r.missing} {d.mom_block}")
        if r.scored != (c in final):
            problems.append(f"{d.name}: 채점 여부가 손계산과 다름(프로그램 {r.scored}, 손계산 {c in final})")
        for k, v in m[c].items():
            if (v is None) != (r.metrics[k] is None) or (v is not None and abs(v - r.metrics[k]) > 1e-12):
                problems.append(f"{d.name}: {k} 지표 값이 손계산과 다름({r.metrics[k]} vs {v})")
        if c in final:
            if any(abs(pcts[c][k] - r.pct[k]) > 1e-9 for k in pcts[c]) or abs(avg[c] - r.avg) > 5e-7 or abs(final[c] - r.score) > 0.05 + 1e-9:
                problems.append(f"{d.name}: 백분위·점수가 손계산과 다름(프로그램 {r.score}, 손계산 {final[c]:.4f})")

    verdict = "검증 실패" if problems else "검증 통과"
    summary(f"## {country} 종목 점수 — {verdict} ({dt.date.today()})\n")
    summary("\n".join(f"- {x}" for x in problems) + "\n" if problems else "재무 수집, 4지표 계산, 손계산 대조(지표 값·지표별 백분위·평균·최종 점수)가 모두 맞습니다.\n")
    unit = "억 원" if country == "한국" else "백만 달러"
    summary(f"### 대형주 손계산 입력 ({unit}, 주가는 현지 통화)\n")
    summary("| 종목 | 재무 출처(기준일) | 순이익 | 자본 | 부채 | 영업이익 | 매출 | 3년 전 매출 | 시총 | 이자부부채 | 현금성 | 12개월 전 주가 | 1개월 전 주가 |\n" + "|---" * 13 + "|")
    for d in group:
        if d.entry.code in BIG[country]:
            s, f = d.stock, d.fundamentals
            summary(f"| {d.name} | {f.source} {f.as_of} | {num(s.net_income)} | {num(s.equity)} | {num(s.liabilities)} | {num(s.op_income)} | {num(s.revenue)} | "
                    f"{num(s.revenue_3y_ago)} | {num(s.market_cap)} | {num(s.debt)} | {num(s.cash)} | {num(s.price_12m, 2)} | {num(s.price_1m, 2)} |")
    summary("\n### 관심 종목 전체\n")
    summary("| 종목 | ROE | 매출 3년 성장 | 이익수익률 | 12-1 | 거름망 | 백분위(ROE·성장·이익·12-1) | 점수 | 손계산 |\n|---|---|---|---|---|---|---|---|---|")
    for d in sorted(group, key=lambda d: -(d.result.score if d.result.score is not None else -1)):
        r, c, mm = d.result, d.entry.code, d.result.metrics
        if d.data_problem:  # 재무를 못 받은 것을 거름망 탈락처럼 보이지 않게
            flt, sc = f"판단 불가(재무 없음: {d.data_problem})", "없음"
        else:
            flt, sc = r.filter_text, f"{r.score:.1f}" if r.score is not None else r.status + (f" — {d.mom_block}" if d.mom_block else "")
        ps = "·".join(f"{r.pct[k]:.1f}" for k in ("roe", "growth", "ey", "mom")) if r.scored else "–"
        hand = f"{final[c]:.2f}" if c in final else "채점 안 함"
        summary(f"| {d.name} | {pct(mm['roe'])} | {pct(mm['growth'])} | {pct(mm['ey'])} | {pct(mm['mom'])} | {flt} | {ps} | {sc} | {hand} |")
        if d.fundamentals.notes or d.notes:
            print("   ", d.symbol, d.fundamentals.notes + d.notes)
    summary(f"\n채점 {len(final)} / {len(group)}\n")
    if problems:
        print(f"\n::error title=종목 점수 검증 실패({country})::" + " / ".join(problems)[:900])
    assert not problems, problems


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
        print(it["label"], it["current"], it["last_date"], it["pct"], it["issues"], "계산에 쓴 값", it["basis"])
    assert sum(it["current"] is not None for it in items) >= 4
    ex = next(it for it in items if it["key"] == "exports")
    (d, v), (bd, bv) = ex["basis"]
    summary(f"## 한국 수출 전년비 대조용 ({dt.date.today()} 조회)\n\n"
            f"- 시리즈: FRED XTEXVA01KRM667N ({fred_meta('XTEXVA01KRM667N')})\n"
            f"- {d:%Y-%m}: {v:,.0f}\n- {bd:%Y-%m}: {bv:,.0f}\n- 전년비: {v / bv - 1:.4%}\n")


def fred_meta(sid):
    """FRED 시리즈 화면의 단위·갱신일(대조 기록용). 못 읽으면 그렇다고 적는다."""
    import re

    import requests

    try:
        page = requests.get(f"https://fred.stlouisfed.org/series/{sid}", timeout=30).text
    except Exception as ex:  # noqa: BLE001
        return f"설명 화면 못 읽음: {ex}"
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))
    found = [m.group(0).strip() for k in ("Units:", "Frequency:", "Updated:") for m in [re.search(k + r"[^:]{0,80}?(?= [A-Z][a-z]+:|$)", text)] if m]
    return "; ".join(found) or "단위·갱신일 못 찾음"


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
