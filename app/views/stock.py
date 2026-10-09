"""종목 카드(사전 출력): 거름망 결과, 지표 값·풀 내 위치, 한 줄 요약, 참고 근거, 매수 이유 카드 상태. 주가 차트와 재무 출처."""

import pandas as pd
import streamlit as st

from app import charts, fmt, state, store, ui
from judge.common import IMPL, SPEC
from judge.evidence import KINDS
from judge.reasons import card
from judge.stocks import METRICS
from market.pool import UNIT, UNIT_NAME, momentum_prices

state.header()

try:
    pools = state.pool()
except Exception as ex:  # noqa: BLE001
    st.error(f"자료를 불러오지 못했습니다: {ex}")
    st.stop()

options = [(c, d.entry.code) for c in ("미국", "한국") for d in pools.get(c, ([], None))[0]]
if not options:
    st.info("관심 종목이 없습니다. 관심 종목 화면에서 추가하세요.")
    st.stop()
labels = {(c, d.entry.code): f"{c} · {d.name} ({d.entry.code})" for c in ("미국", "한국") for d in pools[c][0]}
qp = st.query_params
chosen = (qp.get("country"), qp.get("code"))
if chosen not in labels:
    chosen = st.session_state.get("stock") if st.session_state.get("stock") in labels else options[0]
picked = st.selectbox("종목", options, index=options.index(chosen), format_func=labels.get, label_visibility="collapsed")
if picked != chosen:
    st.query_params.update(country=picked[0], code=picked[1])
st.session_state["stock"] = picked
country, code = picked
d = state.find(country, code)
r, q, f = d.result, d.quote, d.fundamentals
dark = state.dark()

st.title(d.name)
st.caption(f"{d.symbol} · {d.profile.industry or '업종 정보 없음'} · {'보유 중' if d.held else '미보유'}")

chg = (q.price / q.previous_close - 1) if q.price and q.previous_close else None
n_pool = sum(1 for x in pools[country][0] if x.result.scored)
ui.kpis([
    ("현재가", fmt.price(q.price, country), f"오늘 {fmt.pct(chg, 2, sign=True)}" if chg is not None else ""),
    ("시가총액", fmt.money(q.market_cap, country)),
    ("점수", fmt.score(r.score), f"{country} {n_pool}종목 중" if r.scored else "점수 없음"),
])

# 판정
if d.data_problem:
    st.error(f"**재무 자료를 받지 못해 점수를 매길 수 없습니다** — {d.data_problem}", icon=":material/cloud_off:")
elif r.decision == "편입 후보":
    st.success(f"**편입 후보** — 점수 {r.score:.1f} (기준 {SPEC['candidate_score']}점 이상). {r.summary}", icon=":material/thumb_up:")
elif r.decision.startswith("교체 제안"):
    st.warning(f"**{r.decision}** — 보유 종목 점수 {SPEC['replace_below']}점 미만이고 같은 국가에 {SPEC['replace_gap']}점 이상 높은 후보가 있습니다.", icon=":material/swap_horiz:")
elif r.filter_reasons:
    st.warning(f"**거름망 제외** — {', '.join(r.filter_reasons)}. 점수를 매기지 않습니다.", icon=":material/filter_alt_off:")
elif not r.scored:
    st.info(f"**{r.status}** — 지표를 모두 계산할 수 있어야 점수를 매깁니다." + (f" {d.mom_block}" if d.mom_block else ""), icon=":material/help:")
else:
    st.info(f"**{r.decision or '편입 기준 미달'}** — 점수 {r.score:.1f}. {r.summary}", icon=":material/info:")

# 거름망 결과와 매수 이유 카드 상태
s0 = d.stock
checks = [
    ("최근 1년 영업이익 흑자", s0.op_income is not None and s0.op_income > 0, fmt.money(s0.op_income * UNIT[country], country) if s0.op_income is not None else "자료 없음"),
    ("부채비율 200% 이하", r.debt_ratio is not None and r.debt_ratio <= SPEC["debt_ratio_max"], fmt.pct(r.debt_ratio, 0) if r.debt_ratio is not None else "자료 없음"),
    (f"시총 {'5천억 원' if country == '한국' else '20억 달러'} 이상", s0.market_cap is not None and s0.market_cap >= SPEC["mcap_min"][country],
     fmt.money(s0.market_cap * UNIT[country], country) if s0.market_cap is not None else "자료 없음"),
    ("금융·리츠 아님", not d.fin, d.fin_reason),
]
st.markdown(ui.md("**거름망** — " + ("통과" if not r.filter_reasons else "제외: " + ", ".join(r.filter_reasons)) + "  \n" +
                  " · ".join(f"{'✓' if ok else '✗'} {name} ({val})" for name, ok, val in checks)))
cd = card(code, state.reason_items())
st.markdown(f"**매수 이유 카드** — {cd.status or ('없음' if not cd.items else '상태 미선택')}" + ("" if cd.buy_ok else f" · {cd.buy_why}"))
st.session_state["card_code"] = code  # 카드 화면이 이 종목으로 열리게
st.page_link("app/views/reasons.py", label="매수 이유 카드 열기", icon=":material/fact_check:")

# 점수 설명 카드
st.subheader("점수 설명")
rows = []
for key, label, *_ in METRICS:
    v = r.metrics[key]
    rows.append(
        {
            "지표": label,
            "값": fmt.pct(v) if v is not None else "결측",
            "위치": f"상위 {r.top[key]:.0f}%" if r.scored else "–",
            "백분위": r.pct.get(key),
        }
    )
