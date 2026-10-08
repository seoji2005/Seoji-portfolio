"""작은 화면용 표시 조각: 숫자 타일 한 줄."""

from __future__ import annotations

import html

import streamlit as st

CSS = """
<style>
.kpis{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px}
.kpi{flex:1 1 0;min-width:96px;padding:8px 10px;border:1px solid rgba(128,128,128,.28);border-radius:8px}
.kpi .l{font-size:.75rem;opacity:.72;line-height:1.3}
.kpi .v{font-size:1.15rem;font-weight:600;line-height:1.35;word-break:keep-all}
.kpi .s{font-size:.75rem;opacity:.72;line-height:1.3}
</style>
"""


def kpis(items: list[tuple]) -> None:
    """items: (이름, 값[, 보조 문구]). 좁은 화면에서는 줄바꿈된다."""
    cells = []
    for item in items:
        label, value, sub = (list(item) + [None])[:3]
        sub_html = f'<div class="s">{html.escape(str(sub))}</div>' if sub not in (None, "") else ""
        cells.append(f'<div class="kpi"><div class="l">{html.escape(str(label))}</div><div class="v">{html.escape(str(value))}</div>{sub_html}</div>')
    st.markdown(CSS + '<div class="kpis">' + "".join(cells) + "</div>", unsafe_allow_html=True)


def change(after: float | None, before: float | None, digits: int = 1) -> str:
    if after is None or before is None:
        return ""
    d = after - before
    return f"{'▲' if d > 0 else '▼' if d < 0 else '–'} {abs(d):.{digits}f} (전 {before:.{digits}f})"
