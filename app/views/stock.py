"""종목 상세: 시세, 판정, 점수 설명 카드, 차트, 재무 근거, 포트폴리오에 넣으면?"""

import pandas as pd
import streamlit as st

from app import charts, fmt, state, ui
from judge.common import IMPL, SPEC
from judge.portfolio import Position, shares, what_if
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
if r.decision == "편입 후보":
    st.success(f"**편입 후보** — 점수 {r.score:.1f} (기준 {SPEC['candidate_score']}점 이상). {r.summary}", icon=":material/thumb_up:")
elif r.decision.startswith("교체 제안"):
    st.warning(f"**{r.decision}** — 보유 종목 점수 {SPEC['replace_below']}점 미만이고 같은 국가에 {SPEC['replace_gap']}점 이상 높은 후보가 있습니다.", icon=":material/swap_horiz:")
elif r.filter_reasons:
    st.warning(f"**거름망 제외** — {', '.join(r.filter_reasons)}. 점수를 매기지 않습니다.", icon=":material/filter_alt_off:")
elif not r.scored:
    st.info(f"**{r.status}** — 지표를 모두 계산할 수 있어야 점수를 매깁니다.", icon=":material/help:")
else:
    st.info(f"**{r.decision or '편입 기준 미달'}** — 점수 {r.score:.1f}. {r.summary}", icon=":material/info:")

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
    st.markdown(
        f"- 재무 출처: {f.source or '–'} (기준일 {f.as_of or '–'})\n"
        f"- 이자부부채 구성: {', '.join(f'{k} {v / unit:,.0f}' for k, v in f.debt_parts.items()) or '없음'}\n"
        f"- 현금성자산 구성: {', '.join(f'{k} {v / unit:,.0f}' for k, v in f.cash_parts.items()) or '없음'}\n"
        f"- 부채비율: {fmt.pct(r.debt_ratio, 0)} (한도 {SPEC['debt_ratio_max']:.0%})\n"
        f"- 주가 기준일 {asof or '–'}: 12개월 전 {fmt.price(p12, country)}, 1개월 전 {fmt.price(p1, country)}\n"
        f"- 금융·리츠 판단: {d.fin_reason}"
    )
    for note in f.notes + d.notes:
        st.caption(f"· {note}")

# 포트폴리오에 넣으면?
st.subheader("포트폴리오에 넣으면?")
amount = st.number_input("살 금액(원)", min_value=0, value=1_000_000, step=500_000, format="%d")
if amount > 0:
    try:
        b = state.book()
    except Exception as ex:  # noqa: BLE001
        st.error(f"포트폴리오를 계산하지 못했습니다: {ex}")
        st.stop()
    add = Position(country, code, d.name, float(amount), r.score if r.scored else None, r.summary)
    w = what_if(b.positions, b.cash, add)
    before, after = w["before"], w["after"]
    held = [p for p in w["positions_after"] if p.value_krw > 0]
    share = shares(held, w["cash_after"])
    ui.kpis([
        ("포트폴리오 점수", fmt.score(after.total), ui.change(after.total, before.total)),
        ("이 종목 비중", fmt.pct(share.get(code)), "개별 몫 대비"),
        ("개별 종목 수", f"{w['count_after']}개", "명세: 3~5개"),
    ])
    if w["concentration_after"]:
        for name, weight, excess in w["concentration_after"]:
            st.warning(f"{name} 비중 {weight:.0%} — 개별 몫(주식+대기 현금)의 40%를 넘습니다(초과 {fmt.won(excess)}).", icon=":material/warning:")
    if w["new_money"] > 0:
        st.caption(f"대기 현금 {fmt.won(b.cash)}보다 많아서 {fmt.won(w['new_money'])}은 새 돈으로 봤습니다.")
    if not r.scored:
        st.caption("이 종목은 점수가 없어 포트폴리오 점수 계산에서 빠집니다.")
    st.plotly_chart(charts.weights_bar([p.name for p in held], [share[p.code] for p in held], {d.name}, SPEC["conc_max"], dark), config=charts.CONFIG)
    st.caption(f"비중 = 개별 몫(주식 + 남은 대기 현금 {fmt.won(w['cash_after'])}) 대비. 40% 규칙은 3종목 이상일 때 적용.")
    if st.button("이 구성으로 과거 성과 보기", icon=":material/history:"):
        st.session_state["bt_add"] = (country, code, float(amount))
        st.switch_page("app/views/backtest.py")
