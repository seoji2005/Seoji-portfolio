"""7. 매수 이유 카드. 점수가 아니다. 상태는 내가 점검해서 고른다.

- 이유 1~3개. 이유마다 [확인 지표] 또는 [확인 사실·사건], [무너지는 조건(필요 시 기간)], 상태.
- 카드 상태: 무너짐이 하나라도 있으면 무너짐 → 그 외 보류가 있으면 보류 → 모두 통과면 통과.
- 보류는 보류로 둔다(시간이 지나도 자동으로 무너짐이 되지 않는다). 적어 둔 조건이 확인될 때만 무너짐.
- 확인 지표와 확인 사실·사건을 하나도 적지 못하면 매수 불가.
- 조건을 바꾸면 이전 내용과 바꾼 이유를 이력으로 남긴다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

STATUSES = ("통과", "보류", "무너짐")
TRACKED = {"indicator": "확인 지표", "fact": "확인 사실·사건", "condition": "무너지는 조건", "period": "기간"}


@dataclass
class ReasonItem:
    code: str
    no: int
    reason: str = ""
    indicator: str = ""  # 확인 지표(숫자)
    fact: str = ""  # 확인 사실·사건
    condition: str = ""  # 무너지는 조건
    period: str = ""  # 기간(필요할 때)
    status: str = ""  # 통과 / 보류 / 무너짐
    note: str = ""  # 상태 근거 메모
    checked: str = ""  # 점검일


@dataclass
class Card:
    code: str
    items: list
    status: str  # 통과 / 보류 / 무너짐, 이유가 없으면 ""
    buy_ok: bool
    buy_why: str
    problems: list = field(default_factory=list)


def card_status(items: list[ReasonItem]) -> str:
    statuses = [i.status for i in items]
    if "무너짐" in statuses:
        return "무너짐"
    if "보류" in statuses:
        return "보류"
    if items and all(s == "통과" for s in statuses):
        return "통과"
    return ""


def problems(items: list[ReasonItem]) -> list[str]:
    """기록이 덜 된 곳(상태를 정하지는 않는다)."""
    out = []
    if len(items) > 3:
        out.append(f"이유가 {len(items)}개 — 사전은 1~3개")
    for i in items:
        if not (i.indicator or i.fact):
            out.append(f"{i.no}번 이유: 확인 지표·사실 없음")
        if not i.condition:
            out.append(f"{i.no}번 이유: 무너지는 조건 없음")
        if i.status not in STATUSES:
            out.append(f"{i.no}번 이유: 상태(통과/보류/무너짐)를 고르지 않음")
    return out


def card(code: str, items: list[ReasonItem]) -> Card:
    mine = sorted((i for i in items if i.code == code), key=lambda i: i.no)
    if not mine:
        return Card(code, [], "", False, "매수 이유 없음 — 매수 불가")
    if not any(i.indicator or i.fact for i in mine):
        return Card(code, mine, card_status(mine), False, "확인 지표·사실을 하나도 적지 못함 — 매수 불가", problems(mine))
    return Card(code, mine, card_status(mine), True, "", problems(mine))


def history(old: list[ReasonItem], new: list[ReasonItem], why: str, when: dt.date) -> list[dict]:
    """같은 종목의 이유 목록이 바뀐 곳 → 이력 줄. 확인 지표·사실·조건·기간이 바뀌었는데 이유가 없으면 오류."""
    before = {i.no: i for i in old}
    rows = []
    for i in new:
        prev = before.get(i.no)
        if prev is None:
            continue  # 새 이유는 이력이 아니다
        for key, label in TRACKED.items():
            a, b = getattr(prev, key), getattr(i, key)
            if a != b:
                rows.append({"changed_at": when.isoformat(), "code": i.code, "no": i.no, "field": label, "old": a, "new": b, "why": why})
    removed = [prev for no, prev in before.items() if no not in {i.no for i in new}]
    for prev in removed:
        rows.append({"changed_at": when.isoformat(), "code": prev.code, "no": prev.no, "field": "이유 삭제",
                     "old": " / ".join(x for x in (prev.reason, prev.indicator, prev.fact, prev.condition, prev.period) if x), "new": "", "why": why})
    if rows and not why.strip():
        raise ValueError("확인 지표·사실·조건·기간을 바꾸거나 이유를 지울 때는 바꾼 이유를 적어야 합니다.")
    return rows
