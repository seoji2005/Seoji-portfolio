# Seoji-portfolio — 나만의 투자 판단 프로그램

판단 기준 명세([`docs/spec.md`](docs/spec.md))를 구현한 개인 투자 도구. 프로그램은 **제안만** 하고, 매매는 사람이 승인하고 직접 한다.

| 형태 | 하는 일 |
|---|---|
| **웹앱** (`streamlit_app.py`) | 관심 종목 시세·점수 목록 → 종목 상세(차트, 점수 설명, 재무 근거) → 포트폴리오 점수와 매도 판단 → 종목을 더하면? → 과거 성과(백테스트) |
| **스프레드시트** (`sheets/투자판단.xlsx`) | 1차 구현. 시장 심리 지수(명세 3)와 거시 패널(명세 4)은 아직 여기에만 있다 |

## 웹앱 화면

| 화면 | 내용 (명세 번호) |
|---|---|
| 관심 종목 | 국가별 점수 순 목록, 편입 후보(70점 이상), 최고 미보유 후보 (1·2) |
| 종목 상세 | 현재가·시총, 판정, 점수 설명 카드(지표 값·풀 안 위치), 주가 차트, 점수에 쓴 숫자와 출처, 포트폴리오에 넣으면? (1·2·8) |
| 내 포트폴리오 | 포트폴리오 점수, ①~④ 매도 판단, 비중 40% 확인, 종목을 더하면?, 보유·계좌·매수 이유 고치기 (5·6·7·8) |
| 과거 성과 | 연평균 수익률·변동성·최대 낙폭·샤프 비율, 평가액·낙폭·연도별 차트, 비교 지수 (9) |
| 설정·도움말 | 자료 연결 상태, 비밀값 설정 방법, 판단 기준 요약 |

자료: 주가·시세는 Yahoo Finance(무료·비공식, 미국은 거의 실시간, 한국은 지연), 미국 재무는 SEC EDGAR, 한국 재무는 OpenDART. 내 자료(관심 종목, 보유, 계좌, 매수 이유)는 이 비공개 저장소의 `my/*.csv`에 있다.

## 휴대폰으로 배포하기 (처음 한 번)

1. **OpenDART 인증키 받기** — 휴대폰 브라우저로 opendart.fss.or.kr → 인증키 신청(무료, 이메일 인증). 없으면 한국 종목은 점수가 나오지 않는다.
2. **Streamlit Community Cloud에 올리기** — share.streamlit.io → GitHub로 로그인(비공개 저장소 접근 허용) → Create app → 저장소 `seoji2005/Seoji-portfolio`, 브랜치 `main`, 파일 `streamlit_app.py` → Advanced settings에서 Python 3.12를 고르고 Secrets에 아래를 붙여 넣는다 → Deploy.
   ```toml
   OPENDART_API_KEY = "받은 인증키"
   SEC_USER_AGENT = "이름 본인이메일@example.com"   # SEC가 요청자 연락처를 요구
   # 선택: 앱에서 고친 목록·보유를 저장소에 저장하려면
   GITHUB_TOKEN = "github_pat_..."   # Fine-grained token, 이 저장소만, Contents 읽기·쓰기
   GITHUB_REPO = "seoji2005/Seoji-portfolio"
   ```
3. 앱 설정 → Sharing에서 **나만 볼 수 있게** 되어 있는지 확인한다(보유 종목이 보이므로).
4. 받은 주소(`….streamlit.app`)를 휴대폰 홈 화면에 추가한다. 한동안 안 쓰면 앱이 잠들고, 다시 열면 30초쯤 깨어난다.

**GitHub Actions 비밀값(선택)** — 저장소 Settings → Secrets and variables → Actions에 `OPENDART_API_KEY`, `SEC_USER_AGENT`를 넣으면 Actions → 검사 → Run workflow의 '실제 자료 점검'이 한국 재무까지 확인한다.

## 내 자료 고치기

- 앱의 각 화면 아래 '고치기'에서 바로 고친다. `GITHUB_TOKEN`이 있으면 저장소에 저장되고, 없으면 그 브라우저 세션에만 남는다.
- 또는 GitHub 앱에서 `my/watchlist.csv`, `my/portfolio.csv`, `my/account.csv`, `my/reasons.csv`를 직접 고친다. 앱이 자동으로 다시 읽는다.

## 스프레드시트

- [`sheets/투자판단.xlsx`](sheets/투자판단.xlsx) 빈 양식, [`sheets/투자판단_예시.xlsx`](sheets/투자판단_예시.xlsx) 가상 데이터 예시.
- 구글 드라이브에 올려 구글 시트 앱으로 열고 **Google 스프레드시트로 저장**(변환)한다. 변환해야 FRED 자동 입력이 동작한다.

## 개발

```bash
pip install -r requirements.txt pytest
DATA_MODE=sample streamlit run streamlit_app.py   # 인터넷 없이 가상 자료로
python -m pytest                                   # LibreOffice가 있으면 시트 수식까지
ONLINE=1 python -m pytest tests/test_online.py -s  # 실제 API 점검
python -m builder                                  # 시트 다시 만들기
```

| 폴더 | 내용 |
|---|---|
| `judge/` | 판단 기준(명세 1~9)의 파이썬 구현. 앱과 시트 검증이 함께 쓴다 |
| `market/` | 자료 계층: Yahoo, SEC EDGAR, OpenDART, 가상 자료, 관심 종목 → 점수 입력 |
| `app/` | 웹앱 화면 |
| `builder/` | 스프레드시트 생성 |
| `my/` | 내 자료(CSV) |
| `tests/` | 손 계산 대조, 시트 수식 대조, 앱 화면, 실제 API 점검 |

명세가 구현하는 쪽에 맡긴 결정은 [`docs/decisions.md`](docs/decisions.md)에 있다.
