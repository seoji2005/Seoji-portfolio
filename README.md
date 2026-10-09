# Seoji-portfolio — 투자 판단 보조

사전([`docs/spec.md`](docs/spec.md), 2026-10-09)을 구현한 웹앱. **제안만** 하고, 자동 매매는 없다. 매매는 직접 승인하고 직접 한다.

## 화면 (사전의 출력)

| 화면 | 내용 |
|---|---|
| 관심 종목 | 국가별 점수 순 목록, 편입 후보, 최고 미보유 후보 (1·2) |
| 종목 카드 | 거름망 결과, 지표 값·풀 내 위치, 한 줄 요약, 매수 이유 카드 상태, 참고 근거, 주가 차트, 재무 출처 (1·2·7·8) |
| 매수 이유 카드 | 이유 1~3개, 확인 지표·사실, 무너지는 조건, 상태, 조건 변경 이력 (7) |
| 보유·매도 판단 | ①~④ 신호 목록(걸린 것 전부, 우선순위 순) (5·6) |
| 시장 심리 | 미국·한국 점수, 신규 매수 분할 횟수, 지표별 근거 (3) |
| 거시 참고 | FRED 5개의 현재값·10년 백분위, 표시만 (4) |

**사전 밖 기능(동결·보존)**: 포트폴리오 점수·종목을 더하면?, 과거 성과. 메뉴의 별도 묶음으로 분리했고 판단에는 쓰지 않는다. 삭제는 미룬다. 스프레드시트(`sheets/`)도 그대로 두었고 이전 명세([`docs/spec_v1.md`](docs/spec_v1.md)) 기준이다.

## 결정한 것 (짧게)

- **형태**: Streamlit 웹앱(Streamlit Community Cloud). 판단 로직은 `judge/`, 자료는 `market/`, 화면은 `app/`.
- **저장**: 비공개 저장소의 `my/*.csv`. 앱에서 고치면 `GITHUB_TOKEN`이 있을 때 저장소에 커밋, 없으면 세션에만 남는다.
- **12-1 수익률**: 수정종가 = 분할·병합·증자 반영, 현금배당 미반영. Yahoo 종가(Close: 분할·병합 반영, 배당 미반영)의 마지막 거래일 기준 12개월 전·1개월 전 값. 배당까지 반영한 Adj Close는 쓰지 않는다. Yahoo가 한국 종목의 증자(특히 유상증자 권리락)까지 보정하는지는 아직 확인하지 못했다.
- **결측·동점**: 지표 하나라도 계산 못 하면 풀에서 제외(이유 표시). 동점은 평균 순위.
- **매수 이유 카드**: 상태는 내가 점검해서 고른다. 보류는 저절로 무너짐이 되지 않는다. 확인 지표·사실·조건·기간을 바꾸거나 이유를 지우려면 바꾼 이유가 필요하고, 이전 내용과 함께 `my/reason_history.csv`에 남는다.
- **매도 신호 ②**: 매수 이유 카드 상태가 '무너짐'일 때.
- **참고 근거**: 직접 넣는 확인된 근거(`my/evidence.csv`, 출처 필수) + 미국 임원 장내 매수(SEC Form 4) + 13F(`my/managers.csv`의 운용사). Form 4는 각주·비고가 장내 매수라고 밝힌 거래만 '확인'이고, 10b5-1 표시 거래는 빼고, 나머지는 '미확인'. 한국 임원 거래는 자동으로 가리지 않는다. 보유 중첩 = 확인된 전문가·기관의 공동 보유 사실.
- **실시간**: 무료 자료라 미국은 거의 실시간, 한국은 지연. 캐시: 주가 15분, 시세 5분, 재무·FRED·공시 12시간.

## 자료 출처 (출처 변경 기록 포함)

| 지표 | 출처 | 정의·단위·주기 | 사전과 비교 |
|---|---|---|---|
| 주가·시총·환율·코스피 | Yahoo Finance(시세) | 일별 종가(분할·병합 반영, 배당 미반영), 시가총액 | 같음(시세) |
| 미국 재무 | SEC EDGAR companyfacts | 10-K·10-Q, 최근 4개 분기 합 | 같음 |
| 한국 재무 | OpenDART | 연결(없으면 별도), 최근 4개 분기 합 | 같음 |
| VIX, Baa−10년물, S&P 500 | FRED VIXCLS·BAA10Y·SP500 | 일별 | 같음 |
| VKOSPI | KRX 정보데이터시스템(CSV 올림) | 일별 지수 | 같음(시세) |
| 회사채 AA- 3년, 국고채 3년 | **한국은행 ECOS 817Y002** (2026-10-09 추가) | 연 %, 일별. 금리차 = AA- − 국고채(%p) | 정의·단위·주기 같음, 출처만 추가 |
| 신용융자잔고 | **금융투자협회 FreeSIS** (2026-10-09 추가, CSV 올림) | 신용거래융자 전체(유가+코스닥), 일별. 20일 증감률은 단위와 무관 | 정의·주기 같음, 출처만 추가 |
| 거시 5개 | FRED SAHMREALTIME·DGS10·T10Y3M·DEXJPUS·XTEXVA01KRM667N | 수출은 같은 달 전년비. 화면에 계산에 쓴 두 원값과 기준월을 함께 표시 | 같음 |
| 임원 매수, 13F | SEC EDGAR Form 4·13F-HR | 최근 12개월 / 운용사 최근 분기 | 같음 |

사전 항목별 구현 위치와 테스트는 [`docs/decisions.md`](docs/decisions.md).

## 휴대폰으로 배포하기

1. 준비: OpenDART 인증키(한국 재무), 선택으로 한국은행 ECOS 인증키(한국 금리 자동). SEC는 인증키가 없다. 대신 요청자를 밝히는 이름·연락처(`SEC_USER_AGENT`)를 요구한다.
2. share.streamlit.io → GitHub 로그인 → 저장소 `seoji2005/Seoji-portfolio`, 브랜치 `main`, 파일 `streamlit_app.py` → Advanced settings에서 Python 3.12, Secrets에:
   ```toml
   OPENDART_API_KEY = "인증키"
   SEC_USER_AGENT = "이름 본인이메일@example.com"   # 인증키 아님: SEC 요청자 이름·연락처(없으면 미국 재무·공시 조회 안 함)
   ECOS_API_KEY = "인증키"                          # 선택
   GITHUB_TOKEN = "github_pat_..."                  # 선택: 앱에서 고친 내용을 저장
   GITHUB_REPO = "seoji2005/Seoji-portfolio"
   ```
3. 앱 Sharing에서 나만 볼 수 있게 되어 있는지 확인. 주소를 홈 화면에 추가.
4. 같은 값(`OPENDART_API_KEY`, `SEC_USER_AGENT`, `ECOS_API_KEY`)을 저장소 Settings → Secrets and variables → Actions에도 넣고 Actions → 검사 → Run workflow를 누르면 '실제 자료 점검'이 모두 돈다. 결과 화면(Summary)에 종목별 4지표와 최종 점수 표가 나온다.

## 개발

```bash
pip install -r requirements.txt pytest
DATA_MODE=sample streamlit run streamlit_app.py   # 인터넷 없이 가상 자료로
python -m pytest                                   # LibreOffice가 있으면 스프레드시트 수식까지
ONLINE=1 python -m pytest tests/test_online.py -s  # 실제 API 점검
```
