"""시장 심리·거시 자료: FRED CSV, 한국은행 ECOS 응답, 내려받은 CSV(세로형·가로형, cp949)."""

import datetime as dt

import pytest

from market import csvin, ecos, fred

D = dt.date


def test_fred_csv_with_missing_values():
    text = "observation_date,VIXCLS\n2026-10-01,16.5\n2026-10-02,.\n2026-10-03,\n2026-10-06,17\n"
    assert fred.parse_csv(text) == [(D(2026, 10, 1), 16.5), (D(2026, 10, 2), None), (D(2026, 10, 3), None), (D(2026, 10, 6), 17.0)]


def test_ecos_rows_and_error():
    data = {"StatisticSearch": {"list_total_count": 2, "row": [
        {"STAT_CODE": "817Y002", "ITEM_CODE1": "010300000", "TIME": "20261001", "DATA_VALUE": "3.512"},
        {"STAT_CODE": "817Y002", "ITEM_CODE1": "010300000", "TIME": "20261002", "DATA_VALUE": "3.498"},
    ]}}
    assert ecos.parse(data) == [(D(2026, 10, 1), 3.512), (D(2026, 10, 2), 3.498)]
    with pytest.raises(ecos.EcosError, match="인증키"):
        ecos.parse({"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키가 유효하지 않습니다."}})


def test_long_csv_in_cp949_with_commas():
    text = "일자,종가,대비\n2026/10/02,\"21.35\",0.2\n2026/10/01,21.15,-0.1\n"
    df = csvin.read_table(text.encode("cp949"))
    assert csvin.date_columns(df) == ["일자"] and not csvin.is_wide(df)
    assert csvin.long_series(df, "일자", "종가") == [(D(2026, 10, 1), 21.15), (D(2026, 10, 2), 21.35)]  # 최신순이어도 날짜순으로


def test_credit_balance_with_thousands_separators():
    text = "기준일자,신용거래융자 전체\n20261002,\"185,123\"\n20261001,\"184,000\"\n"
    df = csvin.read_table(text.encode("utf-8"))
    assert csvin.long_series(df, "기준일자", "신용거래융자 전체")[-1] == (D(2026, 10, 2), 185123.0)


def test_wide_ecos_table():
    dates = [f"2026/09/{d:02d}" for d in range(1, 16)]
    header = "통계표,계정항목,단위," + ",".join(dates)
    rows = ["시장금리(일별),국고채(3년),연%," + ",".join("2.5" for _ in dates), "시장금리(일별),회사채(3년 AA-),연%," + ",".join("3.1" for _ in dates)]
    df = csvin.read_table(("\n".join([header, *rows]) + "\n").encode("utf-8"))
    assert csvin.is_wide(df)
    s = csvin.wide_series(df, 1)
    assert len(s) == 15 and s[0] == (D(2026, 9, 1), 3.1)


def test_frame_round_trip():
    s = [(D(2026, 10, 1), 1.5), (D(2026, 10, 2), 2.0)]
    assert csvin.from_frame(csvin.to_frame(s)) == s
