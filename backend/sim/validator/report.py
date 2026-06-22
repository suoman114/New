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
from .reconstruct import reconstruct_awb, reconstruct_from_packets


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

        # 오디오 골든 비교 (송출 → 골든 .awb vs 서버 파일)
        exp_by_index = {s.index: s for s in exp.talk_spurts}
        for sr in spurts:
            golden = self._golden_for(sr)
            if golden is None:
                continue
            spurt_exp = exp_by_index.get(getattr(sr, "index", -1))
            actual = self._server_file_bytes(spurt_exp)
            if actual is not None:
                item = compare_awb(golden, actual, name=f"audio[{sr.index}]")
                result.add(item)

        await self._emit(result)
        return result

    def _golden_for(self, spurt) -> Optional[bytes]:
        """spurt 의 골든 .awb. 패킷(timestamp)이 있으면 손실/묵음 채움 재구성을 우선."""
        packets = getattr(spurt, "packets", None)
        if packets:
            return reconstruct_from_packets(packets, mode_set_max=self._mode)
        frames = getattr(spurt, "frames", None)
        if frames:
            return reconstruct_awb(frames, mode_set_max=self._mode)
        return None

    def reconstruct_golden(self, spurt) -> bytes:
        """단일 spurt 의 골든 .awb (디버그/대시보드용)."""
        return self._golden_for(spurt) or b""

    def _server_file_bytes(self, spurt_exp) -> Optional[bytes]:
        """기대 파일명 정규식으로 서버 저장 파일 bytes 조회(IMS/MCPTT 공통)."""
        if not self._fs_root or spurt_exp is None or not spurt_exp.name_regex:
            return None
        from pathlib import Path

        from .file_check import find_file
        found = find_file(self._fs_root, spurt_exp.name_regex)
        return Path(found).read_bytes() if found else None

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
