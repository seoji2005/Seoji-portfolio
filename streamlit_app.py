"""내 투자 판단 — Streamlit 앱 입구. 실행: streamlit run streamlit_app.py"""

import streamlit as st

from app import state

st.set_page_config(page_title="내 투자 판단", page_icon=":material/insights:", layout="centered")
state.bridge_secrets()

PAGES = {
    "사전": [
        st.Page("app/views/watchlist.py", title="관심 종목", icon=":material/format_list_bulleted:", default=True),
        st.Page("app/views/stock.py", title="종목 카드", icon=":material/show_chart:", url_path="stock"),
        st.Page("app/views/reasons.py", title="매수 이유 카드", icon=":material/fact_check:", url_path="reasons"),
        st.Page("app/views/portfolio.py", title="보유·매도 판단", icon=":material/sell:", url_path="portfolio"),
        st.Page("app/views/sentiment.py", title="시장 심리", icon=":material/speed:", url_path="sentiment"),
        st.Page("app/views/macro.py", title="거시 참고", icon=":material/public:", url_path="macro"),
    ],
    "사전 밖 기능(동결·보존)": [
        st.Page("app/views/extra.py", title="포트폴리오 점수·종목 추가", icon=":material/donut_large:", url_path="extra"),
        st.Page("app/views/backtest.py", title="과거 성과", icon=":material/history:", url_path="backtest"),
    ],
    "설정": [st.Page("app/views/settings.py", title="설정·도움말", icon=":material/settings:", url_path="settings")],
}
st.navigation(PAGES, position="top").run()
