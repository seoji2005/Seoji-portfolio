"""설정·도움말: 자료 연결 상태, 비밀값 설정 방법, 판단 기준 요약."""

import os

import streamlit as st

from app import state, store

state.header()
st.title("설정·도움말")

st.subheader("자료 연결")
st.write(f"모드: **{'예시 자료(가상)' if state.mode() == 'sample' else '실제 자료'}**")
for k, v in state.provider().status().items():
    st.write(f"- {k}: {v}")
st.write(f"- 저장소 저장(GITHUB_TOKEN): {'설정됨' if store.can_commit() else '없음 — 앱에서 고친 내용은 이 세션에만 남음'}")
if st.button("자료 새로 받기", icon=":material/refresh:"):
    st.cache_data.clear()
    st.session_state.pop("_pool_cache", None)
    state.flash("캐시를 지웠습니다. 자료를 다시 받습니다.")
    st.rerun()
st.caption("주가는 15분, 시세는 5분, 재무는 12시간 동안 다시 받지 않습니다(무료 API 한도 보호).")

st.subheader("비밀값 설정 (Streamlit Cloud → 앱 → Settings → Secrets)")
st.code(
    '''OPENDART_API_KEY = "OpenDART에서 받은 인증키"     # 한국 종목 재무 (opendart.fss.or.kr, 무료)
SEC_USER_AGENT = "이름 이메일@example.com"          # 미국 종목 재무 (SEC가 연락처를 요구)
GITHUB_TOKEN = "github_pat_..."                    # 선택: 앱에서 고친 목록을 저장소에 저장
GITHUB_REPO = "seoji2005/Seoji-portfolio"          # 선택: 위 토큰과 함께
# DATA_MODE = "sample"                             # 인터넷 없이 가상 자료로 볼 때''',
    language="toml",
)
st.caption(
    "GITHUB_TOKEN: GitHub → Settings → Developer settings → Fine-grained tokens → 이 저장소만, Contents 읽기·쓰기 권한. "
    "토큰이 없으면 GitHub 앱에서 my/watchlist.csv, my/portfolio.csv 등을 직접 고치면 됩니다."
)

st.subheader("판단 기준 (docs/spec.md 요약)")
st.markdown(
    """
- **점수(1)**: ROE, 3년 매출 성장률, 이익수익률, 12-1개월 수익률의 풀 안 백분위를 같은 비중으로 평균 → 다시 백분위(0~100). 같은 국가 관심 종목끼리만 비교.
- **편입 후보**: 70점 이상. **교체 제안**: 보유 종목 50점 미만이고 같은 국가에 10점 이상 높은 후보.
- **거름망(2)**: 최근 1년 영업흑자, 부채비율 200% 이하, 시총 한국 5,000억·미국 20억 달러 이상. 금융·리츠 제외. 하나라도 걸리면 점수 없음.
- **손실 한도(5)**: 손실액 ≥ 계좌 평가액 2%, 또는 매수 평균가 대비 −25% → 매도.
- **매도 판단(6)**: ① 손실 한도 ② 핵심 매수 이유 붕괴 ③ 비중 40% 초과(3종목 이상) ④ 교체 제안. '많이 올랐다'는 매도 신호가 아님.
- **포트폴리오 점수(8)**: 보유 종목 점수의 평가액 가중 평균. 표시만.
- **과거 성과(9)**: 수익률·변동성·낙폭. 표시만.
- 시장 심리(3)와 거시 패널(4)은 아직 스프레드시트(sheets/투자판단.xlsx)에 있습니다.
"""
)
st.caption(f"앱 버전: {os.environ.get('GITHUB_SHA', '')[:7] or '로컬'}")
