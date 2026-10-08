"""내 투자 판단 — Streamlit 앱 입구. 실행: streamlit run streamlit_app.py"""

import streamlit as st

from app import state

st.set_page_config(page_title="내 투자 판단", page_icon=":material/insights:", layout="centered")
state.bridge_secrets()

PAGES = [
    st.Page("app/views/watchlist.py", title="관심 종목", icon=":material/format_list_bulleted:", default=True),
    st.Page("app/views/stock.py", title="종목 상세", icon=":material/show_chart:", url_path="stock"),
    st.Page("app/views/portfolio.py", title="내 포트폴리오", icon=":material/donut_large:", url_path="portfolio"),
    st.Page("app/views/backtest.py", title="과거 성과", icon=":material/history:", url_path="backtest"),
    st.Page("app/views/settings.py", title="설정·도움말", icon=":material/settings:", url_path="settings"),
]
st.navigation(PAGES, position="top").run()
