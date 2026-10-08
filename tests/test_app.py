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
PAGES = ["app/views/watchlist.py", "app/views/stock.py", "app/views/portfolio.py", "app/views/backtest.py", "app/views/settings.py"]


@pytest.fixture
def my_dir(tmp_path, monkeypatch):
    (tmp_path / "watchlist.csv").write_text(
        "country,code,name,market,fin\n미국,AAPL,애플,,\n미국,NVDA,엔비디아,,\n미국,TSLA,테슬라,,\n미국,JPM,JP모건,,\n"
        "한국,005930,삼성전자,KOSPI,\n한국,000660,SK하이닉스,KOSPI,\n",
        encoding="utf-8",
    )
    (tmp_path / "portfolio.csv").write_text(PORTFOLIO, encoding="utf-8")
    (tmp_path / "account.csv").write_text("total_krw,cash_krw\n100000000,3000000\n", encoding="utf-8")
    (tmp_path / "reasons.csv").write_text(
        "code,no,reason,core,evidence,break_rule,checked,result\n005930,1,메모리 업황,Y,부문 이익,2분기 연속 적자,2026-08-01,무너짐\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATA_MODE", "sample")
    monkeypatch.setenv("MY_DATA_DIR", str(tmp_path))
    return tmp_path


def run(page=None):
    at = AppTest.from_file(MAIN, default_timeout=180)
    at.run()
    if page:
        at.switch_page(page).run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_errors(my_dir, page):
    at = run(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert at.title


def test_watchlist_shows_pool_summary(my_dir):
    at = run()
    html = " ".join(m.body for m in at.markdown)
    assert "채점 종목" in html and "/ 4" in html  # 미국 4종목(JPM은 금융이라 점수 없음)
    assert any("★ 애플" in str(df.value) for df in at.dataframe)


def test_portfolio_actions_follow_priority(my_dir):
    at = run("app/views/portfolio.py")
    shown = [w.value for w in at.warning]
    samsung = [w for w in shown if w.startswith("**삼성전자**")]
    # 비중 40%도 넘지만, 핵심 이유가 무너진 ②가 ③보다 먼저
    assert samsung and "② 핵심 매수 이유 붕괴" in samsung[0]


def test_stock_page_what_if(my_dir):
    at = run("app/views/stock.py")
    html = " ".join(m.body for m in at.markdown)
    assert "포트폴리오 점수" in html and "개별 몫 대비" in html