st.dataframe(
    pd.DataFrame(rows),
    hide_index=True,
    column_config={
        "지표": st.column_config.TextColumn("지표", width="small"),
        "값": st.column_config.TextColumn("값", width="small"),
        "위치": st.column_config.TextColumn("풀 안 위치", width="small"),
        "백분위": st.column_config.ProgressColumn("백분위", min_value=0, max_value=100, format="%.0f", width="small"),
    },
)
st.caption(
    "ROE = 순이익 ÷ 자본 · 매출성장률 = 3년 연평균 · 이익수익률 = 영업이익 ÷ (시총 + 이자부부채 − 현금성자산) · "
    f"12-1 = 12개월 전 → 1개월 전 주가 수익률. 점수 = 네 백분위 평균의 풀 안 백분위. 요약은 백분위 {IMPL['strong_pct']} 이상 강점, {IMPL['weak_pct']} 미만 약점."
)

# 차트
st.subheader("주가")
period = st.pills("기간", ["1년", "3년", "5년", "10년", "전체"], default="3년", key="px_period", label_visibility="collapsed") or "3년"
close = d.history["close"] if not d.history.empty else pd.Series(dtype=float)
if close.empty:
    st.info("주가 자료가 없습니다.")
else:
    if period != "전체":
        years = int(period.removesuffix("년"))
        close = close[close.index >= close.index[-1] - pd.DateOffset(years=years)]
    st.plotly_chart(charts.price_line(close, d.name, dark), config=charts.CONFIG)
    first, last = float(close.iloc[0]), float(close.iloc[-1])
    st.caption(f"{close.index[0]:%Y-%m-%d} → {close.index[-1]:%Y-%m-%d}: {fmt.pct(last / first - 1, 1, sign=True)} (분할 반영, 배당 제외)")
    with st.expander("표로 보기(월말 종가)"):
        m = close.resample("ME").last().dropna()
        st.dataframe(pd.DataFrame({"월": m.index.strftime("%Y-%m"), "종가": m.values}).iloc[::-1], hide_index=True)

# 재무 근거
with st.expander("점수에 쓴 숫자와 출처"):
    unit = UNIT[country]
    s = d.stock

    def u(v):
        return "–" if v is None else f"{v:,.0f}"

    p12, p1, asof = momentum_prices(d.history["close"]) if not d.history.empty else (None, None, None)
    table = [
        ("순이익(최근 1년)", s.net_income), ("자본총계", s.equity), ("부채총계", s.liabilities), ("영업이익(최근 1년)", s.op_income),
        ("매출(최근 1년)", s.revenue), ("매출(3년 전 1년)", s.revenue_3y_ago), ("시가총액", s.market_cap),
        ("이자부부채", s.debt), ("현금성자산", s.cash),
    ]
    st.dataframe(pd.DataFrame([(k, u(v)) for k, v in table], columns=["항목", f"금액({UNIT_NAME[country]})"]), hide_index=True)
    st.markdown(ui.md(
        f"- 재무 출처: {f.source or '–'} (기준일 {f.as_of or '–'})\n"
        f"- 이자부부채 구성: {', '.join(f'{k} {v / unit:,.0f}' for k, v in f.debt_parts.items()) or '없음'}\n"
        f"- 현금성자산 구성: {', '.join(f'{k} {v / unit:,.0f}' for k, v in f.cash_parts.items()) or '없음'}\n"
        f"- 부채비율: {fmt.pct(r.debt_ratio, 0)} (한도 {SPEC['debt_ratio_max']:.0%})\n"
        f"- 12-1 수익률(분할·병합 반영 종가, 현금배당 미반영, 기준일 {asof or '–'}): 12개월 전 {fmt.price(p12, country)}, 1개월 전 {fmt.price(p1, country)}"
        f"{' — ' + d.mom_block if d.mom_block else ''}\n"
        f"- 금융·리츠 판단: {d.fin_reason}"
    ))
    for note in f.notes + d.notes:
        st.caption(f"· {note}")

# 참고 근거(사전 8)
st.subheader("참고 근거")
st.caption("표시만 합니다. 점수·순위·매매 규칙에 반영하지 않습니다. 자료가 없으면 '미확인'이며, 다른 숫자로 대신 채우지 않습니다.")
try:
    with st.spinner("공시 자료를 확인하는 중…"):
        sections = state.evidence(d)
except Exception as ex:  # noqa: BLE001
    sections = []
    st.error(f"참고 근거를 불러오지 못했습니다: {ex}")
for sec_ in sections:
    st.markdown(f"**{sec_.title}**")
    for line in sec_.lines or ["미확인"]:
        st.markdown(ui.md(f"- {line}"))
    if sec_.note:
        st.caption(sec_.note)

with st.expander("확인한 근거 직접 넣기"):
    st.caption("출처(공시 링크·문서)와 기준일이 있는 확인된 사실만. 종류: " + " / ".join(KINDS) + ". 참고지수 비중은 비중(%) 칸에.")
    ev = store.read("evidence")
    mine = ev[ev["code"].astype(str) == code].drop(columns=["code"]).reset_index(drop=True)
    edited = st.data_editor(
        mine,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "kind": st.column_config.SelectboxColumn("종류", options=list(KINDS), required=True),
            "holder": st.column_config.TextColumn("누가(사람·운용자·기관·지수)", required=True),
            "detail": st.column_config.TextColumn("무엇을"),
            "weight_pct": st.column_config.TextColumn("비중(%)"),
            "as_of": st.column_config.TextColumn("기준일"),
            "source": st.column_config.TextColumn("출처", required=True),
        },
        key=f"ev_editor_{code}",
    )
    if st.button("근거 저장"):
        rest = ev[ev["code"].astype(str) != code]
        new = edited.dropna(how="all").fillna("").assign(code=code)
        state.flash(store.write("evidence", pd.concat([rest, new], ignore_index=True)[store.FILES["evidence"][1]]))
        st.rerun()
