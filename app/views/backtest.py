"""과거 성과(명세 9): 포트폴리오를 과거 월별 자료로 돌려 본다. Portfolio Visualizer처럼. 표시만 한다."""

import pandas as pd
import streamlit as st

from app import charts, fmt, state, ui
from judge import backtest
from market import yahoo

state.header()
st.title("과거 성과")
st.caption("배당 재투자(수정주가), 월말 기준. 과거 성과는 미래를 보장하지 않으며, 어떤 매매 규칙의 입력도 아닙니다.")

BENCH = {"S&P 500 (SPY)": "SPY", "코스피 200 (KODEX 200)": "069500.KS", "없음": None}

try:
    b = state.book()
except Exception as ex:  # noqa: BLE001
    st.error(f"자료를 불러오지 못했습니다: {ex}")
    st.stop()


def holdings_table(extra=None) -> pd.DataFrame:
    vals = {}
    names = {}
    for p in b.positions:
        d = state.find(p.country, p.code)
        sym = d.symbol if d else yahoo.symbol(p.country, p.code)
        vals[sym] = vals.get(sym, 0) + p.value_krw
        names[sym] = p.name
    if extra:
        country, code, amount = extra
        d = state.find(country, code)
        sym = d.symbol if d else yahoo.symbol(country, code)
        vals[sym] = vals.get(sym, 0) + amount
        names[sym] = d.name if d else code
    total = sum(vals.values())
    return pd.DataFrame([{"심볼": s, "이름": names[s], "비중(%)": round(v / total * 100, 1)} for s, v in vals.items()]) if total > 0 else pd.DataFrame(columns=["심볼", "이름", "비중(%)"])


add = st.session_state.get("bt_add")
sources = ["내 포트폴리오"] + (["포트폴리오 + 추가 종목"] if add else []) + ["직접 입력"]
source = st.segmented_control("구성", sources, default=sources[1] if add else sources[0], key="bt_source") or sources[0]
if source == "내 포트폴리오":
    base = holdings_table()
elif source == "포트폴리오 + 추가 종목":
    d = state.find(add[0], add[1])
    st.caption(f"추가: {d.name if d else add[1]} {fmt.won(add[2])}")
    base = holdings_table(add)
else:
    base = pd.DataFrame([{"심볼": "SPY", "이름": "S&P 500 ETF", "비중(%)": 50.0}, {"심볼": "069500.KS", "이름": "KODEX 200", "비중(%)": 50.0}])
if base.empty:
    st.info("보유 종목이 없어 '직접 입력'으로 구성을 만들어 보세요.")
    base = pd.DataFrame([{"심볼": "SPY", "이름": "S&P 500 ETF", "비중(%)": 100.0}])

st.caption("심볼은 Yahoo 형식: 미국 AAPL, 코스피 005930.KS, 코스닥 247540.KQ, ETF SPY·069500.KS")
assets = st.data_editor(base, num_rows="dynamic", hide_index=True, key=f"bt_assets_{source}",
                        column_config={"비중(%)": st.column_config.NumberColumn("비중(%)", min_value=0.0, max_value=100.0, step=1.0)})
c1, c2, c3 = st.columns(3)
years = c1.selectbox("기간", [3, 5, 10, 15, 20], index=2, format_func=lambda y: f"최근 {y}년")
rebalance = c2.selectbox("리밸런싱", ["none", "annual"], format_func={"none": "안 함", "annual": "매년"}.get)
bench_label = c3.selectbox("비교", list(BENCH), index=0)
krw = st.toggle("원화 기준(미국 자산에 환율 반영)", value=True)

assets = assets.dropna(subset=["심볼"])
assets = assets[assets["심볼"].astype(str).str.strip() != ""]
weights = {str(r["심볼"]).strip(): float(r["비중(%)"] or 0) for _, r in assets.iterrows()}
weights = {k: v for k, v in weights.items() if v > 0}
if not weights:
    st.stop()
bench = BENCH[bench_label]
symbols = list(weights) + ([bench] if bench else [])

