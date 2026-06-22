"""시나리오 → 검증 기대값(expectations) 산출.

validator 가 SUT 산출물(파일/DB/RMQ/통계)과 대조하는 단일 출처(CLAUDE.md scenario 계약).
파일명/필드 규칙은 observed-from-logs.md §3 기준.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from .loader import Scenario


def mdn_digits(mdn: str) -> str:
    """tel:+82585102802 → 585102802 (국가코드 82 제거, MCPTT 파일명 규칙)."""
    d = "".join(c for c in mdn if c.isdigit())
    if d.startswith("82"):
        d = d[2:]
    return d


def mdn_local(mdn: str) -> str:
    """IMS 파일명 규칙: +821358512668 → 01358512668 (국가코드 82 → 0)."""
    d = "".join(c for c in mdn if c.isdigit())
    if d.startswith("82"):
        d = "0" + d[2:]
    return d


class TalkSpurtExpectation(BaseModel):
    index: int                       # 0-based 발언 순번(MCPTT) / 레그(IMS)
    talker_mdn: str
    talker_digits: str
    group_id: Optional[str] = None
    duration_ms: int
    frame_count: int
    expect_empty: bool               # duration 0 → "No packets recorded"
    file_prefix: str = "M"
    audio_ext: str = "awb"
    name_regex: str = ""             # 실제 파일명 매칭용 정규식


class ScenarioExpectations(BaseModel):
    session_id: str
    call_id: str
    service_type: str
    talk_spurts: list[TalkSpurtExpectation] = Field(default_factory=list)
    rmq_change_sequence: list[str] = Field(default_factory=list)
    file_status_final: int = 2
    file_index_increments: bool = True
    db_min_rows: int = 0             # 기대 최소 DB 행수(MCPTT=비어있지않은 발언수, IMS=1)


def _frame_count(duration_sec: float) -> int:
    return int(round(duration_sec * 1000)) // 20


def build_expectations(scenario: Scenario, *, session_id: str,
                       call_id: str) -> ScenarioExpectations:
    exp = ScenarioExpectations(session_id=session_id, call_id=call_id,
                               service_type=scenario.service_type)
    if scenario.service_type == "MCPTT":
        _build_mcptt(exp, scenario)
    elif scenario.service_type == "IMS":
        _build_ims(exp, scenario)
    return exp


def _build_mcptt(exp: ScenarioExpectations, scenario: Scenario) -> None:
    group_id = scenario.mcptt.group_id if scenario.mcptt else None
    change_seq: list[str] = []
    for i, fl in enumerate(scenario.floor_sequence):
        digits = mdn_digits(fl.talker)
        fc = _frame_count(fl.duration_sec)
        gid = re.escape(group_id) if group_id else r"\d+"
        # M_{callid...}_{digits}_{gid}_{14자리ts}_{fileindex}.awb
        name_regex = rf"^M_.+_{re.escape(digits)}_{gid}_\d{{14}}_\d+\.awb$"
        exp.talk_spurts.append(TalkSpurtExpectation(
            index=i, talker_mdn=fl.talker, talker_digits=digits, group_id=group_id,
            duration_ms=fc * 20, frame_count=fc, expect_empty=(fc == 0),
            name_regex=name_regex,
        ))
        change_seq += ["TAKEN", "IDLE"]
    exp.rmq_change_sequence = change_seq
    exp.db_min_rows = sum(1 for s in exp.talk_spurts if not s.expect_empty)


def _build_ims(exp: ScenarioExpectations, scenario: Scenario) -> None:
    """IMS: caller/callee 양 레그를 각각 파일로 녹취 (observed-from-logs.md §2.2)."""
    call = scenario.call
    from_no = call.from_no if call else ""
    to_no = call.to_no if call else ""
    f_local, t_local = mdn_local(from_no), mdn_local(to_no)
    ext = "amr" if scenario.media.codec.upper() == "AMR" else "awb"
    fc = _frame_count(scenario.media.duration_sec)
    legs = [
        (0, from_no, f_local, t_local),   # caller leg: I_..._{from}_{to}_ts
        (1, to_no, t_local, f_local),     # callee leg: I_..._{to}_{from}_ts
    ]
    for index, mdn, a, b in legs:
        name_regex = rf"^I_.+_{re.escape(a)}_{re.escape(b)}_\d{{14}}\.{ext}$"
        exp.talk_spurts.append(TalkSpurtExpectation(
            index=index, talker_mdn=mdn, talker_digits=a, group_id=None,
            duration_ms=fc * 20, frame_count=fc, expect_empty=(fc == 0),
            file_prefix="I", audio_ext=ext, name_regex=name_regex,
        ))
    # IMS 는 floor 변화 없음. 1 호 = 1 DB 행(CALLER/CALLEE_FILE_NAME 동시 보유) 가정.
    exp.rmq_change_sequence = []
    exp.db_min_rows = 1
