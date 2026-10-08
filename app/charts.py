"""앱 차트(plotly). 색은 검증한 두 계열(파랑=포트폴리오·주가, 주황=비교 지수)과 강조용 회색만 쓴다."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

LIGHT = {"s1": "#2a78d6", "s2": "#eb6834", "grid": "#e1e0d9", "axis": "#c3c2b7", "muted": "#898781", "ink": "#52514e", "dim": "#c3c2b7"}
DARK = {"s1": "#3987e5", "s2": "#d95926", "grid": "#2c2c2a", "axis": "#383835", "muted": "#898781", "ink": "#c3c2b7", "dim": "#5c5b56"}
FONT = 'system-ui, -apple-system, "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif'
CONFIG = {"displayModeBar": False, "scrollZoom": False}


def _c(dark: bool) -> dict:
    return DARK if dark else LIGHT


def _layout(fig: go.Figure, dark: bool, height: int = 300, yfmt: str | None = None, legend: bool = False) -> go.Figure:
    c = _c(dark)
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=c["ink"]),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
        hoverlabel=dict(font=dict(family=FONT)),
        dragmode=False,
    )
    axis = dict(showgrid=True, gridcolor=c["grid"], gridwidth=1, zeroline=False, linecolor=c["axis"], tickfont=dict(color=c["muted"]), fixedrange=True)
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    fig.update_xaxes(showgrid=False, showline=True)
    if yfmt:
        fig.update_yaxes(tickformat=yfmt)
    return fig


def price_line(close: pd.Series, name: str, dark: bool = False) -> go.Figure:
    c = _c(dark)
    fig = go.Figure(go.Scatter(x=close.index, y=close.values, mode="lines", name=name, line=dict(color=c["s1"], width=2), hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f}<extra></extra>"))
    fig.update_layout(hovermode="x")
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikecolor=c["muted"], spikedash="solid")
    return _layout(fig, dark)


def weights_bar(names: list[str], weights: list[float], highlight: set, limit: float | None, dark: bool = False) -> go.Figure:
    """비중 가로 막대. highlight에 든 종목만 파랑, 나머지는 회색(강조)."""
    c = _c(dark)
    colors = [c["s1"] if n in highlight or not highlight else c["dim"] for n in names]
    fig = go.Figure(
        go.Bar(
            y=names, x=weights, orientation="h", marker=dict(color=colors, cornerradius=4, line=dict(width=0)),
            text=[f"{w:.0%}" for w in weights], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{x:.1%}<extra></extra>",
        )
    )
    if limit is not None:
        fig.add_vline(x=limit, line=dict(color=c["muted"], width=1))
        fig.add_annotation(x=limit, y=1, yref="paper", text=f"{limit:.0%} 한도", showarrow=False, xanchor="left", yanchor="bottom", font=dict(color=c["muted"], size=11))
    fig.update_layout(bargap=0.35)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(range=[0, max([*weights, limit or 0]) * 1.25 or 1], tickformat=".0%")
    _layout(fig, dark, height=80 + 36 * len(names), yfmt=None)
    fig.update_layout(margin=dict(l=8, r=8, t=26 if limit is not None else 8, b=8))
    return fig


def growth_lines(values: pd.DataFrame, dark: bool = False) -> go.Figure:
    """월말 평가액. 열: 포트폴리오, (비교 지수)."""
    c = _c(dark)
    fig = go.Figure()
    for col, color in zip(values.columns, (c["s1"], c["s2"])):
        s = values[col]
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name=col, line=dict(color=color, width=2), hovertemplate=f"{col}: %{{y:,.0f}}<extra></extra>"))
        fig.add_annotation(x=s.index[-1], y=s.iloc[-1], text=col, showarrow=False, xanchor="left", xshift=4, font=dict(color=c["ink"], size=11))
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikecolor=c["muted"], spikedash="solid")
    fig.update_layout(margin=dict(l=8, r=70, t=28, b=8))
    return _layout(fig, dark, legend=len(values.columns) > 1, yfmt=",.0f")


def drawdown_area(dd: pd.Series, dark: bool = False) -> go.Figure:
    c = _c(dark)
    fig = go.Figure(go.Scatter(x=dd.index, y=dd.values, mode="lines", fill="tozeroy", line=dict(color=c["s1"], width=2), fillcolor="rgba(42,120,214,0.15)", hovertemplate="%{x|%Y-%m}: %{y:.1%}<extra></extra>"))
    fig.update_layout(hovermode="x")
    return _layout(fig, dark, height=220, yfmt=".0%")


def annual_bars(annual: pd.DataFrame, dark: bool = False) -> go.Figure:
    """연도별 수익률. 열: 포트폴리오, (비교 지수)."""
    c = _c(dark)
    fig = go.Figure()
    for col, color in zip(annual.columns, (c["s1"], c["s2"])):
        fig.add_trace(go.Bar(x=[str(y) for y in annual.index], y=annual[col].values, name=col, marker=dict(color=color, cornerradius=4), hovertemplate=f"{col} %{{x}}: %{{y:.1%}}<extra></extra>"))
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    fig.add_hline(y=0, line=dict(color=c["axis"], width=1))
    return _layout(fig, dark, height=260, yfmt=".0%", legend=len(annual.columns) > 1)
