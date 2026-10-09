"""8. 참고 근거: Form 4 장내 매수 판별, 13F 비중, 카드 구성. 실제 서류 모양의 가짜 자료로."""

import datetime as dt

import pytest

from judge.evidence import EvidenceRow, summarize
from market import f13, insider

D = dt.date


def form4(code="P", footnote="", remarks="", plan="0", officer=True, ad="A", derivative=False):
    tx = f"""
      <{'derivativeTransaction' if derivative else 'nonDerivativeTransaction'}>
        <securityTitle><value>Common Stock</value></securityTitle>
        <transactionDate><value>2026-05-01</value></transactionDate>
        <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode>
          <equitySwapInvolved>0</equitySwapInvolved>{'<footnoteId id="F1"/>' if footnote else ''}</transactionCoding>
        <transactionAmounts><transactionShares><value>1000</value></transactionShares>
          <transactionPricePerShare><value>150.25</value></transactionPricePerShare>
          <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode></transactionAmounts>
      </{'derivativeTransaction' if derivative else 'nonDerivativeTransaction'}>"""
    table = f"<derivativeTable>{tx}</derivativeTable>" if derivative else f"<nonDerivativeTable>{tx}</nonDerivativeTable>"
    return f"""<?xml version="1.0"?>
    <ownershipDocument>
      <documentType>4</documentType><periodOfReport>2026-05-01</periodOfReport>
      <issuer><issuerCik>0000000001</issuerCik><issuerName>Example Corp</issuerName><issuerTradingSymbol>EXM</issuerTradingSymbol></issuer>
      <reportingOwner><reportingOwnerId><rptOwnerCik>0000000002</rptOwnerCik><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>{1 if officer else 0}</isOfficer>
          <officerTitle>{'CEO' if officer else ''}</officerTitle><isTenPercentOwner>{0 if officer else 1}</isTenPercentOwner></reportingOwnerRelationship>
      </reportingOwner>
      <aff10b5One>{plan}</aff10b5One>
      {table}
      <footnotes>{f'<footnote id="F1">{footnote}</footnote>' if footnote else ''}</footnotes>
      <remarks>{remarks}</remarks>
    </ownershipDocument>"""


@pytest.mark.parametrize(
    "kwargs,status",
    [
        ({"footnote": "The shares were purchased in the open market."}, "확인"),
        ({"remarks": "All purchases reported herein were open-market purchases."}, "확인"),
        ({}, "미확인"),  # P 코드만으로는 장내인지 알 수 없음
        ({"footnote": "Represents a weighted average purchase price."}, "미확인"),  # 추정은 확인이 아님
        ({"footnote": "Purchased in a privately negotiated transaction, not on the open market."}, "미확인"),
        ({"footnote": "Purchased in the open market.", "plan": "1"}, "제외(10b5-1)"),
        ({"footnote": "Purchased in the open market pursuant to a Rule 10b5-1 trading plan."}, "제외(10b5-1)"),
    ],
)
def test_form4_open_market_needs_explicit_confirmation(kwargs, status):
    got = insider.parse_form4(form4(**kwargs))
    assert [p.status for p in got] == [status]
    assert got[0].owner == "Doe Jane" and got[0].role == "CEO" and got[0].shares == 1000 and got[0].price == 150.25


@pytest.mark.parametrize(
    "kwargs",
    [{"code": "M"}, {"code": "S", "ad": "D"}, {"officer": False, "footnote": "open market"}, {"derivative": True, "footnote": "open market"}],
)
def test_form4_ignores_non_purchases_and_non_officers(kwargs):
    assert insider.parse_form4(form4(**kwargs)) == []  # 옵션 행사·매도·10% 주주·파생 거래는 보지 않음


def test_recent_form4_paths_point_to_raw_xml():
    subs = {"filings": {"recent": {
        "form": ["4", "8-K", "4", "4/A"],
        "accessionNumber": ["0001-26-000001", "0001-26-000002", "0001-24-000003", "0001-26-000004"],
        "filingDate": ["2026-09-01", "2026-09-02", "2024-01-01", "2026-08-01"],
        "primaryDocument": ["xslF345X05/wk-form4_1.xml", "x.htm", "xslF345X05/old.xml", "xslF345X05/wk-form4_2.xml"],
    }}}
    assert insider.recent_form4(subs, D(2025, 10, 9)) == [("000126000001/wk-form4_1.xml", "2026-09-01"), ("000126000004/wk-form4_2.xml", "2026-08-01")]


