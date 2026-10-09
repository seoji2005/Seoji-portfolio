"""설정·도움말: 자료 연결 상태, 비밀값, 13F 운용사 목록, 사전 요약."""

import os

import streamlit as st

from app import state, store

state.header()
st.title("설정·도움말")

st.subheader("자료 연결")
st.write(f"모드: **{'예시 자료(가상)' if state.mode() == 'sample' else '실제 자료'}**")
for k, v in state.provider().status().items():
    st.write(f"- {k}: {v}")
st.write(f"- ECOS_API_KEY: {'설정됨 — 한국 금리 자동' if os.environ.get('ECOS_API_KEY') else '없음 — 한국 금리는 CSV로 올림'}")
st.write(f"- 저장소 저장(GITHUB_TOKEN): {'설정됨' if store.can_commit() else '없음 — 앱에서 고친 내용은 이 세션에만 남음'}")
if st.button("자료 새로 받기", icon=":material/refresh:"):
    st.cache_data.clear()
    st.session_state.pop("_pool_cache", None)
    state.flash("캐시를 지웠습니다. 자료를 다시 받습니다.")
    st.rerun()
st.caption("주가 15분, 시세 5분, 재무·FRED·공시 12시간, 13F 하루 동안 다시 받지 않습니다(무료 API 한도 보호).")

st.subheader("비밀값 (Streamlit Cloud → 앱 → Settings → Secrets)")
st.code(
    '''OPENDART_API_KEY = "OpenDART 인증키"            # 한국 재무
SEC_USER_AGENT = "이름 이메일@example.com"       # 미국 재무·Form 4·13F (SEC가 연락처를 요구)
ECOS_API_KEY = "한국은행 ECOS 인증키"            # 선택: 한국 회사채·국고채 금리 자동
GITHUB_TOKEN = "github_pat_..."                 # 선택: 앱에서 고친 내용을 저장소에 저장
GITHUB_REPO = "seoji2005/Seoji-portfolio"''',
    language="toml",
)

st.subheader("13F 운용사 목록 (참고 근거)")
st.caption("참고지수 대비 비중 차이·보유 중첩에 쓸 운용사. SEC CIK 번호를 넣는다(예: 버크셔 해서웨이 1067983). 13F 비중은 공개 보유분 안의 비중이다.")
mg = store.read("managers")
edited = st.data_editor(mg, num_rows="dynamic", hide_index=True, key="mg_editor",
                        column_config={"name": st.column_config.TextColumn("이름", required=True), "cik": st.column_config.TextColumn("CIK", required=True)})
if st.button("운용사 목록 저장"):
    state.flash(store.write("managers", edited.dropna(how="all").fillna("")))
    st.rerun()

st.subheader("사전 요약 (docs/spec.md)")
st.markdown(
    """
- **1 점수**: ROE, 3년 매출 성장률, 이익수익률, 12-1개월 수익률(수정종가)의 풀 안 백분위를 같은 비중으로 평균 → 다시 백분위. 결측 있으면 제외. 70 이상 편입 후보, 보유 50 미만 + 10점 이상 높은 후보 → 교체 제안.
- **2 거름망**: 영업흑자, 부채비율 200% 이하, 시총 한국 5천억·미국 20억 달러 이상, 금융·리츠 제외.
- **3 시장 심리**: 신규 매수 분할 횟수만. **4 거시**: 표시만.
- **5 손실 한도**: 손실액 ≥ 계좌 2% 또는 −25% → 매도. **6 매도 판단**: ① 손실 한도 ② 매수 이유 카드 무너짐 ③ 40% 초과분 ④ 교체 제안.
- **7 매수 이유 카드**: 이유 1~3개, 확인 지표·사실, 무너지는 조건, 상태(통과/보류/무너짐). 보류는 저절로 무너짐이 되지 않음. 조건 변경 이력. 지표·사실이 없으면 매수 불가.
- **8 참고 근거**: 표시만. 없으면 미확인.
"""
)
st.caption(f"앱 버전: {os.environ.get('GITHUB_SHA', '')[:7] or '로컬'}")
