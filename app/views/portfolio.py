"""보유·매도 판단(사전 5·6): 매도 판단 신호 목록, 보유·계좌 고치기."""

import pandas as pd
import streamlit as st

from app import charts, fmt, state, store, ui
from judge.common import SPEC

state.header()
st.title("보유·매도 판단")
st.caption("개별 종목 몫(전체의 30%)만 다룹니다. 지수 몫은 이 프로그램이 판단하지 않습니다. 제안만 하며, 매매는 직접 합니다.")

try:
    with st.spinner("보유 종목을 계산하는 중…"):
        b = state.book()
except Exception as ex:  # noqa: BLE001
    st.error(f"자료를 불러오지 못했습니다: {ex}")
    st.stop()

if not b.holdings:
    st.info("보유 종목이 없습니다. 아래 '보유 종목'에서 추가하세요.")
else:
    stocks_total = sum(h.value_krw or 0 for h in b.holdings)
    ui.kpis([
        ("개별 몫(주식+대기 현금)", fmt.won(stocks_total + b.cash), f"대기 현금 {fmt.won(b.cash)}"),
        ("보유 종목", f"{len(b.holdings)}개"),
        ("매도 신호", f"{sum(1 for h in b.holdings if h.signals)}종목"),
    ])
    st.subheader("매도 판단 신호")
    any_signal = False
    for h in b.holdings:
        for i, sig in enumerate(h.signals):
            any_signal = True
            icon = {"①": ":material/error:", "②": ":material/report:", "③": ":material/balance:", "④": ":material/swap_horiz:"}.get(sig[0])
            (st.warning if i == 0 else st.caption)(f"**{h.holding.name}** — {sig}" + ("" if i == 0 else " (뒤 순위)"), **({"icon": icon} if i == 0 else {}))
    if not any_signal:
        st.success("걸린 신호가 없습니다. 모두 유지.", icon=":material/check:")
    st.caption("우선순위: ① 손실 한도(손실액 ≥ 계좌 평가액 2%, 또는 매수가 대비 −25%) → 매도 · ② 매수 이유 카드 '무너짐' → 매도 검토 · "
               "③ 3종목 이상 보유 중 한 종목이 개별 몫의 40% 초과 → 초과분만 매도 · ④ 점수 50 미만 + 같은 국가에 10점 이상 높은 후보 → 교체 제안. "
               "'많이 올랐다'는 신호가 아닙니다.")

    rows = [{"종목": h.holding.name, "제안": h.action, "카드": h.card_status or "없음", "점수": h.score, "비중": h.weight,
             "매수가 대비": h.price_change, "평가액": fmt.won(h.value_krw)} for h in b.holdings]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "종목": st.column_config.TextColumn("종목", width="small"),
            "제안": st.column_config.TextColumn("제안", width="medium"),
            "카드": st.column_config.TextColumn("매수 이유 카드", width="small"),
            "점수": st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f"),
            "비중": st.column_config.NumberColumn("비중", format="percent", help="개별 몫(주식+대기 현금) 대비"),
            "매수가 대비": st.column_config.NumberColumn("매수가 대비", format="percent"),
        },
    )
    names = [h.holding.name for h in b.holdings]
    weights = [h.weight or 0 for h in b.holdings]
    st.plotly_chart(charts.weights_bar(names, weights, set(), SPEC["conc_max"], state.dark()), config=charts.CONFIG)
    with st.expander("표로 보기"):
        st.dataframe(pd.DataFrame({"종목": names, "비중": [fmt.pct(w) for w in weights]}), hide_index=True)

st.subheader("고치기")
with st.expander("계좌"):
    total, cash = state.account()
    t = st.number_input("계좌 전체 평가액(원) — 손실 한도 2%의 기준", min_value=0, value=int(total), step=1_000_000, format="%d")
    c = st.number_input("개별 몫 대기 현금(원) — 비중 40% 계산에 포함", min_value=0, value=int(cash), step=100_000, format="%d")
    if st.button("계좌 저장"):
        state.flash(store.write("account", pd.DataFrame([{"total_krw": t, "cash_krw": c}])))
        st.rerun()

with st.expander("보유 종목"):
    st.caption("평균가는 현지 통화(원/달러), 원화 매수원가는 실제로 쓴 원화 합계")
    pf = store.read("portfolio")
    edited = st.data_editor(
        pf,
        num_rows="dynamic",
        hide_index=True,
        column_order=["country", "code", "name", "qty", "avg_price", "cost_krw"],
        column_config={
            "country": st.column_config.SelectboxColumn("국가", options=["미국", "한국"], required=True),
            "code": st.column_config.TextColumn("종목코드", required=True),
            "name": st.column_config.TextColumn("이름"),
            "qty": st.column_config.TextColumn("수량"),
            "avg_price": st.column_config.TextColumn("평균가"),
            "cost_krw": st.column_config.TextColumn("원화 매수원가"),
        },
        key="pf_editor",
    )
    if st.button("보유 종목 저장", type="primary"):
        keep = pf.reindex(edited.index)["last_earnings"].fillna("") if "last_earnings" in pf else ""  # 예전 칸은 지우지 않고 그대로 둔다
        state.flash(store.write("portfolio", edited.assign(last_earnings=keep).fillna("")))
        st.rerun()
st.page_link("app/views/reasons.py", label="매수 이유 카드 고치기", icon=":material/fact_check:")
