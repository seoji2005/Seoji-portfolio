"""매수 이유 카드(사전 7). 점수가 아니다. 상태는 직접 점검해서 고른다."""

import datetime as dt

import pandas as pd
import streamlit as st

from app import state, store
from judge.reasons import STATUSES, ReasonItem, card, history

state.header()
st.title("매수 이유 카드")
st.caption(
    "종목마다 이유 1~3개. 이유마다 확인할 지표나 확인 가능한 사실·사건, 무너지는 조건(필요하면 기간), 상태를 적는다. "
    "카드 상태: 무너짐이 하나라도 있으면 무너짐 → 보류가 있으면 보류 → 모두 통과면 통과. 보류는 저절로 무너짐이 되지 않는다."
)

items = state.reason_items()
cards = {code: card(code, items) for code in dict.fromkeys(i.code for i in items)}
if items and not state._rows(store.read("cards")):
    st.info("이전 형식(my/reasons.csv)의 기록을 보여 주는 중입니다. 저장하면 새 형식(my/buy_reasons.csv)으로 남고, 이전 파일은 그대로 둡니다.")

# 한눈에 보기
if cards:
    names = {d.entry.code: d.name for c in ("미국", "한국") for d in state.pool()[c][0]} if items else {}
    st.dataframe(
        pd.DataFrame([{"종목": names.get(code, code), "카드 상태": c.status or "상태 미선택", "매수": "가능" if c.buy_ok else "불가", "이유 수": len(c.items),
                       "확인할 것": " · ".join(c.problems) or ""} for code, c in cards.items()]),
        hide_index=True,
        column_config={"확인할 것": st.column_config.TextColumn("확인할 것", width="large")},
    )

# 종목 하나 고치기
st.subheader("카드 고치기")
pools = state.pool()
choices = [(c, d.entry.code, d.name) for c in ("미국", "한국") for d in pools[c][0]]
if not choices:
    st.info("관심 종목이나 보유 종목을 먼저 넣으세요.")
    st.stop()
default = next((i for i, x in enumerate(choices) if x[1] == st.session_state.get("card_code")), 0)
country, code, name = st.selectbox("종목", choices, index=default, format_func=lambda x: f"{x[0]} · {x[2]} ({x[1]})")
st.session_state["card_code"] = code
c = card(code, items)
if c.items:
    msg = f"**카드 상태: {c.status or '상태 미선택'}** · 매수 {'가능' if c.buy_ok else '불가'}"
    (st.error if c.status == "무너짐" else st.warning if c.status in ("보류", "") else st.success)(msg)
if not c.buy_ok:
    st.warning(c.buy_why, icon=":material/block:")
for p in c.problems:
    st.caption(f"· {p}")

mine = pd.DataFrame([{"no": i.no, "reason": i.reason, "indicator": i.indicator, "fact": i.fact, "condition": i.condition, "period": i.period,
                      "status": i.status or None, "note": i.note, "checked": i.checked} for i in c.items],
                    columns=["no", "reason", "indicator", "fact", "condition", "period", "status", "note", "checked"])
edited = st.data_editor(
    mine,
    num_rows="dynamic",
    hide_index=True,
    column_config={
        "no": st.column_config.NumberColumn("번호", min_value=1, max_value=9, step=1, required=True),
        "reason": st.column_config.TextColumn("이유"),
        "indicator": st.column_config.TextColumn("확인 지표", help="숫자로 확인할 것. 예: 데이터센터 매출 전년비"),
        "fact": st.column_config.TextColumn("확인 사실·사건", help="확인 가능한 사실. 예: 핵심 고객과 장기 계약 공시"),
        "condition": st.column_config.TextColumn("무너지는 조건", help="예: 2회 연속 10% 미만 / 해지·미갱신"),
        "period": st.column_config.TextColumn("기간"),
        "status": st.column_config.SelectboxColumn("상태", options=list(STATUSES), required=True),
        "note": st.column_config.TextColumn("상태 근거"),
        "checked": st.column_config.TextColumn("점검일"),
    },
    key=f"card_editor_{code}",
)
why = st.text_input("바꾼 이유", help="확인 지표·사실·조건·기간을 바꾸거나 이유를 지울 때 필수. 이전 내용과 함께 이력으로 남는다.")
if st.button("카드 저장", type="primary"):
    new = []
    for _, r in edited.dropna(how="all").iterrows():
        if pd.isna(r.get("no")):
            continue
        new.append(ReasonItem(code, int(r["no"]), *(("" if pd.isna(r.get(k)) else str(r.get(k)).strip()) for k in
                                                   ("reason", "indicator", "fact", "condition", "period", "status", "note", "checked"))))
    bad = [i.no for i in new if i.status not in STATUSES]
    if bad:
        st.error(f"{bad}번 이유의 상태(통과/보류/무너짐)를 고르세요.")
        st.stop()
    try:
        rows = history(c.items, new, why, dt.date.today())
    except ValueError as ex:
        st.error(str(ex))
        st.stop()
    others = [i for i in items if i.code != code]
    all_rows = pd.DataFrame([vars(i) for i in others + new], columns=store.FILES["cards"][1]).astype(str)
    msgs = [store.write("cards", all_rows)]
    if rows:
        hist = pd.concat([store.read("reason_history"), pd.DataFrame(rows).astype(str)], ignore_index=True)
        msgs.append(store.write("reason_history", hist))
    state.flash(" / ".join(dict.fromkeys(msgs)))
    st.rerun()

hist = store.read("reason_history")
hist = hist[hist["code"].astype(str) == code]
with st.expander(f"조건 변경 이력 ({len(hist)}건)"):
    if hist.empty:
        st.caption("아직 없음")
    else:
        st.dataframe(hist.rename(columns={"changed_at": "날짜", "no": "번호", "field": "항목", "old": "이전", "new": "새 내용", "why": "바꾼 이유"})
                     .drop(columns=["code"]).iloc[::-1], hide_index=True)
