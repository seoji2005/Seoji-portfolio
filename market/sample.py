"""인터넷 없이 앱을 돌려 볼 때 쓰는 가상 자료. 숫자는 모두 지어낸 값이다(종목코드마다 늘 같은 값)."""

from __future__ import annotations

import datetime as dt
import math
import random
import zlib

import numpy as np
import pandas as pd

from .models import Fundamentals, Profile, Quote

END = dt.date(2026, 9, 30)
FINANCIAL = {"JPM", "BRK-B", "105560.KS", "055550.KS"}  # 예시에서 금융으로 볼 심볼


def _rng(key: str) -> random.Random:
    return random.Random(zlib.crc32(key.encode()))


def _country(sym: str) -> str:
    return "한국" if sym.endswith((".KS", ".KQ")) else "미국"


class SampleProvider:
    name = "sample"

    def histories(self, symbols, years=11) -> dict[str, pd.DataFrame]:
        days = pd.bdate_range(END - dt.timedelta(days=int(365.25 * years)), END)
        out = {}
        for s in symbols:
            r = _rng("h" + s)
            nprng = np.random.default_rng(zlib.crc32(s.encode()))
            mu, vol = r.uniform(-0.0001, 0.0009), r.uniform(0.012, 0.024)
            if s == "KRW=X":
                path = 1150 * np.exp(np.cumsum(nprng.normal(0.00006, 0.004, len(days))))
            else:
                start = r.uniform(30, 400) if _country(s) == "미국" else r.uniform(20000, 400000)
                path = start * np.exp(np.cumsum(nprng.normal(mu, vol, len(days))))
            close = pd.Series(np.round(path, 2), index=days)
            dy = 0 if s == "KRW=X" else r.uniform(0, 0.03)
            t = np.arange(len(days))[::-1] / 252
            out[s] = pd.DataFrame({"close": close, "adj_close": close * np.exp(-dy * t)})
        return out

    def quote(self, sym) -> Quote:
        h = self.histories([sym], 1)[sym]["close"]
        r = _rng("q" + sym)
        shares = r.uniform(2e8, 1.5e10) if _country(sym) == "미국" else r.uniform(5e7, 6e9)
        cur = "USD" if _country(sym) == "미국" else "KRW"
        return Quote(price=float(h.iloc[-1]), previous_close=float(h.iloc[-2]), market_cap=float(h.iloc[-1]) * shares, currency=cur)

    def profile(self, sym) -> Profile:
        if sym in FINANCIAL:
            return Profile(name=sym, sector="Financial Services", industry="Banks - Diversified")
        r = _rng("p" + sym)
        industry = r.choice(["Semiconductors", "Software - Infrastructure", "Auto Manufacturers", "Consumer Electronics", "Drug Manufacturers"])
        return Profile(name=sym, sector="", industry=industry)

    def fx_usdkrw(self, years=11) -> pd.Series:
        return self.histories(["KRW=X"], years)["KRW=X"]["close"]

    def fundamentals(self, country, code) -> Fundamentals:
        r = _rng(f"f{country}{code}")
        scale = 1e9 if country == "미국" else 1e12
        rev = scale * math.exp(r.uniform(math.log(5), math.log(300)))
        margin = r.uniform(-0.05, 0.4)
        equity = rev * r.uniform(0.3, 1.5)
        liab = equity * r.uniform(0.2, 1.8)
        debt = liab * r.uniform(0.0, 0.5)
        f = Fundamentals(
            as_of=dt.date(2026, 6, 30), net_income=rev * margin * 0.8, equity=equity, liabilities=liab, op_income=rev * margin,
            revenue=rev, revenue_3y_ago=rev / r.uniform(0.85, 1.9), debt=debt, cash=rev * r.uniform(0.05, 0.4),
            source="예시 자료(가상)",
        )
        f.debt_parts = {"차입금(예시)": debt}
        f.cash_parts = {"현금및현금성자산(예시)": f.cash}
        return f

    def status(self) -> dict:
        return {"자료": "예시 자료(가상) — 실제 시세가 아님"}
