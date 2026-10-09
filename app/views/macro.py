"""거시 참고(사전 4): 표시만 한다. 어떤 규칙의 입력도 아니고 합산 점수도 없다."""

import pandas as pd
import streamlit as st

from app import fmt, state
from judge import macro

state.header()
st.title("거시 참고")
st.caption("표시만 합니다. 어떤 규칙의 입력도 아니고, 합산 점수도 만들지 않습니다. 10년 백분위: 0 = 최근 10년 중 가장 낮음, 100 = 가장 높음.")

try:
    with st.spinner("FRED에서 불러오는 중…"):
        items = macro.panel(state.macro_raw())
except Exception as ex:  # noqa: BLE001
    st.error(f"자료를 불러오지 못했습니다: {ex}")
    st.stop()



def raw(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 1e4 else f"{v:,.2f}"


def used(it) -> str:
    """현재값을 계산할 때 쓴 원자료(날짜 원값). 월별 자료는 연-월만."""
    day = (lambda d: f"{d:%Y-%m}") if it["key"] in macro.MONTHLY else (lambda d: f"{d:%Y-%m-%d}")
    parts = [f"{day(d)} {raw(v)}" for d, v in it["basis"]]
    if len(parts) < 2:
        return parts[0] if parts else "–"
    op = " − " if it["key"] == "dgs10" else " ÷ "
    return parts[0] + op + parts[1] + ("" if it["key"] == "dgs10" else " − 1")


rows = []
for it in items:
    v = it["current"]
    shown = "–" if v is None else (f"{v:+.2f}%p" if it["key"] == "dgs10" else f"{v:.2f}%p" if it["unit"] == "%p" else fmt.pct(v, 1, sign=True))
    rows.append({"지표": it["label"], "보는 것": it["what"], "현재값": shown, "10년 백분위": it["pct"], "기준일": str(it["last_date"] or "–"),
                 "계산에 쓴 값": used(it), "점검": it["issues"], "출처": it["source"]})
st.dataframe(
    pd.DataFrame(rows),
    hide_index=True,
    column_order=["지표", "현재값", "10년 백분위", "기준일", "계산에 쓴 값", "보는 것", "점검", "출처"],
    column_config={
        "10년 백분위": st.column_config.ProgressColumn("10년 백분위", min_value=0, max_value=100, format="%.0f"),
        "지표": st.column_config.TextColumn("지표", width="small"),
        "계산에 쓴 값": st.column_config.TextColumn("계산에 쓴 값", help="FRED 원값. 출처 숫자와 대조할 때 씀"),
    },
)
st.caption("미 10년물 3개월 변화 = 오늘 − 3개월 전(%p). 엔/달러 변화율이 음수면 엔화 강세. 한국 수출 전년비 = 이번 달 ÷ 1년 전 같은 달 − 1"
           "(월별 자료라 기준일은 그달 1일로 표시됨). 기준일이 오래되었으면 FRED 쪽 갱신이 늦거나 멈춘 것입니다.")
