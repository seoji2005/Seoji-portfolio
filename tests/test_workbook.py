"""시트 수식(LibreOffice로 계산)이 파이썬 기준 구현과 같은 답을 내는지 대조한다."""

import datetime as dt

import pytest

from builder.workbook import (
    DASH_CAND, HOLD_FIRST, MACRO_HELP_FIRST, PLAN_FIRST, SC, SENT_FIRST, SH_DASH, SH_HOLD, SH_MACRO, SH_PLAN, SH_SENT,
    SH_REASON, SH_STOCK, STOCK_FIRST, REASON_FIRST, DASH_HOLD,
)
from builder import v1_macro as macro
from builder.v1_holdings import evaluate_holdings, plan_purchase, reason_note, record_status
from judge import sentiment
from judge.stocks import evaluate_pool

from .conftest import needs_soffice

pytestmark = needs_soffice


def v(ws, cell):
    x = ws[cell].value
    if isinstance(x, dt.datetime):
        return x.date()
    return None if x == "" else x


def blank(x):
    return None if x in ("", None) else x


def approx(x):
    return None if x is None else pytest.approx(x, rel=1e-9, abs=1e-9)


def all_errors(book):
    return [f"{ws.title}!{c.coordinate}={c.value}" for ws in book.worksheets for row in ws.iter_rows() for c in row if c.data_type == "e"]


@pytest.fixture(scope="module")
def data(case):
    return case[0]


@pytest.fixture(scope="module")
def book(case):
    return case[1]


def test_no_formula_errors(book, template_book):
    assert all_errors(book) == []
    assert all_errors(template_book) == []


@pytest.fixture(scope="module")
def pools(data):
    return {c: evaluate_pool(data["stocks"][c], c) for c in ("한국", "미국")}


@pytest.mark.parametrize("country", ["한국", "미국"])
def test_stock_sheet(book, pools, country):
    ws = book[SH_STOCK[country]]
    results, best = pools[country]
    assert v(ws, "B3") == sum(r.scored for r in results)
    assert v(ws, "E3") == (blank(best.stock.name) if best else None)
    assert v(ws, "H3") == (best.score if best else None)
    for i, r in enumerate(results):
        row = STOCK_FIRST + i
        cell = lambda k: v(ws, f"{SC[k]}{row}")  # noqa: E731
        assert cell("filter") == r.filter_text, r.stock.code
        assert cell("status") == r.status, r.stock.code
        assert cell("score") == r.score, r.stock.code
        assert cell("decision") == blank(r.decision), r.stock.code
        assert cell("summary") == r.summary, r.stock.code
        for k in ("roe", "growth", "ey", "mom"):
            assert cell(k) == approx(r.metrics[k]), (r.stock.code, k)
            assert cell("c_" + k) == r.cards[k], (r.stock.code, k)
            if r.scored:
                assert cell("p_" + k) == approx(r.pct[k]), (r.stock.code, k)
        assert cell("debt_ratio") == approx(r.debt_ratio)


def test_holdings_sheet(book, data, pools):
    ws = book[SH_HOLD]
    out = evaluate_holdings(data["account"], data["holdings"], data["reasons"], pools)
    assert v(ws, "D6") == sum(r.value_krw is not None for r in out)
    for i, r in enumerate(out):
        row = HOLD_FIRST + i
        assert v(ws, f"I{row}") == r.action
        assert v(ws, f"J{row}") == approx(r.value_krw)
        assert v(ws, f"K{row}") == approx(r.loss_krw)
        assert v(ws, f"L{row}") == approx(r.loss_ratio)
        assert v(ws, f"M{row}") == approx(r.price_change)
        assert v(ws, f"N{row}") == ("도달" if r.loss_hit else None)
        assert v(ws, f"O{row}") == r.record
        assert v(ws, f"P{row}") == ("무너짐" if r.core_broken else None)
        assert v(ws, f"Q{row}") == blank(r.earnings)
        assert v(ws, f"R{row}") == approx(r.weight)
        assert v(ws, f"S{row}") == ("초과" if r.conc_hit else None)
        assert v(ws, f"T{row}") == approx(r.excess_krw)
        assert v(ws, f"U{row}") == r.score
        assert v(ws, f"V{row}") == blank(r.best_text)
        assert v(ws, f"W{row}") == ("제안" if r.replace_hit else None)


@pytest.fixture(scope="module")
def senti(data):
    return {m: sentiment.compute(m, data["sentiment"][m]) for m in ("미국", "한국")}


