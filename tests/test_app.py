"""앱 화면을 예시 자료로 돌려 본다(브라우저 없이). 내 자료는 실제처럼 CSV 파일에서 읽는다."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

MAIN = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")

PORTFOLIO = """country,code,name,qty,avg_price,cost_krw,last_earnings
미국,AAPL,애플,30,150,6000000,2026-07-30
한국,005930,삼성전자,100,70000,7000000,
미국,TSLA,테슬라,10,300,4000000,
"""
CARDS = """code,no,reason,indicator,fact,condition,period,status,note,checked
005930,1,메모리 업황,부문 영업이익,,2분기 연속 적자,,무너짐,2분기 적자 확인,2026-08-01
005930,2,고객 계약,,핵심 고객 장기 계약 공시,해지·미갱신,,통과,,2026-08-01
AAPL,1,서비스 매출,서비스 매출 전년비,,2회 연속 5% 미만,,보류,자료 상충,2026-08-01
"""
PAGES = ["app/views/watchlist.py", "app/views/stock.py", "app/views/reasons.py", "app/views/portfolio.py", "app/views/sentiment.py",
         "app/views/macro.py", "app/views/extra.py", "app/views/backtest.py", "app/views/settings.py"]


@pytest.fixture
def my_dir(tmp_path, monkeypatch):
    (tmp_path / "watchlist.csv").write_text(
        "country,code,name,market,fin\n미국,AAPL,애플,,\n미국,NVDA,엔비디아,,\n미국,TSLA,테슬라,,\n미국,JPM,JP모건,,\n"
        "한국,005930,삼성전자,KOSPI,\n한국,000660,SK하이닉스,KOSPI,\n",
        encoding="utf-8",
    )
    (tmp_path / "portfolio.csv").write_text(PORTFOLIO, encoding="utf-8")
    (tmp_path / "account.csv").write_text("total_krw,cash_krw\n100000000,3000000\n", encoding="utf-8")
    (tmp_path / "buy_reasons.csv").write_text(CARDS, encoding="utf-8")
    (tmp_path / "evidence.csv").write_text("code,kind,holder,detail,weight_pct,as_of,source\nAAPL,참고지수 비중,S&P 500,,6.5,2026-09-30,spglobal.com\n", encoding="utf-8")
    monkeypatch.setenv("DATA_MODE", "sample")
    monkeypatch.setenv("MY_DATA_DIR", str(tmp_path))
    return tmp_path


def run(page=None):
    at = AppTest.from_file(MAIN, default_timeout=180)
    at.run()
    if page:
        at.switch_page(page).run()
    return at


def text(at):
    return " ".join([m.body for m in at.markdown] + [c.body for c in at.caption] + [w.body for w in at.warning] + [i.body for i in at.info])


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_errors(my_dir, page):
    at = run(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert at.title


def test_watchlist_shows_pool_summary(my_dir):
    at = run()
    assert "채점 종목" in text(at) and "/ 4" in text(at)  # 미국 4종목(JPM은 금융이라 점수 없음)
    assert any("★ 애플" in str(df.value) for df in at.dataframe)


def test_sell_signals_follow_card_status(my_dir):
    at = run("app/views/portfolio.py")
    samsung = [w.value for w in at.warning if w.value.startswith("**삼성전자**")]
    assert samsung and "② 매수 이유 무너짐 → 매도 검토" in samsung[0]  # 비중 40%도 넘지만 ②가 먼저
    assert not any(w.value.startswith("**애플** — ②") for w in at.warning)  # 보류는 신호가 아님
    assert any("③ 비중" in c.value for c in at.caption)  # 뒤 순위 신호도 함께 보임


def test_stock_card_shows_filter_card_and_evidence(my_dir):
    at = run("app/views/stock.py")  # 첫 종목 = 애플
    t = text(at)
    assert "**거름망**" in t and "부채비율 200% 이하" in t
    assert "**매수 이유 카드** — 보류" in t
    assert "참고 근거" in [s.value for s in at.subheader]
    assert "S&P 500 비중" not in t  # 13F 비중이 없으면 지수 비중만으로 차이를 만들지 않음
    assert "미확인" in t and "예시 자료 모드라 SEC를 조회하지 않음" in t


def test_reason_card_page_shows_status_and_buy_block(my_dir):
    at = run("app/views/reasons.py")
    table = at.dataframe[0].value
    assert set(table["카드 상태"]) == {"무너짐", "보류"}


def test_legacy_reasons_are_shown_not_deleted(my_dir):
    (my_dir / "buy_reasons.csv").unlink()
    (my_dir / "reasons.csv").write_text("code,no,reason,core,evidence,break_rule,checked,result\n005930,1,옛 이유,Y,부문 이익,적자,2026-01-01,유지\n", encoding="utf-8")
    at = run("app/views/reasons.py")
    assert any("이전 형식" in i.value for i in at.info)
    assert (my_dir / "reasons.csv").exists()


def test_sentiment_and_macro_pages(my_dir):
    at = run("app/views/sentiment.py")
    assert "심리 점수" in text(at) and "신규 매수" in text(at)
    at = run("app/views/macro.py")
    table = at.dataframe[0].value
    assert len(table) == 5
    exports = table[table["지표"] == "한국 수출 전년비"]["계산에 쓴 값"].iloc[0]
    assert " ÷ " in exports and exports.endswith(" − 1")  # 이번 달 원값 ÷ 1년 전 같은 달 원값 − 1


def test_non_spec_pages_are_labeled(my_dir):
    for page in ("app/views/extra.py", "app/views/backtest.py"):
        at = run(page)
        assert any("사전 밖 기능" in w.value for w in at.warning)
