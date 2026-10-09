"""자료 공급자. LiveProvider는 실제 API, SampleProvider(sample.py)는 인터넷 없이 쓰는 가상 자료."""

from __future__ import annotations

import datetime as dt
import os
import threading

import pandas as pd

from . import dart, sec, yahoo
from .models import Fundamentals, Profile, Quote


def setting(name: str, default: str = "") -> str:
    """비밀값·설정: 환경변수(Streamlit Cloud는 secrets를 환경변수로도 준다)."""
    return os.environ.get(name, default).strip()


class LiveProvider:
    name = "live"

    def __init__(self, sec_user_agent: str | None = None, dart_key: str | None = None):
        self.sec_ua = sec_user_agent if sec_user_agent is not None else setting("SEC_USER_AGENT")
        self.dart_key = dart_key if dart_key is not None else setting("OPENDART_API_KEY")
        self._lock = threading.Lock()
        self._cik = None
        self._corp = None

    def histories(self, symbols, years=11) -> dict[str, pd.DataFrame]:
        return yahoo.histories(symbols, years)

    def quote(self, sym) -> Quote:
        return yahoo.quote(sym)

    def profile(self, sym) -> Profile:
        return yahoo.profile(sym)

    def fx_usdkrw(self, years=11) -> pd.Series:
        return yahoo.histories([yahoo.FX_USDKRW], years)[yahoo.FX_USDKRW]["close"]

    def _maps(self, country):
        with self._lock:
            if country == "미국" and self._cik is None:
                self._cik = sec.ticker_map(self.sec_ua)
            if country == "한국" and self._corp is None:
                self._corp = dart.corp_codes(self.dart_key)
        return self._cik if country == "미국" else self._corp

    def fundamentals(self, country, code) -> Fundamentals:
        if country == "미국":
            if not self.sec_ua:
                return Fundamentals(source="SEC EDGAR", notes=["SEC_USER_AGENT(이름 이메일)가 설정되지 않아 미국 재무를 받지 않음"])
            return sec.fetch_fundamentals(code, self.sec_ua, self._maps("미국"))
        if not self.dart_key:
            return Fundamentals(source="OpenDART", notes=["OpenDART 인증키(OPENDART_API_KEY)가 설정되지 않음"])
        return dart.fetch_fundamentals(code, self.dart_key, self._maps("한국"), dt.date.today())

    def rights_events(self, code, start, end) -> list:
        """한국 종목의 권리락이 생기는 증자 결정(OpenDART). 확인할 수 없으면 예외."""
        if not self.dart_key:
            raise dart.DartError("OpenDART 인증키 없음")
        return dart.rights_events(code, self.dart_key, self._maps("한국"), start, end)

    def status(self) -> dict:
        return {
            "SEC_USER_AGENT": "설정됨" if self.sec_ua else "없음 — 미국 종목 재무를 받을 수 없음",
            "OPENDART_API_KEY": "설정됨" if self.dart_key else "없음 — 한국 종목 재무를 받을 수 없음",
        }
