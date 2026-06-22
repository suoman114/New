"""RMQ 메시지 검증 — 헤더 필수필드, reasonCode, 트랜잭션 페어링, floor 시퀀스.

기대값(ScenarioExpectations)과 대조하여 ValidationItem(category=RMQ)을 생성한다.
"""

from __future__ import annotations

from ..platform.models import ValidationItem
from ..scenario.expectations import ScenarioExpectations
from .decode import RC_ERRORS, RC_SUCCESS, RmqMessage


def validate_header(msg: RmqMessage) -> list[ValidationItem]:
    items: list[ValidationItem] = []
    h = msg.header
    ok = bool(h.type) and bool(h.transaction_id) and bool(h.msg_from)
    items.append(ValidationItem(
        category="RMQ", name=f"{h.type or '?'}.header",
        status="PASS" if ok else "FAIL",
        detail=f"type/transactionId/msgFrom 필수 (type={h.type}, "
               f"txn={h.transaction_id}, from={h.msg_from})"))
    # 응답(_res)은 성공 시 reasonCode=2000
    if h.type.endswith("_res"):
        good = h.reason_code in (RC_SUCCESS, *RC_ERRORS.keys())
        items.append(ValidationItem(
            category="RMQ", name=f"{h.type}.reasonCode",
            status="PASS" if good else "FAIL",
            expected=f"{RC_SUCCESS}|{list(RC_ERRORS)}", actual=h.reason_code,
            detail=h.reason or ""))
    return items


class CallRmqTracker:
    """한 호(call_id)의 RMQ 메시지를 누적/검증."""

    def __init__(self, call_id: str) -> None:
        self.call_id = call_id
        self.messages: list[RmqMessage] = []

    def add(self, msg: RmqMessage) -> None:
        self.messages.append(msg)

    @property
    def change_sequence(self) -> list[str]:
        """recording_change_req 의 floor 시퀀스 (TAKEN/IDLE)."""
        return [m.floor_type for m in self.messages
                if m.type == "recording_change_req" and m.floor_type]

    def transaction_pairs(self) -> dict[str, list[RmqMessage]]:
        pairs: dict[str, list[RmqMessage]] = {}
        for m in self.messages:
            if m.header.transaction_id:
                pairs.setdefault(m.header.transaction_id, []).append(m)
        return pairs

    def validate(self, exp: ScenarioExpectations | None = None) -> list[ValidationItem]:
        items: list[ValidationItem] = []

        # 1) floor 시퀀스 대조
        if exp is not None and exp.rmq_change_sequence:
            obs = self.change_sequence
            items.append(ValidationItem(
                category="RMQ", name="floor_sequence",
                status="PASS" if obs == exp.rmq_change_sequence else "FAIL",
                expected=exp.rmq_change_sequence, actual=obs,
                detail=f"recording_change TAKEN/IDLE 순서 (관찰 {len(obs)}개)"))

        # 2) req↔res 페어링: 각 _req 는 동일 transactionId 의 _res 가 있어야
        by_txn = self.transaction_pairs()
        unmatched = []
        for txn, msgs in by_txn.items():
            types = {m.type for m in msgs}
            has_req = any(t.endswith("_req") for t in types)
            has_res = any(t.endswith("_res") for t in types)
            if has_req and not has_res:
                unmatched.append(txn)
        items.append(ValidationItem(
            category="RMQ", name="txn_pairing",
            status="PASS" if not unmatched else "FAIL",
            actual=f"unmatched={len(unmatched)}",
            detail=f"{len(by_txn)} transaction, 미응답 {len(unmatched)}"))

        # 3) 예기치 않은 에러 reasonCode 표면화
        errors = [(m.type, m.header.reason_code, m.header.reason)
                  for m in self.messages if m.is_error]
        items.append(ValidationItem(
            category="RMQ", name="error_codes",
            status="PASS" if not errors else "FAIL",
            actual=errors, detail=f"에러 응답 {len(errors)}건 "
            f"({', '.join(RC_ERRORS.get(c, str(c)) for _, c, _ in errors)})" if errors else "없음"))

        return items
