"""관심 종목: 국가별 점수 순 목록. 줄을 누르면 종목 상세로."""

import pandas as pd
import streamlit as st

from app import fmt, state, store, ui

state.header()
st.title("관심 종목")
st.caption("점수는 이 목록(보유 종목 포함) 안에서 같은 국가끼리 매긴 위치입니다. 프로그램은 제안만 합니다.")

country = st.segmented_control("시장", ["미국", "한국"], default="미국", key="wl_country", label_visibility="collapsed") or "미국"

try:
    with st.spinner("시세와 재무를 불러오는 중… 처음에는 1~2분 걸릴 수 있습니다."):
        pools = state.pool()
except Exception as ex:  # noqa: BLE001
    st.error(f"자료를 불러오지 못했습니다: {ex}")
    st.stop()

group, best = pools.get(country, ([], None))
problems = {}
for d in group:
    if d.data_problem:
        problems.setdefault(d.data_problem, []).append(d.name)
for why, names in problems.items():
    st.warning(f"{len(names)}종목의 재무를 받지 못해 점수를 매기지 못했습니다 — {why}", icon=":material/cloud_off:")
if problems:
    st.page_link("app/views/settings.py", label="설정·도움말에서 고치는 법 보기", icon=":material/settings:")
if not group:
    st.info("이 시장의 관심 종목이 없습니다. 아래 '관심 종목 고치기'에서 추가하세요.")
else:
    scored = [d for d in group if d.result.scored]
    cands = [d for d in scored if d.result.decision == "편입 후보"]
    ui.kpis([("채점 종목", f"{len(scored)} / {len(group)}"), ("편입 후보(70점↑)", f"{len(cands)}개"), ("최고 미보유 후보", best.name if best else "–", fmt.score(best.result.score) if best else "")])
    more = st.toggle("가격·요약도 보기", key="wl_more")

    rows = []
    for d in group:
        q, r = d.quote, d.result
        chg = (q.price / q.previous_close - 1) if q.price and q.previous_close else None
        rows.append(
            {
                "종목": ("★ " if d.held else "") + d.name,
                "점수": r.score,
                "판정": "자료 없음" if d.data_problem else (r.decision or ("" if r.scored else "점수 없음")),
                "현재가": fmt.price(q.price, country),
                "오늘": chg,
                "요약": d.data_problem or r.summary,
                "_code": d.entry.code,
            }
        )
    df = pd.DataFrame(rows).sort_values("점수", ascending=False, na_position="last").reset_index(drop=True)
    sel = st.dataframe(
        df,
        hide_index=True,
        column_order=["종목", "점수", "판정", "현재가", "오늘", "요약"] if more else ["종목", "점수", "판정"],
        column_config={
            "점수": st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f", width="small"),
            "오늘": st.column_config.NumberColumn("오늘", format="percent", width="small"),
            "종목": st.column_config.TextColumn("종목", width="small"),
            "요약": st.column_config.TextColumn("한 줄 요약", width="large"),
        },
        on_select="rerun",
        selection_mode="single-row",
        key=f"wl_table_{country}",
    )
    st.caption("★ 보유 중 · 줄을 누르면 종목 상세로 갑니다.")
    picked = sel.selection.rows if sel else []
    if picked:
        code = df.loc[picked[0], "_code"]
        st.session_state["stock"] = (country, code)
        st.switch_page("app/views/stock.py", query_params={"country": country, "code": code})

with st.expander("관심 종목 고치기"):
    st.caption("국가(미국/한국), 종목코드(미국 AAPL, 한국 005930), 이름, 시장(한국만: KOSPI/KOSDAQ), 금융·리츠(Y/N, 비우면 업종으로 자동)")
    wl = store.read("watchlist")
    edited = st.data_editor(
        wl,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "country": st.column_config.SelectboxColumn("국가", options=["미국", "한국"], required=True),
            "code": st.column_config.TextColumn("종목코드", required=True),
            "name": st.column_config.TextColumn("이름"),
            "market": st.column_config.SelectboxColumn("시장", options=["", "KOSPI", "KOSDAQ"]),
            "fin": st.column_config.SelectboxColumn("금융·리츠", options=["", "Y", "N"]),
        },
        key="wl_editor",
    )
    if st.button("저장", type="primary"):
        state.flash(store.write("watchlist", edited.fillna("")))
        st.rerun()