@pytest.mark.parametrize("market", ["미국", "한국"])
def test_sentiment_sheet(book, senti, market):
    ws = book[SH_SENT[market]]
    res = senti[market]
    assert v(ws, "B4") == res.last_date
    assert v(ws, "B5") == res.cutoff
    assert v(ws, "B6") == res.score
    assert v(ws, "B7") == blank(res.band)
    assert v(ws, "B9") == approx(res.composite)
    assert v(ws, "B10") == res.message
    for j, ind in enumerate(res.indicators):
        row = 13 + j
        assert v(ws, f"A{row}") == ind["label"]
        assert v(ws, f"B{row}") == approx(ind["latest"])
        assert v(ws, f"C{row}") == ind["last_date"]
        assert v(ws, f"D{row}") == approx(ind["pct"])
        assert v(ws, f"F{row}") == approx(ind["greed"])
        assert v(ws, f"G{row}") == ind["n"]
    # 날마다의 지표 평균도 모두 같아야 한다
    comp_col = 13 if market == "미국" else 19
    for k, row in enumerate(res.rows):
        r = SENT_FIRST + k
        assert v(ws, f"A{r}") == row["date"]
        got = ws.cell(r, comp_col).value
        assert blank(got) == approx(row["composite"]), row["date"]


def test_macro_sheet(book, data):
    ws = book[SH_MACRO]
    for j, item in enumerate(macro.panel(data["macro"])):
        row = 5 + j
        assert v(ws, f"A{row}") == item["label"]
        assert v(ws, f"C{row}") == approx(item["current"]), item["key"]
        assert v(ws, f"E{row}") == item["last_date"], item["key"]
        assert v(ws, f"F{row}") == approx(item["pct"]), item["key"]
        assert v(ws, f"G{row}") == item["n"], item["key"]
        assert v(ws, f"H{row}") == item["first"], item["key"]
        assert v(ws, f"J{row}") == item["issues"], item["key"]
    assert MACRO_HELP_FIRST > 12  # 패널과 보조 계산이 겹치지 않음


def test_plan_sheet(book, data, pools, senti):
    ws = book[SH_PLAN]
    for i, p in enumerate(data["plans"]):
        row = PLAN_FIRST + i
        results, _ = pools[p.country]
        score = next((r.score for r in results if r.stock.code == p.code), None)
        out = plan_purchase(p, senti[p.country].score, score, record_status(p.code, data["reasons"]))
        assert v(ws, f"F{row}") == out["advice"]
        assert v(ws, f"H{row}") == blank(out["band"])
        assert v(ws, f"I{row}") == out["times"]
        assert v(ws, f"J{row}") == out["weeks"]
        assert v(ws, f"K{row}") == approx(out["each"])
        assert [v(ws, f"{c}{row}") for c in "LMNO"] == out["dates"] + [None] * (4 - len(out["dates"]))
        assert v(ws, f"Q{row}") == out["candidate"]


def test_reason_notes(book, data):
    ws = book[SH_REASON]
    earnings = {}
    for h in data["holdings"]:
        earnings.setdefault(h.code, h.last_earnings)
    for i, r in enumerate(data["reasons"]):
        assert v(ws, f"K{REASON_FIRST + i}") == blank(reason_note(r, earnings)), r


def test_dashboard_holdings(book, data, pools):
    ws = book[SH_DASH]
    out = evaluate_holdings(data["account"], data["holdings"], data["reasons"], pools)
    for i, r in enumerate(out):
        row = DASH_HOLD + i
        h = r.holding
        assert [v(ws, f"{c}{row}") for c in "ABCDE"] == [h.country, h.code, blank(h.name), r.action, r.score]
    assert v(ws, f"A{DASH_HOLD + len(out)}") is None


def test_dashboard_candidates(book, pools):
    ws = book[SH_DASH]
    for country, (c_name, c_score) in (("한국", ("C", "B")), ("미국", ("F", "E"))):
        results, _ = pools[country]
        cands = sorted((r for r in results if r.decision == "편입 후보"), key=lambda r: -r.score)
        got = [(v(ws, f"{c_name}{DASH_CAND + k}"), v(ws, f"{c_score}{DASH_CAND + k}")) for k in range(10)]
        want = [(r.stock.name, r.score) for r in cands] + [(None, None)] * (10 - len(cands))
        assert got == want


def test_template_is_blank(template_book):
    assert v(template_book[SH_SENT["미국"]], "B10") == "원자료 없음"
    assert v(template_book[SH_HOLD], f"I{HOLD_FIRST}") is None
    assert v(template_book[SH_MACRO], "J5") == "자료 없음"
