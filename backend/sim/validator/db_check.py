"""DB 검증: TBL_RECORD_INFO 정합 (docs/specs/observed-from-logs.md §4).

repository(read-only)로 호의 레코드를 조회하여 기대값과 대조한다.
- 비어있지 않은 talk-spurt 마다 1행, FILE_STATUS 최종=2(완료)
- audio_extension=awb, mcptt_group_id 일치, caller_file_name 에 발언자 digits 포함
"""

from __future__ import annotations

from ..platform.db import RecordInfoRepository
from ..platform.models import RecordInfo, ValidationItem
from ..scenario.expectations import ScenarioExpectations


def _match_row(rows: list[RecordInfo], digits: str) -> RecordInfo | None:
    for r in rows:
        if r.caller_file_name and f"_{digits}_" in r.caller_file_name:
            return r
    return None


def check_db(exp: ScenarioExpectations, repo: RecordInfoRepository) -> list[ValidationItem]:
    items: list[ValidationItem] = []
    rows = repo.by_call_id(exp.call_id)
    non_empty = [s for s in exp.talk_spurts if not s.expect_empty]

    items.append(ValidationItem(
        category="DB", name="row_count",
        status="PASS" if len(rows) >= len(non_empty) else "FAIL",
        expected=f">={len(non_empty)}", actual=len(rows),
        detail=f"TBL_RECORD_INFO rows={len(rows)} (non-empty spurts={len(non_empty)})"))

    for spurt in non_empty:
        name = f"db[{spurt.index}] {spurt.talker_digits}"
        row = _match_row(rows, spurt.talker_digits)
        if row is None:
            items.append(ValidationItem(category="DB", name=name, status="FAIL",
                                        detail="해당 발언자 레코드 없음"))
            continue
        # FILE_STATUS 최종 = 2
        items.append(ValidationItem(
            category="DB", name=f"{name}.FILE_STATUS",
            status="PASS" if row.file_status == exp.file_status_final else "FAIL",
            expected=exp.file_status_final, actual=row.file_status))
        # audio_extension
        items.append(ValidationItem(
            category="DB", name=f"{name}.AUDIO_EXTENSION",
            status="PASS" if (row.audio_extension or "").lower() in ("awb", "amr") else "FAIL",
            expected="awb|amr", actual=row.audio_extension))
        # MCPTT_GROUP_ID
        if spurt.group_id is not None:
            items.append(ValidationItem(
                category="DB", name=f"{name}.MCPTT_GROUP_ID",
                status="PASS" if row.mcptt_group_id == spurt.group_id else "FAIL",
                expected=spurt.group_id, actual=row.mcptt_group_id))
    return items