INFOTABLE = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>600</value>
    <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>ALPHABET INC</nameOfIssuer><titleOfClass>CAP STK CL A</titleOfClass><cusip>02079K305</cusip><value>150</value></infoTable>
  <infoTable><nameOfIssuer>ALPHABET INC</nameOfIssuer><titleOfClass>CAP STK CL C</titleOfClass><cusip>02079K107</cusip><value>50</value></infoTable>
  <infoTable><nameOfIssuer>PROCTER AND GAMBLE CO</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>742718109</cusip><value>200</value></infoTable>
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>999</value><putCall>Call</putCall></infoTable>
</informationTable>"""


def test_13f_weight_is_share_of_disclosed_holdings_without_options():
    rows = f13.parse_infotable(INFOTABLE)
    assert len(rows) == 5
    w, matched = f13.weight_of(rows, "Apple Inc.")
    assert w == pytest.approx(600 / 1000) and matched == [("APPLE INC", "COM")]
    w, matched = f13.weight_of(rows, "Alphabet Inc.")
    assert w == pytest.approx(0.2) and len(matched) == 2  # 두 종류 모두(찾은 이름을 보여 줌)
    assert f13.weight_of(rows, "Procter & Gamble Co")[0] == pytest.approx(0.2)
    assert f13.weight_of(rows, "Costco Wholesale Corp /NEW")[0] == 0  # 못 찾으면 0 → 표시는 미확인


def test_card_unknown_when_no_data_and_never_filled_with_counts():
    secs = summarize("미국", [])
    assert [s.title for s in secs] == ["전문가 개인 종목 투자(확인된 것만)", "매니저 자기 펀드 투자(운용자 단위)", "참고지수 대비 비중 차이",
                                       "임원 장내 매수", "보유 중첩(확인된 전문가·기관의 공동 보유)"]
    assert all(s.unknown for s in secs)


def test_card_with_13f_index_weight_insider_and_co_holding():
    rows = [
        EvidenceRow("A", "참고지수 비중", "S&P 500", weight_pct=6.0, as_of="2026-09-30", source="spglobal.com"),
        EvidenceRow("A", "전문가 개인 투자", "홍길동", "2025-11 장내 매수 공시", as_of="2025-11-20", source="SEC Form 4"),
    ]
    hit = f13.Hit("버크셔 해서웨이", "2026-06-30", 0.25, [("APPLE INC", "COM")])
    s = insider.InsiderSummary(since="2025-10-09")
    s.confirmed.append(insider.Purchase("2026-05-01", "Doe Jane", "CEO", 1000, 150.25, "확인", "The shares were purchased in the open market."))
    s.unconfirmed.append(insider.Purchase("2026-06-01", "Roe Rick", "CFO", 10, 1, "미확인"))
    secs = {x.title: x for x in summarize("미국", rows, s, hits=[hit])}
    assert secs["참고지수 대비 비중 차이"].lines == ["버크셔 해서웨이: 공개 보유분(13F) 안 비중 25.00% (기준 2026-06-30) − S&P 500 비중 6.00% = +19.00%p"]
    assert "13F에 공개된 보유분 안의 비중" in secs["참고지수 대비 비중 차이"].note
    assert secs["임원 장내 매수"].lines[0].startswith("2026-05-01 Doe Jane(CEO) 1,000주")
    assert "장내 여부를 확인할 수 없는 매수 1건은 미확인" in secs["임원 장내 매수"].note
    assert secs["보유 중첩(확인된 전문가·기관의 공동 보유)"].lines == ["버크셔 해서웨이(13F), 홍길동(전문가 개인 투자) — 2곳"]


def test_single_holder_is_not_an_overlap_and_korea_has_no_13f():
    rows = [EvidenceRow("K", "기관 보유", "국민연금", weight_pct=3.0)]
    secs = {x.title: x for x in summarize("한국", rows, insider_note="한국 공시는 자동 확인하지 않음")}
    overlap = secs["보유 중첩(확인된 전문가·기관의 공동 보유)"]
    assert overlap.unknown and "국민연금" in overlap.note
    assert secs["참고지수 대비 비중 차이"].lines == ["국민연금: 비중 3.00% — 참고지수 비중 미확인이라 차이 미확인"]
    assert "한국 종목은 대상이 아님" in secs["참고지수 대비 비중 차이"].note
    assert secs["임원 장내 매수"].unknown and secs["임원 장내 매수"].note == "한국 공시는 자동 확인하지 않음"
