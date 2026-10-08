"""내 포트폴리오: 포트폴리오 점수(명세 8), 매도 판단(명세 5·6), 종목을 더하면?, 보유·계좌·매수 이유 고치기."""

import pandas as pd
import streamlit as st

from app import charts, fmt, state, store, ui
from judge.common import SPEC
from judge.portfolio import Position, portfolio_score, shares, what_if

state.header()
st.title("내 포트폴리오")
st.caption("개별 종목 몫(전체의 30%)만 다룹니다. 지수 몫은 규칙(고점 대비 −10/−20/−30% 분할매수)으로 따로 운용합니다.")

try:
    with st.spinner("포트폴리오를 계산하는 중…"):
        b = state.book()
except Exception as ex:  # noqa: BLE001
    st.error(f"자료를 불러오지 못했습니다: {ex}")
    st.stop()
dark = state.dark()
ps = portfolio_score(b.positions)
stocks_total = sum(p.value_krw for p in b.positions)

if not b.positions:
    st.info("보유 종목이 없습니다. 아래 '보유 종목 고치기'에서 추가하세요.")
else:
    ui.kpis([
        ("포트폴리오 점수", fmt.score(ps.total), "평가액 가중 평균 · 표시만"),
        ("개별 몫", fmt.won(stocks_total + b.cash), f"대기 현금 {fmt.won(b.cash)}"),
        ("개별 종목", f"{len(b.positions)}개", "명세: 3~5개"),
    ])
    if ps.by_country:
        st.caption(" · ".join(f"{c} {fmt.score(v)}" for c, v in ps.by_country.items()) + " (종목 점수는 국가별 풀 안의 위치라 전체 점수는 참고용)")
    for name, weight, why in ps.unscored:
        st.caption(f"점수 없음: {name} (비중 {weight:.0%}) — {why}")

    rows = []
    for p, h in zip(b.positions, b.holdings):
        rows.append(
            {
                "종목": p.name,
                "평가액": fmt.won(h.value_krw),
                "비중": h.weight,
                "점수": p.score,
                "매수가 대비": h.price_change,
                "제안": h.action,
            }
        )
    st.subheader("매도 판단")
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_order=["종목", "제안", "점수", "비중", "평가액", "매수가 대비"],
        column_config={
            "종목": st.column_config.TextColumn("종목", width="small"),
            "비중": st.column_config.NumberColumn("비중", format="percent", help="개별 몫(주식+대기 현금) 대비"),
            "점수": st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f"),
            "매수가 대비": st.column_config.NumberColumn("매수가 대비", format="percent"),
            "제안": st.column_config.TextColumn("제안", width="medium"),
        },
    )
    for p, h in zip(b.positions, b.holdings):
        if h.action != "유지":
            icon = {"①": ":material/error:", "②": ":material/report:", "③": ":material/balance:", "④": ":material/swap_horiz:"}.get(h.action[0])
            st.warning(f"**{p.name}** — {h.action}", icon=icon)
    st.caption("우선순위: ① 손실 한도(계좌의 2% 또는 −25%) → ② 핵심 매수 이유 붕괴 → ③ 비중 40% 초과(3종목 이상) → ④ 점수 50 미만 + 10점 이상 높은 후보. '많이 올랐다'는 매도 신호가 아닙니다.")
    names = [p.name for p in b.positions]
    weights = [h.weight or 0 for h in b.holdings]
    st.plotly_chart(charts.weights_bar(names, weights, set(), SPEC["conc_max"], dark), config=charts.CONFIG)
    with st.expander("표로 보기"):
        st.dataframe(pd.DataFrame({"종목": names, "비중": [fmt.pct(w) for w in weights]}), hide_index=True)

