"""예시 파일용 가상 데이터. 종목·숫자·원자료는 모두 지어낸 값이다.

같은 데이터로 시트(예시 파일)와 파이썬 기준 구현(judge)을 모두 계산해 결과를 대조한다.
"""

from __future__ import annotations

import datetime as dt
import math
import random

from builder.v1_holdings import Account, BuyPlan, Holding, Reason
from judge.stocks import Stock

D = dt.date
END = D(2026, 9, 30)


def _stock(code, name, held, fin, ni, eq, liab, op, rev, rev3, mcap, debt, cash, p12, p1):
    return Stock(
        code=code, name=name, held=held, excluded_sector=fin, basis="2026-2Q",
        net_income=ni, equity=eq, liabilities=liab, op_income=op, revenue=rev, revenue_3y_ago=rev3,
        market_cap=mcap, debt=debt, cash=cash, price_12m=p12, price_1m=p1,
    )


# 한국: 억 원, 원
KR = [
    _stock("K01", "예시전자", True, False, 1200, 8000, 4000, 1600, 12000, 8000, 15000, 1500, 2500, 50000, 62000),
    _stock("K02", "예시화학", True, False, 150, 9000, 9000, 300, 7000, 7500, 6000, 4000, 500, 30000, 24000),
    _stock("K03", "예시바이오", False, False, -250, 5000, 1000, -200, 800, 300, 20000, 0, 3000, 40000, 52000),
    _stock("K04", "예시은행", False, True, 3000, 30000, 300000, 4000, 20000, 17000, 25000, 0, 0, 10000, 11000),
    _stock("K05", "예시건설", False, False, 300, 5000, 13000, 700, 15000, 13000, 6000, 5000, 1500, 20000, 18000),
    _stock("K06", "예시식품", False, False, 200, 2000, 1000, 280, 4000, 3600, 3000, 300, 400, 15000, 16000),
    _stock("K07", "예시소프트", False, False, 900, 3000, 1200, 1100, 5000, 2500, 12000, 0, 1500, 20000, 31000),
    _stock("K08", "예시기계", False, False, 500, 6000, 5000, 750, 9000, 8000, 7000, 2000, 800, 25000, 26500),
    _stock("K09", "예시에너지", False, False, 700, 7000, 6000, 1000, 10000, 6000, 9000, 3000, 1000, None, 33000),
    _stock("K10", "예시소재", False, False, 650, 4500, 3000, 900, 6500, 5000, 8000, 1200, 900, 18000, 21000),
    _stock("K11", "예시로봇", False, False, 300, 2500, 1500, 400, 3000, 1200, 18000, 500, 1200, 30000, 45000),
    _stock("K12", "예시통신", False, False, 1100, 12000, 14000, 1800, 30000, 29000, 10000, 7000, 1000, 32000, 31000),
]

# 미국: 백만 달러, 달러
US = [
    _stock("U01", "예시반도체", True, False, 9000, 30000, 20000, 11000, 50000, 30000, 300000, 8000, 15000, 120, 165),
    _stock("U02", "예시리테일", True, False, 800, 6000, 9000, 1300, 30000, 27000, 9000, 3000, 700, 80, 55),
    _stock("U03", "예시클라우드", False, False, 2500, 10000, 6000, 3200, 15000, 8000, 90000, 2000, 6000, 200, 260),
    _stock("U04", "예시보험", False, True, 2000, 20000, 100000, 2500, 25000, 22000, 30000, 5000, 3000, 50, 55),
    _stock("U05", "예시제약", False, False, 4000, 25000, 15000, 5000, 40000, 36000, 60000, 10000, 8000, 90, 92),
    _stock("U06", "예시산업재", False, False, 1500, 9000, 8000, 2200, 20000, 16000, 25000, 4000, 1500, 60, 70),
    _stock("U07", "예시소형주", False, False, 100, 800, 500, 150, 1200, 900, 1500, 100, 200, 20, 24),
    _stock("U08", "예시에너지", False, False, 3000, 20000, 18000, 4500, 35000, 38000, 30000, 9000, 2000, 45, 48),
    _stock("U09", "예시미디어", False, False, -120, 4000, 3000, -50, 5000, 5200, 3500, 1500, 300, 30, 22),
]

ACCOUNT = Account(total_krw=200_000_000, cash_krw=7_000_000, usdkrw=1380)

HOLDINGS = [
    Holding("미국", "U01", "예시반도체", 120, 110, 120 * 110 * 1300, 170, D(2026, 8, 27)),
    Holding("한국", "K01", "예시전자", 200, 52000, 10_400_000, 61000, D(2026, 7, 30)),
    Holding("한국", "K02", "예시화학", 300, 27000, 8_100_000, 25000, D(2026, 8, 10)),
    Holding("미국", "U02", "예시리테일", 70, 80, 70 * 80 * 1340, 55, D(2026, 8, 20)),
]

