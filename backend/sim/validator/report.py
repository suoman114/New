"""검증 facade: 파일/DB/오디오 항목을 모아 ValidationResult 로 집계.

검증 결과는 FlowEvent(channel=VALIDATION)로도 발행하여 대시보드 리포트에 반영한다.
"""

from __future__ import annotations

from typing import Optional

from ..platform.db import RecordInfoRepository
from ..platform.eventbus import EventBus
from ..platform.models import FlowEvent, ValidationItem, ValidationResult
from ..scenario.expectations import ScenarioExpectations
from .audio_check import compare_awb
from .db_check import check_db
from .file_check import check_files
from .reconstruct import reconstruct_awb


class Validator:
    """SUT 산출물 검증기.

    repo(DB) / fs_root(파일) / server_files(call별 실제 파일 bytes) 는 가용한 것만 검증한다.
    server_files: {spurt_index: bytes} — 오디오 골든 비교용(파일시스템 접근 대안/테스트).
    """

    def __init__(self, *, repo: Optional[RecordInfoRepository] = None,
                 fs_root: Optional[str] = None, bus: Optional[EventBus] = None,
                 mode_set_max: int = 8) -> None:
        self._repo = repo
        self._fs_root = fs_root
        self._bus = bus
        self._mode = mode_set_max

    async def validate(self, exp: ScenarioExpectations, spurts: list) -> ValidationResult:
        """expectations + 송출 결과(spurts)로 검증. spurts[i].frames 로 골든 재구성."""
        result = ValidationResult(session_id=exp.session_id, call_id=exp.call_id)

        # 파일 검증
        if self._fs_root:
            for item in check_files(exp, self._fs_root):
                result.add(item)

        # DB 검증
        if self._repo is not None:
            for item in check_db(exp, self._repo):
                result.add(item)

        # 오디오 골든 비교 (송출 frame → 골든 .awb vs 서버 파일)
        for sr in spurts:
            frames = getattr(sr, "frames", None)
            if not frames:
                continue
            golden = reconstruct_awb(frames, mode_set_max=self._mode)
            actual = self._server_file_bytes(sr)
            if actual is not None:
                item = compare_awb(golden, actual, name=f"audio[{sr.index}]")
                result.add(item)

        await self._emit(result)
        return result

    def reconstruct_golden(self, spurt) -> bytes:
        """단일 spurt 의 골든 .awb (디버그/대시보드용)."""
        return reconstruct_awb(getattr(spurt, "frames", []), mode_set_max=self._mode)

    def _server_file_bytes(self, spurt) -> Optional[bytes]:
        """서버 저장 파일 bytes 조회. fs_root 가 있으면 파일에서, 없으면 None."""
        if not self._fs_root:
            return None
        from .file_check import find_file
        # spurt 에 대응하는 expectation regex 가 필요하나, 여기서는 digits 로 단순 탐색
        from pathlib import Path
        digits = "".join(c for c in spurt.talker_mdn if c.isdigit())
        if digits.startswith("82"):
            digits = digits[2:]
        found = find_file(self._fs_root, rf"^M_.+_{digits}_.+\.awb$")
        if found is None:
            return None
        return Path(found).read_bytes()

    async def _emit(self, result: ValidationResult) -> None:
        if self._bus is None:
            return
        fails = [i for i in result.items if i.status == "FAIL"]
        await self._bus.publish(FlowEvent(
            session_id=result.session_id, call_id=result.call_id, channel="VALIDATION",
            direction="SIM-INTERNAL", peer="validator",
            label="PASS" if result.passed else "FAIL",
            severity="info" if result.passed else "error",
            summary=f"{len(result.items)}개 항목, 실패 {len(fails)}",
            payload={"items": [i.model_dump() for i in result.items]},
        ))


def aggregate(items: list[ValidationItem], *, session_id: str = "",
              call_id: str = "") -> ValidationResult:
    res = ValidationResult(session_id=session_id, call_id=call_id)
    res.items = list(items)
    return res
