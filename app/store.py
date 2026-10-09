"""내 자료(관심 종목, 보유, 계좌, 매수 이유)를 저장소의 my/*.csv에 둔다.

앱에서 고친 내용은 이 브라우저 세션에 바로 반영되고, GITHUB_TOKEN이 설정되어 있으면 저장소에도 커밋된다.
토큰이 없으면 GitHub에서 my/*.csv 파일을 직접 고치면 된다(앱이 자동으로 다시 읽는다).
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "watchlist": ("my/watchlist.csv", ["country", "code", "name", "market", "fin"]),
    "portfolio": ("my/portfolio.csv", ["country", "code", "name", "qty", "avg_price", "cost_krw", "last_earnings"]),
    "account": ("my/account.csv", ["total_krw", "cash_krw"]),
    "reasons": ("my/reasons.csv", ["code", "no", "reason", "core", "evidence", "break_rule", "checked", "result"]),  # 이전 형식(지우지 않음)
    "cards": ("my/buy_reasons.csv", ["code", "no", "reason", "indicator", "fact", "condition", "period", "status", "note", "checked"]),
    "reason_history": ("my/reason_history.csv", ["changed_at", "code", "no", "field", "old", "new", "why"]),
    "evidence": ("my/evidence.csv", ["code", "kind", "holder", "detail", "weight_pct", "as_of", "source"]),
    "managers": ("my/managers.csv", ["name", "cik"]),
    "kr_vkospi": ("my/market/kr_vkospi.csv", ["date", "value"]),
    "kr_aa": ("my/market/kr_aa.csv", ["date", "value"]),
    "kr_ktb": ("my/market/kr_ktb.csv", ["date", "value"]),
    "kr_credit": ("my/market/kr_credit.csv", ["date", "value"]),
}


def _key(name):
    return f"store:{name}"


def read(name: str) -> pd.DataFrame:
    if _key(name) in st.session_state:
        return st.session_state[_key(name)].copy()
    path, cols = FILES[name]
    local = os.environ.get("MY_DATA_DIR")  # 시험·화면 확인용: 다른 폴더의 내 자료를 읽음
    file = Path(local) / Path(path).name if local else ROOT / path
    if file.exists():
        df = pd.read_csv(file, dtype=str, keep_default_na=False)  # 편집기에서 글자로 다룬다(숫자는 쓸 때 바꿈)
    else:
        df = pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]


def to_csv(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue()


def github_save(path: str, text: str, message: str) -> None:
    import requests

    token, repo = os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPO", "")
    branch = os.environ.get("GITHUB_BRANCH", "main")
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    r = requests.get(url, headers=headers, params={"ref": branch}, timeout=20)
    sha = r.json().get("sha") if r.status_code == 200 else None
    body = {"message": message, "content": base64.b64encode(text.encode()).decode(), "branch": branch}
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=headers, json=body, timeout=20)
    r.raise_for_status()


def can_commit() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO"))


def write(name: str, df: pd.DataFrame) -> str:
    """세션에 반영하고, 가능하면 저장소에 커밋. 사용자에게 보여 줄 문구를 돌려준다."""
    path, cols = FILES[name]
    df = df[cols].copy()
    st.session_state[_key(name)] = df
    if not can_commit():
        return "이 브라우저 세션에만 반영했습니다. 계속 남기려면 설정·도움말의 'GitHub 저장' 안내를 따르세요."
    try:
        github_save(path, to_csv(df), f"앱에서 {path} 수정")
    except Exception as ex:  # noqa: BLE001
        return f"세션에는 반영했지만 저장소 저장에 실패했습니다: {ex}"
    return f"저장소의 {path}에 저장했습니다."
