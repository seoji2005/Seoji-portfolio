"""덜 채운 입력: 빈 칸, 종목 하나뿐인 풀, 빈 풀, 짧은 원자료, 계좌 평가액 0."""

import datetime as dt

from builder.v1_holdings import Account, BuyPlan, Holding, Reason
from judge.stocks import Stock

D = dt.date


def _days(n, end=D(2026, 9, 30)):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out[::-1]


def edge_data():
    good = dict(net_income=10, equity=100, liabilities=50, op_income=20, revenue=200, revenue_3y_ago=150,
                market_cap=9000, debt=10, cash=5, price_12m=100, price_1m=110)
    kr = [
        Stock("E1"),  # 코드만
        Stock("E2", "자본잠식", **{**good, "equity": 0}),
        Stock("E3", "하나뿐", held=True, **good),
        Stock("E4", "현금부자", **{**good, "market_cap": 5000, "debt": 0, "cash": 6000}),  # 기업가치 0 이하
        Stock("E5", "자료없음", held=True, **{**good, "revenue_3y_ago": None}),
        Stock("E6", "", **good),  # 이름 없는 후보(E3와 동점)
    ]
    days = _days(30)
    return {
        "price_date": D(2026, 9, 30),
        "stocks": {"한국": kr, "미국": []},
        "account": Account(total_krw=0, cash_krw=0, usdkrw=1300),
        "holdings": [
            Holding("한국", "E3", "하나뿐", qty=10, avg_price=0, cost_krw=None, price=100),
            Holding("미국", "Z9", "시트에없음", qty=1, avg_price=10, cost_krw=10_000, price=5, last_earnings=D(2026, 1, 1)),
            Holding("한국", "E5", "자료없음", qty=None, avg_price=100, cost_krw=1000, price=None),
            Holding("한국", "E7", "", qty=1, avg_price=1, cost_krw=1, price=1),
        ],
        "reasons": [
            Reason("E3", 1, "이유", True, "", ""),
            Reason("E7", 1, "실적일 없는 보유 종목", True, "근거", "기준"),  # 점검일도 실적일도 없음 → 안내 없음
        ],
        "plans": [
            BuyPlan("미국", "Q1", ""),
            BuyPlan("한국", "E3", "하나뿐", 1000, D(2026, 1, 1)),
        ],
        "sentiment": {
            "미국": {
                "sp500": [(d, 3000 + i) for i, d in enumerate(days)],
                "vix": [(d, 20 - i * 0.1) for i, d in enumerate(days)],
                "baa": [(d, ".") for d in days[:5]] + [(d, 2.0) for d in days[5:]],
            },
            "한국": {k: [] for k in ("kospi", "vkospi", "aa", "ktb", "credit")},
        },
        "macro": {
            "sahm": [(D(2026, m, 1), 0.1 * m) for m in range(1, 6)],
            "dgs10": [],
            "t10y3m": [(d, ".") for d in days],
            "jpy": [],
            "exports": [],
        },
    }
