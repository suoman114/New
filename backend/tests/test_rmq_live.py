"""실 RabbitMQ 브로커 연동 테스트 (브로커 미가동 시 skip).

RmqMonitor 의 실제 consume 경로(start→declare→bind→_consume)를 실 브로커로 검증한다.
"""

import asyncio
import json
import socket

import pytest

from sim.platform.config import RmqConfig
from sim.platform.eventbus import EventBus
from sim.rmq import RmqMonitor


def _broker_up(host="127.0.0.1", port=5672) -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


pytestmark = pytest.mark.skipif(not _broker_up(), reason="RabbitMQ 브로커 미가동")

EXCHANGE = "uvcs.live.test"


async def _publish(routing_key: str, payload: dict) -> None:
    import aio_pika

    conn = await aio_pika.connect_robust(host="127.0.0.1", port=5672,
                                         login="guest", password="guest")
    ch = await conn.channel()
    ex = await ch.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    await ex.publish(aio_pika.Message(json.dumps(payload).encode()), routing_key=routing_key)
    await conn.close()


def _msg(typ_body, call_id, txn):
    return {"header": {"type": "recording_change_req", "callId": call_id,
                       "transactionId": txn, "msgFrom": "VCMM_0", "trxType": 0,
                       "reasonCode": 2000, "reason": "Success"},
            "body": {"type": typ_body}}


async def test_rmq_monitor_consumes_from_real_broker():
    import aio_pika

    # 1) exchange 선언(실 VCMM 대역) — monitor 는 passive 로 붙으므로 미리 존재해야 함
    conn = await aio_pika.connect_robust(host="127.0.0.1", port=5672,
                                         login="guest", password="guest")
    ch = await conn.channel()
    await ch.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    await conn.close()

    # 2) 실 브로커에 RmqMonitor 연결 + consume 시작
    bus = EventBus()
    cfg = RmqConfig(enabled=True, host="127.0.0.1", port=5672,
                    user="guest", password="guest", exchange=EXCHANGE)
    mon = RmqMonitor(cfg, bus=bus, session_id="live")
    ok = await mon.start()
    assert ok is True and mon.enabled is True
    await asyncio.sleep(0.3)

    # 3) VCMM→VCMC floor 메시지를 실 브로커로 발행
    call_id = "tb2bua-live-call"
    await _publish("rec.change", _msg("TAKEN", call_id, "x1"))
    await _publish("rec.change", _msg("IDLE", call_id, "x2"))

    # 4) 모니터가 실제로 consume 했는지 확인 (브로커→네트워크→consumer)
    for _ in range(50):
        if call_id in mon.trackers and \
           mon.tracker_for(call_id).change_sequence == ["TAKEN", "IDLE"]:
            break
        await asyncio.sleep(0.1)
    await mon.close()

    assert mon.tracker_for(call_id).change_sequence == ["TAKEN", "IDLE"]
    rmq_events = [e for e in bus.recent(channel="RMQ", limit=100) if e.call_id == call_id]
    assert rmq_events and any("TAKEN" in e.label for e in rmq_events)
