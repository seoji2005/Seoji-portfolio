"""9. 과거 성과 점검(2026-10-08 추가). Portfolio Visualizer처럼 월말 값으로 계산한다. 표시만 한다.

- 가격은 배당까지 반영한 수정주가(배당 재투자).
- 원화 기준이면 미국 자산에 원/달러 환율을 곱한다.
- 시작은 모든 자산의 자료가 있는 첫 달. 리밸런싱은 '안 함' 또는 '매년 12월 말'.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    values: pd.Series  # 월말 평가액(첫 값 = 시작 금액)
    stats: dict
    annual: pd.Series  # 연도별 수익률
    drawdown: pd.Series


def to_krw(prices: pd.DataFrame, usd_columns: list[str], usdkrw: pd.Series) -> pd.DataFrame:
    """미국 자산(달러)을 원화로. 환율은 그날 또는 직전 값."""
    out = prices.copy()
    if usd_columns:
        fx = usdkrw.sort_index().reindex(out.index.union(usdkrw.index)).ffill().reindex(out.index)
        for c in usd_columns:
            out[c] = out[c] * fx
    return out


def monthly(prices: pd.DataFrame) -> pd.DataFrame:
    """달마다 마지막 값. 모든 자산의 값이 있는 달부터."""
    m = prices.sort_index().ffill().resample("ME").last()
    return m.dropna(how="any")


def simulate(prices_m: pd.DataFrame, weights: dict, rebalance: str = "none", initial: float = 1.0) -> pd.Series:
    cols = [c for c in weights if weights[c] > 0]
    total = sum(weights[c] for c in cols)
    w = pd.Series({c: weights[c] / total for c in cols})
    p = prices_m[cols]
    units = w * initial / p.iloc[0]
    values = []
    for date, row in p.iterrows():
        v = float((units * row).sum())
        values.append(v)
        if rebalance == "annual" and date.month == 12:
            units = w * v / row
    return pd.Series(values, index=p.index)


def annual_returns(values: pd.Series) -> pd.Series:
    out, prev = {}, float(values.iloc[0])
    for year, v in values.groupby(values.index.year):
        last = float(v.iloc[-1])
        out[year] = last / prev - 1
        prev = last
    return pd.Series(out)


def stats(values: pd.Series) -> dict:
    r = values.pct_change().dropna()
    months = len(values) - 1
    dd = values / values.cummax() - 1
    vol = float(r.std(ddof=1) * math.sqrt(12)) if len(r) > 1 else None
    annual = annual_returns(values)
    return {
        "start": values.index[0].date(),
        "end": values.index[-1].date(),
        "months": months,
        "final": float(values.iloc[-1]),
        "cagr": (float(values.iloc[-1] / values.iloc[0]) ** (12 / months) - 1) if months > 0 else None,
        "vol": vol,
        "mdd": float(dd.min()),
        "sharpe": (float(r.mean()) * 12 / vol) if vol else None,  # 무위험 수익률 0으로 봄
        "best_year": (int(annual.idxmax()), float(annual.max())) if len(annual) else None,
        "worst_year": (int(annual.idxmin()), float(annual.min())) if len(annual) else None,
    }


def run(prices: pd.DataFrame, weights: dict, rebalance: str = "none", initial: float = 10_000_000) -> BacktestResult:
    m = monthly(prices[[c for c in weights if weights[c] > 0]])
    if len(m) < 2:
        raise ValueError("겹치는 기간이 두 달보다 짧음")
    values = simulate(m, weights, rebalance, initial)
    return BacktestResult(values, stats(values), annual_returns(values), values / values.cummax() - 1)
