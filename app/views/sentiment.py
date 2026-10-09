"""시장 심리(사전 3): 신규 매수를 몇 번에 나눌지만 정한다. 매도에는 쓰지 않는다."""

import pandas as pd
import streamlit as st

from app import fmt, state, store, ui
from judge import sentiment
from market import csvin

state.header()
st.title("시장 심리")
st.caption("신규 종목 매수를 몇 번에 나눌지만 정합니다. 매도에는 쓰지 않습니다. 0 = 극단 공포, 100 = 극단 탐욕. "
           "미국 종목은 미국 점수, 한국 종목은 한국 점수를 씁니다.")

market = st.segmented_control("시장", ["미국", "한국"], default="미국", key="sent_market", label_visibility="collapsed") or "미국"
try:
    with st.spinner("지표를 불러오는 중…"):
        raw, src = state.sentiment_raw(market)
        res = sentiment.compute(market, raw)
except Exception as ex:  # noqa: BLE001
    st.error(f"자료를 불러오지 못했습니다: {ex}")
    st.stop()

if res.score is None:
    st.info(f"점수를 계산할 자료가 부족합니다. {res.message}", icon=":material/hourglass_empty:")
else:
    how = "1회에 전부" if res.times == 1 else f"{res.times}회, {res.weeks}주 간격"
    ui.kpis([("심리 점수", f"{res.score:.1f}", res.band), ("신규 매수", how), ("기준일", str(res.last_date), "5년 창")])
    if res.message != "이상 없음":
        st.warning(res.message, icon=":material/warning:")

FEAR = {"vix": "높을수록 공포", "vkospi": "높을수록 공포", "baa": "넓을수록 공포", "spread": "넓을수록 공포", "ma": "낮을수록 공포", "credit": "줄어들수록 공포"}
PCT = {"ma", "credit"}
SOURCE_KEYS = {"vix": ["vix"], "baa": ["baa"], "ma": ["sp500", "kospi"], "vkospi": ["vkospi"], "spread": ["aa", "ktb"], "credit": ["credit"]}
rows = []
for ind in res.indicators or [{"key": k, "label": lab} for k, lab, *_ in sentiment.MARKETS[market]["indicators"]]:
    v = ind.get("latest")
    rows.append({
        "지표": ind["label"],
        "최신값": (fmt.pct(v, 2) if ind["key"] in PCT else f"{v:,.2f}") if v is not None else "–",
        "5년 백분위": ind.get("pct"),
        "공포 방향": FEAR[ind["key"]],
        "탐욕 쪽 점수": ind.get("greed"),
        "최종 자료일": str(ind.get("last_date") or "–"),
        "출처": ", ".join(dict.fromkeys(src.get(k, "") for k in SOURCE_KEYS[ind["key"]] if src.get(k))),
    })
st.dataframe(
    pd.DataFrame(rows),
    hide_index=True,
    column_order=["지표", "최신값", "탐욕 쪽 점수", "5년 백분위", "최종 자료일", "공포 방향", "출처"],
    column_config={
        "5년 백분위": st.column_config.NumberColumn("5년 백분위(값)", format="%.0f"),
        "탐욕 쪽 점수": st.column_config.ProgressColumn("탐욕 쪽 점수", min_value=0, max_value=100, format="%.0f", help="공포 방향을 뒤집은 백분위"),
        "출처": st.column_config.TextColumn("출처", width="medium"),
    },
)
st.caption(ui.md("계산: 지표별 최근 5년 백분위(공포 방향은 100에서 뺌) → 평균 → 그 평균의 5년 백분위. "
                 "구간: 10 미만 1회 / 10~30 2회·2주 / 30~70 2회·4주 / 70~90 3회·4주 / 90 이상 4회·4주."))

if market == "한국":
    with st.expander("한국 자료 올리기(CSV)"):
        st.markdown(
            "- **VKOSPI**: KRX 정보데이터시스템 → 지수 → 파생상품지수 → 개별지수 시세 추이(코스피 200 변동성지수), 일별 지수\n"
            "- **회사채 AA- 3년 / 국고채 3년**: 한국은행 ECOS 817Y002 시장금리(일별), 연 %. `ECOS_API_KEY`가 있으면 자동\n"
            "- **신용융자잔고**: 금융투자협회 FreeSIS → 신용공여 잔고 추이 → 신용거래융자 전체(유가증권+코스닥), 일별\n"
            "- 코스피는 시세에서 자동. 최근 6년 이상을 올리세요."
        )
        labels = {"kr_vkospi": "VKOSPI", "kr_aa": "회사채 AA- 3년", "kr_ktb": "국고채 3년", "kr_credit": "신용융자잔고"}
        which = st.selectbox("올릴 지표", list(labels), format_func=labels.get)
        have = csvin.from_frame(store.read(which))
        st.caption(f"저장된 자료: {len(have)}일" + (f", {have[0][0]} ~ {have[-1][0]}" if have else ""))
        up = st.file_uploader("CSV 파일", type=["csv"], key=f"up_{which}")
        if up is not None:
            try:
                df = csvin.read_table(up.getvalue())
            except ValueError as ex:
                st.error(str(ex))
                st.stop()
            if csvin.is_wide(df):
                row = st.selectbox("쓸 줄(가로형 표)", range(len(df)), format_func=lambda i: " · ".join(str(x) for x in df.iloc[i, :3]))
                series = csvin.wide_series(df, row)
            else:
                dcols = csvin.date_columns(df) or list(df.columns)
                dcol = st.selectbox("날짜 열", dcols)
                vcol = st.selectbox("값 열", [c for c in df.columns if c != dcol])
                series = csvin.long_series(df, dcol, vcol)
            if series:
                st.caption(f"읽은 자료: {len(series)}일, {series[0][0]} ~ {series[-1][0]}, 마지막 값 {series[-1][1]:,}")
                if st.button("이 자료로 저장", type="primary"):
                    state.flash(store.write(which, csvin.to_frame(series)))
                    st.rerun()
            else:
                st.warning("날짜와 숫자를 읽지 못했습니다. 열을 다시 고르세요.")