REASONS = [
    Reason("K01", 1, "핵심 고객과 장기 공급 계약", True, "계약 유지 공시", "해지·미갱신", D(2026, 8, 3), "무너짐"),
    Reason("K01", 2, "고부가 메모리 매출 비중 확대", False, "부문 매출 전년비", "2회 연속 10% 미만", D(2026, 8, 3), "유지"),
    Reason("K02", 1, "스페셜티 제품 비중 확대", True, "스페셜티 매출 비중(분기)", "2분기 연속 감소", D(2026, 8, 12), "유지"),
    Reason("U01", 1, "데이터센터 매출이 빠르게 는다", True, "부문 매출 전년비", "2회 연속 10% 미만", D(2026, 6, 1), "유지"),
    Reason("U01", 2, "높은 영업이익률 유지", False, "영업이익률", "2분기 연속 30% 미만", D(2026, 6, 1), "유지"),
    Reason("U02", 1, "온라인 매출 성장", True, "온라인 매출 전년비", "2분기 연속 감소", D(2026, 8, 25), "유지"),
    Reason("K07", 1, "구독 매출 전환", True, "구독 매출 비중", "2분기 연속 하락", None, ""),
    Reason("K07", 2, "해외 매출 확대", False, "해외 매출 전년비", "2분기 연속 0% 미만", None, ""),
    Reason("U03", 1, "AI 작업 수요 증가", True, "클라우드 매출 전년비", "", None, ""),
]

PLANS = [
    BuyPlan("한국", "K07", "예시소프트", 10_000_000, D(2026, 10, 12)),
    BuyPlan("미국", "U03", "예시클라우드", 6_000_000, D(2026, 10, 12)),
]


# ---------------------------------------------------------------- 원자료(가상)


def _weekdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def _nth_weekday(year, month, weekday, n):
    d = D(year, month, 1)
    while d.weekday() != weekday:
        d += dt.timedelta(days=1)
    return d + dt.timedelta(days=7 * (n - 1))


def _us_holidays(year):
    return {D(year, 1, 1), D(year, 7, 4), D(year, 12, 25), _nth_weekday(year, 11, 3, 4)}


def _kr_holidays(year):
    return {D(year, m, d) for m, d in ((1, 1), (3, 1), (5, 5), (8, 15), (10, 3), (10, 9), (12, 25))}


def _index_path(rng, n, start, shocks):
    """지수 경로(로그 수익률). shocks: {구간 시작 위치: (길이, 일평균 수익률)}."""
    level, out, rets = start, [], []
    drift_until = {}
    for k, (length, mu) in shocks.items():
        for j in range(k, min(k + length, n)):
            drift_until[j] = mu
    for i in range(n):
        r = rng.gauss(drift_until.get(i, 0.0004), 0.011)
        level *= math.exp(r)
        out.append(round(level, 2))
        rets.append(r)
    return out, rets


def _fear(rng, rets, base, beta, floor, decimals, persist=0.97, noise=0.6):
    v, out = base, []
    for r in rets:
        v = persist * v + (1 - persist) * base - beta * r + rng.gauss(0, noise)
        v = max(v, floor)
        out.append(round(v, decimals))
    return out