with st.spinner("과거 주가를 불러오는 중…"):
    hist = state.provider().histories(symbols + [yahoo.FX_USDKRW])
missing = [s for s in symbols if hist.get(s) is None or hist[s].empty]
if missing:
    st.error(f"주가를 찾지 못한 심볼: {', '.join(missing)}")
    st.stop()

prices = pd.DataFrame({s: hist[s]["adj_close"] for s in symbols})
start = prices.index.max() - pd.DateOffset(years=years)
prices = prices[prices.index >= start]
if krw:
    usd = [s for s in symbols if not s.endswith((".KS", ".KQ"))]
    prices = backtest.to_krw(prices, usd, hist[yahoo.FX_USDKRW]["close"])
initial = 10_000_000 if krw else 10_000
money = fmt.won if krw else fmt.usd

try:
    res = backtest.run(prices, weights, rebalance, initial)
except ValueError as ex:
    st.error(str(ex))
    st.stop()
series = {"포트폴리오": res.values}
bres = None
if bench:
    bp = prices[[bench]][prices.index >= res.values.index[0].replace(day=1)]
    bres = backtest.run(bp, {bench: 1}, "none", initial)
    series["비교 지수"] = bres.values
s = res.stats
if s["start"] > start.date() + pd.Timedelta(days=40):
    st.caption(f"모든 자산의 자료가 있는 {s['start']:%Y-%m}부터 계산했습니다.")

bs = bres.stats if bres else {}


def vs(key, pct=True):
    if not bres or bs.get(key) is None:
        return ""
    return f"비교 {fmt.pct(bs[key]) if pct else f'{bs[key]:.2f}'}"


ui.kpis([
    ("연평균 수익률", fmt.pct(s["cagr"]), vs("cagr")),
    ("변동성(연)", fmt.pct(s["vol"]), vs("vol")),
    ("최대 낙폭", fmt.pct(s["mdd"]), vs("mdd")),
    ("샤프 비율", "–" if s["sharpe"] is None else f"{s['sharpe']:.2f}", vs("sharpe", pct=False)),
])
st.caption(f"{s['start']:%Y-%m} → {s['end']:%Y-%m}, 시작 {money(initial)} → {money(s['final'])}. '비교'는 비교 지수 값. 샤프 비율은 무위험 수익률 0으로 계산.")

dark = state.dark()
values = pd.DataFrame(series)
st.subheader("평가액")
st.plotly_chart(charts.growth_lines(values, dark), config=charts.CONFIG)
st.subheader("고점 대비 낙폭")
st.plotly_chart(charts.drawdown_area(res.drawdown, dark), config=charts.CONFIG)
st.subheader("연도별 수익률")
annual = pd.DataFrame({"포트폴리오": res.annual} | ({"비교 지수": bres.annual} if bres else {}))
st.plotly_chart(charts.annual_bars(annual, dark), config=charts.CONFIG)

with st.expander("표로 보기"):
    summary = pd.DataFrame(
        {
            "포트폴리오": [fmt.pct(s["cagr"]), fmt.pct(s["vol"]), fmt.pct(s["mdd"]), "–" if s["sharpe"] is None else f"{s['sharpe']:.2f}",
                         f"{s['best_year'][0]} {fmt.pct(s['best_year'][1])}", f"{s['worst_year'][0]} {fmt.pct(s['worst_year'][1])}", money(s["final"])],
        }
        | ({"비교 지수": [fmt.pct(bs["cagr"]), fmt.pct(bs["vol"]), fmt.pct(bs["mdd"]), "–" if bs["sharpe"] is None else f"{bs['sharpe']:.2f}",
                      f"{bs['best_year'][0]} {fmt.pct(bs['best_year'][1])}", f"{bs['worst_year'][0]} {fmt.pct(bs['worst_year'][1])}", money(bs["final"])]} if bres else {}),
        index=["연평균 수익률", "변동성(연)", "최대 낙폭", "샤프 비율", "최고 연도", "최저 연도", "최종 평가액"],
    )
    st.dataframe(summary)
    st.dataframe(annual.map(fmt.pct).rename_axis("연도"))
