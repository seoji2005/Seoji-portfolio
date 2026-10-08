"""자료 계층의 공통 모양. 금액은 모두 현지 통화 원 단위(원, 달러)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class Fundamentals:
    """한 회사의 재무(명세 1·2에 필요한 것만)."""

    as_of: dt.date | None = None  # 재무상태표 기준일(최근 분기말)
    net_income: float | None = None  # 최근 1년(TTM) 당기순이익
    equity: float | None = None  # 자본총계
    liabilities: float | None = None  # 부채총계
    op_income: float | None = None  # 최근 1년 영업이익
    revenue: float | None = None  # 최근 1년 매출
    revenue_3y_ago: float | None = None  # 3년 전 같은 1년 매출
    debt: float | None = None  # 이자부부채
    cash: float | None = None  # 현금성자산
    debt_parts: dict = field(default_factory=dict)  # 이자부부채 구성(항목 → 금액)
    cash_parts: dict = field(default_factory=dict)
    source: str = ""  # 예: "SEC EDGAR 10-Q 2026-06-30"
    notes: list = field(default_factory=list)  # 계산하며 생긴 알림(결측 이유 등)


@dataclass
class Quote:
    price: float | None = None
    previous_close: float | None = None
    market_cap: float | None = None
    currency: str = ""


@dataclass
class Profile:
    name: str = ""
    sector: str = ""
    industry: str = ""