def sentiment_raw():
    rng = random.Random(20261007)
    data = {}

    us_days = list(_weekdays(D(2020, 6, 1), END))
    n = len(us_days)
    sp, rets = _index_path(rng, n, 3050, {380: (180, -0.0012), 1210: (25, -0.006)})
    vix = _fear(rng, rets, 18, 90, 9.5, 2)
    baa = _fear(rng, rets, 2.0, 2.0, 0.9, 2, persist=0.995, noise=0.02)
    hol = set().union(*(_us_holidays(y) for y in range(2020, 2027)))
    bond_hol = hol | {_nth_weekday(y, 10, 0, 2) for y in range(2020, 2027)} | {D(y, 11, 11) for y in range(2020, 2027)}
    data["미국"] = {
        "sp500": [(d, "." if d in hol else v) for d, v in zip(us_days, sp)],
        "vix": [(d, "" if d in hol else v) for d, v in zip(us_days, vix)],
        "baa": [(d, "." if d in bond_hol else v) for d, v in zip(us_days, baa)],
    }

    kr_hol = set().union(*(_kr_holidays(y) for y in range(2020, 2027)))
    kr_days = [d for d in _weekdays(D(2020, 6, 1), END) if d not in kr_hol]
    n = len(kr_days)
    kospi, krets = _index_path(rng, n, 2100, {300: (60, 0.003), 520: (200, -0.0011), 1400: (30, -0.004)})
    vkospi = _fear(rng, krets, 20, 100, 10, 2)
    ktb, aa, credit = [], [], []
    y, s, c = 1.0, 0.7, 150000.0
    for i, r in enumerate(krets):
        y = min(max(y + rng.gauss(0.0015 if i < 600 else -0.0004, 0.025), 0.8), 4.3)
        s = min(max(0.99 * s + 0.01 * 0.9 - 3 * r + rng.gauss(0, 0.01), 0.3), 2.5)
        c = max(c * math.exp(0.6 * r + rng.gauss(0.0001, 0.004)), 80000)
        ktb.append(round(y, 3))
        aa.append(round(y + s, 3))
        credit.append(round(c))
    skip = {kr_days[i] for i in (200, 201, 777, 1300)}  # VKOSPI가 빠진 날 → 직전 값 사용
    data["한국"] = {
        # KRX·금투협 내려받기처럼 최신순, ECOS처럼 오래된 순을 섞는다
        "kospi": list(reversed(list(zip(kr_days, kospi)))),
        "vkospi": list(reversed([(d, v) for d, v in zip(kr_days, vkospi) if d not in skip])),
        "aa": list(zip(kr_days, aa)),
        "ktb": list(zip(kr_days, ktb)),
        "credit": list(reversed(list(zip(kr_days, credit)))),
    }
    return data


def _months(start, end):
    y, m = start.year, start.month
    while D(y, m, 1) <= end:
        yield D(y, m, 1)
        m += 1
        if m == 13:
            y, m = y + 1, 1


def macro_raw():
    rng = random.Random(4)
    hol = set().union(*(_us_holidays(y) for y in range(2014, 2027)))
    days = list(_weekdays(D(2014, 6, 2), END))
    dgs10, t10y3m, jpy = [], [], []
    a, b, j = 2.6, 1.5, 102.0
    for i, d in enumerate(days):
        a = min(max(a + rng.gauss(0.0004 if i > 1700 else -0.0002, 0.045), 0.5), 5.2)
        b = min(max(b + rng.gauss(-0.0006 if 2000 < i < 2600 else 0.0003, 0.04), -1.9), 3.2)
        j = j * math.exp(rng.gauss(0.00012, 0.005))
        miss = d in hol
        dgs10.append((d, "." if miss else round(a, 2)))
        t10y3m.append((d, "." if miss else round(b, 2)))
        jpy.append((d, "." if miss else round(j, 2)))

    months = list(_months(D(2014, 1, 1), D(2026, 8, 1)))
    sahm = []
    for d in months:
        base = 0.1 + 0.15 * math.sin(d.year + d.month / 12)
        spike = 8.5 if D(2020, 4, 1) <= d <= D(2020, 9, 1) else (2.0 if d == D(2020, 10, 1) else 0)
        sahm.append((d, round(max(base + spike + rng.gauss(0, 0.05), 0), 2)))
    exports, level = [], 45000.0
    for i, d in enumerate(months[:-1]):  # 수출은 한 달 늦게 나온다
        level *= math.exp(rng.gauss(0.003, 0.03))
        season = 1 + 0.06 * math.sin(2 * math.pi * d.month / 12)
        exports.append((d, round(level * season, 1)))
    return {"sahm": sahm, "dgs10": dgs10, "t10y3m": t10y3m, "jpy": jpy, "exports": exports}


# 판단기록 예시: 날짜, 국가, 종목코드, 종목명, 제안, 점수, 시장 심리, 내 결정, 실제 행동, 금액, 메모
LOG = [
    (D(2026, 10, 1), "미국", "U02", "예시리테일", "① 손실 한도 도달 → 매도", 0, None, "따름", "매도", 5_313_000, "매수가 대비 −31%. 규칙대로 전량 매도."),
    (D(2026, 10, 1), "한국", "K01", "예시전자", "② 핵심 매수 이유 붕괴 → 매도 검토", 83.3, None, "보류", "유지", None, "계약 미갱신 공시 확인. 대체 계약 공시가 나오는지 2주 뒤 다시 본다."),
]


def example_data():
    return {
        "log": LOG,
        "price_date": END,
        "stocks": {"한국": KR, "미국": US},
        "account": ACCOUNT,
        "holdings": HOLDINGS,
        "reasons": REASONS,
        "plans": PLANS,
        "sentiment": sentiment_raw(),
        "macro": macro_raw(),
    }
