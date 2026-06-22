"""RMQ(JSON) 메시지 디코딩 (docs/specs/observed-from-logs.md §2, rmq-protocol.md).

실제 메시지: UUID transactionId, 성공 reasonCode=2000, heartbeat_indi, caller/callee 분리,
recording_change(MCPTT floor TAKEN/IDLE), recording_update(ReINVITE).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

# reasonCode 의미 (as-built)
RC_REQUEST = 0           # 요청/미결 상태
RC_SUCCESS = 2000        # 성공
RC_ERRORS = {
    3001: "Callee SDP is null",
    4001: "Session is not exist.",
}

# 메시지 타입 → (송신, 수신) 추정 peer (FlowEvent direction=SUT-INTERNAL)
PEER_HINT = {
    "heartbeat_indi": ("VCMM_0", "VCSM"),
    "recording_start_req": ("VCSM", "VCMM_0"),
    "recording_start_res": ("VCMM_0", "VCSM"),
    "recording_update_req": ("VCSM", "VCMM_0"),
    "recording_update_res": ("VCMM_0", "VCSM"),
    "recording_stop_req": ("VCSM", "VCMM_0"),
    "recording_stop_res": ("VCMM_0", "VCSM"),
    "recording_change_req": ("VCMM_0", "VCMC"),
    "recording_change_res": ("VCMC", "VCMM_0"),
}


@dataclass
class RmqHeader:
    type: str = ""
    call_id: Optional[str] = None
    transaction_id: Optional[str] = None
    msg_from: Optional[str] = None
    trx_type: Optional[int] = None
    reason_code: Optional[int] = None
    reason: Optional[str] = None


@dataclass
class RmqMessage:
    header: RmqHeader
    body: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return self.header.type

    @property
    def is_success(self) -> bool:
        return self.header.reason_code == RC_SUCCESS

    @property
    def is_error(self) -> bool:
        return self.header.reason_code in RC_ERRORS

    @property
    def floor_type(self) -> Optional[str]:
        """recording_change 의 body.type (TAKEN/IDLE)."""
        return self.body.get("type") if self.type.startswith("recording_change") else None


def decode(data: str | bytes | dict) -> RmqMessage:
    obj = data if isinstance(data, dict) else json.loads(
        data.decode("utf-8") if isinstance(data, bytes) else data)
    h = obj.get("header", {}) or {}
    header = RmqHeader(
        type=h.get("type", ""),
        call_id=h.get("callId"),
        transaction_id=str(h["transactionId"]) if h.get("transactionId") is not None else None,
        msg_from=h.get("msgFrom"),
        trx_type=h.get("trxType"),
        reason_code=h.get("reasonCode"),
        reason=h.get("reason"),
    )
    return RmqMessage(header=header, body=obj.get("body", {}) or {}, raw=obj)