# 종목을 더하면?
st.subheader("종목을 더하면?")
pools = state.pool()
choices = [(c, d.entry.code) for c in ("미국", "한국") for d in pools[c][0]]
labels = {(c, d.entry.code): f"{c} · {d.name}" + (f" ({d.result.score:.1f})" if d.result.scored else " (점수 없음)") for c in ("미국", "한국") for d in pools[c][0]}
if choices:
    pick = st.selectbox("종목", choices, format_func=labels.get, key="pf_add")
    amount = st.number_input("살 금액(원)", min_value=0, value=1_000_000, step=500_000, format="%d", key="pf_amount")
    d = state.find(*pick)
    w = what_if(b.positions, b.cash, Position(pick[0], pick[1], d.name, float(amount), d.result.score if d.result.scored else None, d.result.summary))
    before, after = w["before"], w["after"]
    ui.kpis([("포트폴리오 점수", fmt.score(after.total), ui.change(after.total, before.total)),
             (f"{d.name} 비중", fmt.pct(shares(w["positions_after"], w["cash_after"]).get(pick[1])), "개별 몫 대비")])
    for name, weight, excess in w["concentration_after"]:
        st.warning(f"{name} 비중 {weight:.0%} — 40% 초과(초과 {fmt.won(excess)}).", icon=":material/warning:")
    if st.button("이 구성으로 과거 성과 보기", icon=":material/history:"):
        st.session_state["bt_add"] = (pick[0], pick[1], float(amount))
        st.switch_page("app/views/backtest.py")

# 고치기
st.subheader("고치기")
with st.expander("계좌"):
    total, cash = state.account()
    t = st.number_input("전체 투자 계좌 평가액(원) — 손실 한도 2%의 기준", min_value=0, value=int(total), step=1_000_000, format="%d")
    c = st.number_input("개별 몫 대기 현금(원) — 비중 40% 계산에 포함", min_value=0, value=int(cash), step=100_000, format="%d")
    if st.button("계좌 저장"):
        state.flash(store.write("account", pd.DataFrame([{"total_krw": t, "cash_krw": c}])))
        st.rerun()

with st.expander("보유 종목"):
    st.caption("평균가는 현지 통화(원/달러), 원화 매수원가는 실제로 쓴 원화 합계, 실적 발표일은 YYYY-MM-DD")
    pf = store.read("portfolio")
    edited = st.data_editor(
        pf,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "country": st.column_config.SelectboxColumn("국가", options=["미국", "한국"], required=True),
            "code": st.column_config.TextColumn("종목코드", required=True),
            "name": st.column_config.TextColumn("이름"),
            "qty": st.column_config.TextColumn("수량"),
            "avg_price": st.column_config.TextColumn("평균가"),
            "cost_krw": st.column_config.TextColumn("원화 매수원가"),
            "last_earnings": st.column_config.TextColumn("최근 실적 발표일"),
        },
        key="pf_editor",
    )
    if st.button("보유 종목 저장", type="primary"):
        state.flash(store.write("portfolio", edited.fillna("")))
        st.rerun()

with st.expander("매수 이유 (명세 7)"):
    st.caption("이유 1~3개, 핵심 1개(Y), 이유마다 확인할 근거와 무너짐 기준. 핵심 이유가 '무너짐'이면 매도 판단 ②가 걸립니다.")
    rs = store.read("reasons")
    edited_r = st.data_editor(
        rs,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "code": st.column_config.TextColumn("종목코드", required=True),
            "no": st.column_config.TextColumn("번호"),
            "reason": st.column_config.TextColumn("매수 이유"),
            "core": st.column_config.SelectboxColumn("핵심", options=["", "Y"]),
            "evidence": st.column_config.TextColumn("확인할 근거"),
            "break_rule": st.column_config.TextColumn("무너짐 기준"),
            "checked": st.column_config.TextColumn("최근 점검일"),
            "result": st.column_config.SelectboxColumn("점검 결과", options=["", "유지", "무너짐"]),
        },
        key="rs_editor",
    )
    if st.button("매수 이유 저장"):
        state.flash(store.write("reasons", edited_r.fillna("")))
        st.rerun()
    for h in b.holdings:
        if h.record != "기록 완료":
            st.caption(f"{h.holding.name}: 매수 이유 {h.record}")
        if h.earnings == "점검 필요":
            st.caption(f"{h.holding.name}: 실적 발표 뒤 점검 필요")
