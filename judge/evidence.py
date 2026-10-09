"""8. 참고 근거. 점수 설명 카드에 표시만 한다. 점수·순위·매매 규칙에 쓰지 않는다.

자료가 없으면 "미확인". 기관 보유 수 같은 다른 숫자로 대신 채우지 않는다.
보유 중첩 = 확인된 전문가·기관 사이에 이 종목을 함께 보유한 사실(위험 점수로 바꾸지 않음).
"""

from __future__ import annotations

from dataclasses import dataclass, field

UNKNOWN = "미확인"
# 직접 입력하는 근거의 종류(my/evidence.csv의 kind)
KINDS = ("전문가 개인 투자", "매니저 자기 펀드 투자", "기관 보유", "참고지수 비중", "임원 장내 매수")
HOLDING_KINDS = ("전문가 개인 투자", "매니저 자기 펀드 투자", "기관 보유")


@dataclass
class EvidenceRow:
    code: str
    kind: str
    holder: str  # 누가(전문가·운용자·기관·지수 이름)
    detail: str = ""  # 무엇을(예: '2025-11 장내 매수 1만 주')
    weight_pct: float | None = None  # 비중(%) — 참고지수 비중일 때
    as_of: str = ""  # 기준일
    source: str = ""  # 출처(공시 링크·문서)


@dataclass
class Section:
    title: str
    lines: list = field(default_factory=list)
    note: str = ""

    @property
    def unknown(self) -> bool:
        return not self.lines


def _line(r: EvidenceRow) -> str:
    bits = [r.holder]
    if r.detail:
        bits.append(r.detail)
    tail = ", ".join(x for x in (r.as_of and f"기준 {r.as_of}", r.source and f"출처 {r.source}") if x)
    return " — ".join(bits) + (f" ({tail})" if tail else "")


def summarize(country: str, rows: list[EvidenceRow], insider=None, insider_note: str = "", hits: list | None = None, f13_note: str = "") -> list[Section]:
    """rows: 이 종목의 직접 입력 근거. insider: market.insider.InsiderSummary(미국). hits: market.f13.Hit 목록."""
    hits = hits or []
    by = {k: [r for r in rows if r.kind == k] for k in KINDS}
    out = []

    out.append(Section("전문가 개인 종목 투자(확인된 것만)", [_line(r) for r in by["전문가 개인 투자"]]))
    out.append(Section("매니저 자기 펀드 투자(운용자 단위)", [_line(r) for r in by["매니저 자기 펀드 투자"]]))

    index = [ix for ix in by["참고지수 비중"] if ix.weight_pct is not None]
    holdings = [(f"{h.manager}: 공개 보유분(13F) 안 비중 {h.weight:.2%} (기준 {h.period})", h.weight * 100) for h in hits]
    holdings += [(f"{r.holder}: 비중 {r.weight_pct:.2f}%" + (f" (기준 {r.as_of})" if r.as_of else ""), r.weight_pct)
                 for r in by["기관 보유"] if r.weight_pct is not None]
    lines = []
    for base, pct in holdings:
        if index:
            lines += [f"{base} − {ix.holder} 비중 {ix.weight_pct:.2f}% = {pct - ix.weight_pct:+.2f}%p" for ix in index]
        else:
            lines.append(f"{base} — 참고지수 비중 {UNKNOWN}이라 차이 {UNKNOWN}")
    sec = Section("참고지수 대비 비중 차이", lines, "13F 비중은 운용사 전체 자산이 아니라 13F에 공개된 보유분 안의 비중")
    if not hits:
        sec.note = f13_note or sec.note
    out.append(sec)

    lines, note = [_line(r) for r in by["임원 장내 매수"]], insider_note
    if insider is not None:
        lines += [f"{p.date} {p.owner}({p.role}) {p.shares or 0:,.0f}주 @ {p.price or 0:,.2f} — 근거: \"{p.evidence[:120]}\"" for p in insider.confirmed]
        bits = []
        if insider.unconfirmed:
            bits.append(f"장내 여부를 확인할 수 없는 매수 {len(insider.unconfirmed)}건은 {UNKNOWN}")
        if insider.excluded:
            bits.append(f"10b5-1 표시 매수 {len(insider.excluded)}건 제외")
        note = f"SEC Form 4, {insider.since} 이후. " + ("; ".join(bits) if bits else "임원 매수 보고 없음") + ". 옵션 행사는 매수가 아니어서 빠짐."
    out.append(Section("임원 장내 매수", lines, note))

    holders = [f"{h.manager}(13F)" for h in hits if h.weight > 0]
    holders += [f"{r.holder}({r.kind})" for k in HOLDING_KINDS for r in by[k]]
    out.append(Section("보유 중첩(확인된 전문가·기관의 공동 보유)", [", ".join(holders) + f" — {len(holders)}곳"] if len(holders) >= 2 else [],
                       "보유자가 하나뿐이면 중첩이 아님: " + holders[0] if len(holders) == 1 else ""))
    if country == "한국":
        out[2].note = "13F는 미국 상장 증권만 담아 한국 종목은 대상이 아님. 직접 입력한 지수 비중만 표시"
    return out
