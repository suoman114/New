"""공통 데이터 모델.

핵심은 `FlowEvent` (CLAUDE.md §3.1) — 모든 엔진이 EventBus 로 발행하고 dashboard 가
WebSocket 으로 중계하는 구조화 이벤트. ladder 시각화와 로그 드릴다운이 이 모델 위에서 동작한다.

DB 모델(`RecordInfo`)은 as-built 실제 테이블 `TBL_RECORD_INFO` 를 반영한다
(docs/specs/observed-from-logs.md §4).
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ── 열거형(문자열 상수) ──────────────────────────────────────────────────────
Channel = Literal["SIP", "RTP", "RMQ", "DB", "VALIDATION", "SYS"]
Direction = Literal["SIM->SUT", "SUT->SIM", "SUT-INTERNAL", "SIM-INTERNAL"]
Severity = Literal["info", "warn", "error"]


def _new_event_id() -> str:
    return uuid.uuid4().hex


def _now_ms() -> float:
    """epoch milliseconds (ms 정밀도)."""
    return round(time.time() * 1000.0, 3)


class FlowEvent(BaseModel):
    """호처리 흐름 단위 이벤트 (ladder 노드 = 1 FlowEvent).

    상관키: session_id(시뮬레이터 테스트 세션) + call_id(SIP Call-ID).
    로그 드릴다운 키: event_id → GET /api/events/{event_id}/logs.
    """

    event_id: str = Field(default_factory=_new_event_id)
    ts: float = Field(default_factory=_now_ms)  # epoch ms
    session_id: str = ""
    call_id: Optional[str] = None
    channel: Channel = "SYS"
    direction: Direction = "SIM-INTERNAL"
    peer: str = ""          # 예: "VCTP", "VCSM", "VCMM_0", "VCMC", "UA-Caller"
    label: str = ""         # ladder 노드 라벨 (예: "INVITE", "recording_change_req")
    summary: str = ""       # 한 줄 요약
    payload: dict[str, Any] = Field(default_factory=dict)
    log_ref: str = ""       # 상세 로그 위치 (기본은 event_id)
    severity: Severity = "info"

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        if not self.log_ref:
            # log_ref 기본값 = event_id (logging.LogStore 조회 키와 일치)
            object.__setattr__(self, "log_ref", self.event_id)


# ── 검증 결과 ────────────────────────────────────────────────────────────────
ValidationStatus = Literal["PASS", "FAIL", "SKIP"]
ValidationCategory = Literal["FILE", "DB", "AUDIO", "RMQ", "STATS"]


class ValidationItem(BaseModel):
    """검증 리포트의 개별 항목 (파일/DB/오디오/RMQ/통계)."""

    category: ValidationCategory
    name: str
    status: ValidationStatus
    expected: Any = None
    actual: Any = None
    detail: str = ""        # diff/사유 상세


class ValidationResult(BaseModel):
    """한 세션/호에 대한 검증 결과 집계."""

    session_id: str = ""
    call_id: Optional[str] = None
    items: list[ValidationItem] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(i.status != "FAIL" for i in self.items)

    def add(self, item: ValidationItem) -> "ValidationResult":
        self.items.append(item)
        return self


# ── DB: TBL_RECORD_INFO (as-built) ───────────────────────────────────────────
class RecordInfo(BaseModel):
    """실제 운영 DB 테이블 `TBL_RECORD_INFO` 한 행 (read-only 검증용).

    출처: docs/specs/observed-from-logs.md §4.
    PK 는 (SIP_CALLID, FILE_INDEX). FILE_STATUS 0(저장중)→2(완료).
    """

    sip_callid: str
    file_index: int
    record_type: Optional[str] = None        # AUDIO / VIDEO / AUDIO_VIDEO
    audio_extension: Optional[str] = None     # awb / amr
    video_extension: Optional[str] = None
    create_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_time: Optional[str] = None       # "00:00:00.668"
    caller_file_name: Optional[str] = None
    callee_file_name: Optional[str] = None
    reason_cord: Optional[int] = None         # 실제 컬럼명 오타(REASON_CORD)
    reason_str: Optional[str] = None
    file_status: Optional[int] = None         # 0 저장중 / 1 부분 / 2 완료 / -1 실패
    mcptt_group_id: Optional[str] = None
    group_display_name: Optional[str] = None
    user_name: Optional[str] = None
    fps: Optional[str] = None


# ── 시뮬레이터 세션 상태(세션 테이블용) ───────────────────────────────────────
SessionState = Literal["INIT", "RUNNING", "VALIDATING", "DONE", "ERROR"]


class SessionInfo(BaseModel):
    """대시보드 세션 테이블 1행."""

    session_id: str
    scenario_id: str = ""
    call_id: Optional[str] = None
    service_type: Optional[str] = None        # IMS / MCPTT
    state: SessionState = "INIT"
    started_ms: float = Field(default_factory=_now_ms)
    ended_ms: Optional[float] = None
    validation_passed: Optional[bool] = None
    summary: str = ""

    def duration(self) -> Optional[timedelta]:
        if self.ended_ms is None:
            return None
        return timedelta(milliseconds=self.ended_ms - self.started_ms)
