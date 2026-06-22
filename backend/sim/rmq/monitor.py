"""RMQ shadow monitor — VCSM/VCMC ↔ VCMM 제어 메시지를 패시브 관찰(발신/변조 금지).

aio-pika 로 RabbitMQ 에 붙어 메시지를 tap 한다. 접근 불가/미설정 시 graceful degrade
(모니터 비활성 + 경고)하여 시뮬레이터 전체가 죽지 않게 한다(CLAUDE.md rmq-monitor 계약).

테스트/오프라인: `handle(raw)` 를 직접 호출하여 디코딩→이벤트→트래커 흐름을 검증할 수 있다.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ..platform.config import RmqConfig
from ..platform.eventbus import EventBus
from ..platform.models import FlowEvent
from .decode import PEER_HINT, RmqMessage, decode
from .validate import CallRmqTracker, validate_header

log = logging.getLogger(__name__)


def rmq_flow_event(msg: RmqMessage, *, session_id: str = "") -> FlowEvent:
    """RMQ 메시지 → ladder FlowEvent (header/body 원문 보존)."""
    src, dst = PEER_HINT.get(msg.type, (msg.header.msg_from or "RMQ", "RMQ"))
    label = msg.type
    if msg.floor_type:
        label = f"{msg.type} ({msg.floor_type})"
    sev = "error" if msg.is_error else "info"
    return FlowEvent(
        session_id=session_id, call_id=msg.header.call_id, channel="RMQ",
        direction="SUT-INTERNAL", peer=src, label=label, severity=sev,
        summary=f"{src}→{dst} rc={msg.header.reason_code} {msg.header.reason or ''}".strip(),
        payload={"header": msg.raw.get("header", {}), "body": msg.body},
    )


class RmqMonitor:
    def __init__(self, cfg: RmqConfig, *, bus: Optional[EventBus] = None,
                 session_id: str = "",
                 on_message: Optional[Callable[[RmqMessage], None]] = None) -> None:
        self._cfg = cfg
        self._bus = bus
        self._session_id = session_id
        self._on_message = on_message
        self._conn = None
        self._channel = None
        self.enabled = cfg.enabled
        self.trackers: dict[str, CallRmqTracker] = {}
        self.header_issues: list = []

    def tracker_for(self, call_id: str) -> CallRmqTracker:
        t = self.trackers.get(call_id)
        if t is None:
            t = CallRmqTracker(call_id)
            self.trackers[call_id] = t
        return t

    async def handle(self, raw: str | bytes | dict) -> RmqMessage:
        """단일 메시지 처리: decode → FlowEvent 발행 → 헤더검증 → 트래커 누적."""
        msg = decode(raw)
        if self._bus is not None:
            await self._bus.publish(rmq_flow_event(msg, session_id=self._session_id))
        self.header_issues.extend(
            i for i in validate_header(msg) if i.status == "FAIL")
        if msg.header.call_id:
            self.tracker_for(msg.header.call_id).add(msg)
        if self._on_message:
            self._on_message(msg)
        return msg

    async def start(self) -> bool:
        """RabbitMQ 연결 + 소비 시작. 실패 시 graceful degrade(False 반환)."""
        if not self._cfg.enabled:
            log.warning("[RMQ] monitor disabled by config")
            self.enabled = False
            return False
        try:
            import aio_pika

            self._conn = await aio_pika.connect_robust(
                host=self._cfg.host, port=self._cfg.port, virtualhost=self._cfg.vhost,
                login=self._cfg.user, password=self._cfg.password)
            self._channel = await self._conn.channel()
            queue = await self._channel.declare_queue(exclusive=True, auto_delete=True)
            if self._cfg.exchange:
                exchange = await self._channel.declare_exchange(
                    self._cfg.exchange, aio_pika.ExchangeType.TOPIC, passive=True)
                await queue.bind(exchange, routing_key="#")
            await queue.consume(self._consume, no_ack=True)
            log.info("[RMQ] shadow monitor connected: %s:%s", self._cfg.host, self._cfg.port)
            return True
        except Exception as exc:  # noqa: BLE001  (graceful degrade는 의도적)
            log.warning("[RMQ] connect failed → monitor disabled: %s", exc)
            self.enabled = False
            return False

    async def _consume(self, message) -> None:  # pragma: no cover (실 브로커 필요)
        async with message.process(ignore_processed=True):
            await self.handle(message.body)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
