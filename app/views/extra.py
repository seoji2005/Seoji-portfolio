"""사전 밖 기능(동결·보존): 포트폴리오 점수, 종목을 더하면?

2026-10-08에 요청해 만든 기능이지만 2026-10-09 사전에는 없다. 지울지 확인을 받을 때까지 판단 화면과 분리해 둔다.
판단(1~7번)에는 쓰지 않는다.
"""

import streamlit as st

from app import charts, fmt, state, ui
from judge.common import SPEC
from judge.portfolio import Position, portfolio_score, shares, what_if

state.header()
st.title("포트폴리오 점수·종목 추가")
st.warning("사전 밖 기능입니다. 동결·보존 중이며, 매수·매도 판단에는 쓰지 않습니다.", icon=":material/inventory_2:")

try:
    b = state.book()
except Exception as ex:  # noqa: BLE001
    st.error(f"자료를 불러오지 못했습니다: {ex}")
    st.stop()

ps = portfolio_score(b.positions)
ui.kpis([("포트폴리오 점수", fmt.score(ps.total), "보유 종목 점수의 평가액 가중 평균"), ("보유 종목", f"{len(b.positions)}개")])
if ps.by_country:
    st.caption(" · ".join(f"{c} {fmt.score(v)}" for c, v in ps.by_country.items()) + " (종목 점수는 국가별 풀 안의 위치라 전체 점수는 참고용)")
for name, weight, why in ps.unscored:
    st.caption(f"점수 없음: {name} (비중 {weight:.0%}) — {why}")

st.subheader("종목을 더하면?")
pools = state.pool()
choices = [(c, d.entry.code) for c in ("미국", "한국") for d in pools[c][0]]
labels = {(c, d.entry.code): f"{c} · {d.name}" + (f" ({d.result.score:.1f})" if d.result.scored else " (점수 없음)") for c in ("미국", "한국") for d in pools[c][0]}
if choices:
    pick = st.selectbox("종목", choices, format_func=labels.get, key="ex_add")
    amount = st.number_input("살 금액(원)", min_value=0, value=1_000_000, step=500_000, format="%d", key="ex_amount")
    d = state.find(*pick)
    w = what_if(b.positions, b.cash, Position(pick[0], pick[1], d.name, float(amount), d.result.score if d.result.scored else None, d.result.summary))
    held = [p for p in w["positions_after"] if p.value_krw > 0]
    share = shares(held, w["cash_after"])
    ui.kpis([("포트폴리오 점수", fmt.score(w["after"].total), ui.change(w["after"].total, w["before"].total)),
             (f"{d.name} 비중", fmt.pct(share.get(pick[1])), "개별 몫 대비")])
    for name, weight, excess in w["concentration_after"]:
        st.warning(f"{name} 비중 {weight:.0%} — 40% 초과(초과 {fmt.won(excess)}).", icon=":material/warning:")
    if held:
        st.plotly_chart(charts.weights_bar([p.name for p in held], [share[p.code] for p in held], {d.name}, SPEC["conc_max"], state.dark()), config=charts.CONFIG)
    if st.button("이 구성으로 과거 성과 보기", icon=":material/history:"):
        st.session_state["bt_add"] = (pick[0], pick[1], float(amount))
        st.switch_page("app/views/backtest.py")
