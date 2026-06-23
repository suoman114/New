#!/usr/bin/env python3
"""실 연동 라이브 데모 — 외부 서비스 없이 가능한 실 자원으로 전체 루프를 돈다.

구성(모두 실제):
  1) 실 uvicorn HTTP 서버 부팅 → /api/health, /api/integration/health 호출(실 HTTP)
  2) FakeSUT: 실 UDP 소켓으로 주입된 SIP/RTP 를 수신(녹취서버 대역 모방)
  3) 실 SQLite DB(TBL_RECORD_INFO) + 실 파일시스템(램디스크 대용 tmp)에 서버 산출물 기록
  4) AppState.validate_session 으로 파일/DB/오디오 골든 대조 → 검증 리포트 출력

실제 uVCS 가 있으면 UVCS_DB_*/RMQ_*/REC_* 환경변수만 바꿔 그대로 붙는다.

실행:  cd backend && python integration_live.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from sim.platform.config import SimConfig, load_config
from sim.platform.models import RecordInfo
from sim.rtp import RtpPacket
from sim.validator.reconstruct import reconstruct_from_packets

RMQ_EXCHANGE = "uvcs.live"

DDL = """
CREATE TABLE IF NOT EXISTS TBL_RECORD_INFO (
  SIP_CALLID TEXT, FILE_INDEX INTEGER, RECORD_TYPE TEXT, AUDIO_EXTENSION TEXT,
  VIDEO_EXTENSION TEXT, CREATE_TIME TEXT, END_TIME TEXT, DURATION_TIME TEXT,
  CALLER_FILE_NAME TEXT, CALLEE_FILE_NAME TEXT, REASON_CORD INTEGER, REASON_STR TEXT,
  FILE_STATUS INTEGER, MCPTT_GROUP_ID TEXT, GROUP_DISPLAY_NAME TEXT, USER_NAME TEXT, FPS TEXT
);"""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _broker_up(host="127.0.0.1", port=5672) -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


async def _publish_floor(call_id: str, talk_spurts) -> None:
    """실 브로커로 VCMM→VCMC recording_change(TAKEN/IDLE) 발행."""
    import aio_pika

    conn = await aio_pika.connect_robust(host="127.0.0.1", port=5672,
                                         login="guest", password="guest")
    ch = await conn.channel()
    ex = await ch.declare_exchange(RMQ_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    n = 0
    for sp in talk_spurts:
        for floor in ("TAKEN", "IDLE"):
            n += 1
            txn = f"t{n}"
            # VCMM_0 → VCMC recording_change_req
            req = {"header": {"type": "recording_change_req", "callId": call_id,
                              "transactionId": txn, "msgFrom": "VCMM_0", "trxType": 0,
                              "reasonCode": 2000, "reason": "Success"},
                   "body": {"type": floor, "caller_mdn": sp.talker_mdn,
                            "audio_extension": "awb"}}
            # VCMC → VCMM_0 recording_change_res (동일 transactionId)
            res = {"header": {"type": "recording_change_res", "callId": call_id,
                              "transactionId": txn, "msgFrom": "VCMC", "trxType": 0,
                              "reasonCode": 0},
                   "body": {"type": floor, "file_index": 5000 + n,
                            "save_file_name": f"M_{call_id}_{sp.talker_digits}"}}
            for m in (req, res):
                await ex.publish(aio_pika.Message(json.dumps(m).encode()),
                                 routing_key="rec.change")
    await conn.close()


def http_get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read().decode()


def real_http_smoke(env: dict) -> None:
    """실 uvicorn 서버를 띄워 실제 HTTP 로 health 를 확인."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        env={**os.environ, **env}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                if http_get(base + "/api/health"):
                    break
            except Exception:
                time.sleep(0.2)
        print("  [HTTP] /api/health         →", http_get(base + "/api/health"))
        print("  [HTTP] /api/integration/health →", http_get(base + "/api/integration/health"))
        print("  [HTTP] /api/scenarios      →",
              http_get(base + "/api/scenarios")[:90], "...")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


class FakeSUT(asyncio.DatagramProtocol):
    """실 UDP 소켓으로 SIP/RTP 를 수신하는 녹취서버 대역."""

    def __init__(self):
        self.rtp: list[bytes] = []

    def datagram_received(self, data, addr):
        try:
            if data[:1] and (data[0] >> 6) == 2:        # RTP V=2
                self.rtp.append(data)
        except Exception:
            pass


async def live_loop(cfg: SimConfig, db_path: str, rec_root: str) -> None:
    from api.state import AppState

    loop = asyncio.get_running_loop()
    sink = FakeSUT()
    # 실 UDP 소켓을 RTP 수신 포트에 바인드(녹취서버 모방)
    rtp_t, _ = await loop.create_datagram_endpoint(
        lambda: sink, local_addr=(cfg.tapper.rtp_host, cfg.tapper.rtp_port_base))
    # 무손실 데모를 위해 수신 버퍼 확대(언페이스 버스트 흡수). 실서버는 페이싱/별 프로세스라 불필요.
    rtp_t.get_extra_info("socket").setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16 * 1024 * 1024)
    sip_t, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, local_addr=(cfg.tapper.sip_host, cfg.tapper.sip_port))

    state = AppState(config=cfg)
    rmq_live = cfg.rmq.enabled and _broker_up(cfg.rmq.host, cfg.rmq.port)
    if rmq_live:
        # 실 VCMM 대역: exchange 선언 후 RmqMonitor(shadow consumer) 실 브로커 연결
        import aio_pika
        c = await aio_pika.connect_robust(host=cfg.rmq.host, port=cfg.rmq.port,
                                          login=cfg.rmq.user, password=cfg.rmq.password)
        cch = await c.channel()
        await cch.declare_exchange(RMQ_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
        await c.close()
        connected = await state.start_rmq()
        print(f"  [RMQ ] shadow monitor connected = {connected} (exchange={RMQ_EXCHANGE})")
    try:
        # 1) 시나리오 실행 → 실제 UDP 로 SIP/RTP 주입(FakeSUT 가 수신)
        sids = await state.run_scenario("MCPTT-GROUP-FLOOR", wait=True)
        sid = sids[0]
        run = state.run_results[sid]
        await asyncio.sleep(0.1)
        print(f"  [WIRE] FakeSUT 수신 RTP packets = {len(sink.rtp)}")

        # 1b) 실 브로커로 floor(TAKEN/IDLE) 발행 → RmqMonitor 가 consume
        if rmq_live:
            await _publish_floor(run.call_id, run.expectations.talk_spurts)
            for _ in range(50):
                tr = state.rmq.trackers.get(run.call_id)
                if tr and tr.change_sequence == run.expectations.rmq_change_sequence:
                    break
                await asyncio.sleep(0.1)
            seq = state.rmq.trackers.get(run.call_id)
            print(f"  [RMQ ] consume floor seq = "
                  f"{seq.change_sequence if seq else None}")

        # 2) FakeSUT '녹취 서버' 산출물 생성: 수신 RTP → .awb 파일 + TBL_RECORD_INFO 행
        con = sqlite3.connect(db_path)
        con.executescript(DDL)
        captured = sorted((RtpPacket.unpack(p) for p in sink.rtp), key=lambda r: r.sequence)
        by_ssrc: dict[int, list[RtpPacket]] = {}
        for pk in captured:
            by_ssrc.setdefault(pk.ssrc, []).append(pk)

        ne = [s for s in run.expectations.talk_spurts if not s.expect_empty]
        for i, (exp, sr) in enumerate(zip(ne, [s for s in run.spurts if s.sent_packets])):
            pkts = by_ssrc.get(sr.ssrc, [])
            awb = reconstruct_from_packets(pkts, mode_set_max=8)  # 서버 = 수신패킷 재구성
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            fidx = 5000 + i
            name = f"M_{run.call_id}_{exp.talker_digits}_{exp.group_id}_{ts}_{fidx}"
            d = Path(rec_root) / "MCPTT" / "VOICE"
            d.mkdir(parents=True, exist_ok=True)
            (d / (name + ".awb")).write_bytes(awb)
            con.execute(
                "INSERT INTO TBL_RECORD_INFO (SIP_CALLID, FILE_INDEX, RECORD_TYPE,"
                " AUDIO_EXTENSION, CREATE_TIME, END_TIME, DURATION_TIME, CALLER_FILE_NAME,"
                " REASON_CORD, REASON_STR, FILE_STATUS, MCPTT_GROUP_ID) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (run.call_id, fidx, "AUDIO", "awb",
                 str(datetime.now()), str(datetime.now()), str(timedelta(seconds=1)),
                 name, 2, "SUCCESS", 2, exp.group_id))
        con.commit()
        con.close()
        print(f"  [SUT ] .awb 파일 + TBL_RECORD_INFO {len(ne)}행 기록 (sqlite)")

        # 3) 실 DB + 실 파일 대조 검증
        result = await state.validate_session(sid)
        print(f"\n  [검증] call_id={run.call_id}")
        for it in result.items:
            mark = "✓" if it.status == "PASS" else ("·" if it.status == "SKIP" else "✗")
            print(f"     {mark} [{it.category:<5}] {it.name:<26} {it.status}  {it.detail}")
        print(f"\n  == 최종: {'PASS ✅' if result.passed else 'FAIL ❌'} "
              f"({sum(1 for i in result.items if i.status=='PASS')} PASS / "
              f"{sum(1 for i in result.items if i.status=='FAIL')} FAIL) ==")
    finally:
        if rmq_live:
            await state.rmq.close()
        rtp_t.close()
        sip_t.close()


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="uvcs-live-")
    db_path = os.path.join(tmp, "uvcs.db")
    rec_root = os.path.join(tmp, "ramdisk")
    os.makedirs(rec_root, exist_ok=True)

    rmq_on = _broker_up()
    env = {
        "UVCS_DB_DRIVER": "sqlite", "UVCS_DB_NAME": db_path,
        "UVCS_RMQ_ENABLED": "true" if rmq_on else "false",
        "UVCS_RMQ_EXCHANGE": RMQ_EXCHANGE,
        "UVCS_REC_RAMDISK": rec_root, "UVCS_REC_NAS": rec_root,
    }
    for k, v in env.items():
        os.environ[k] = v

    if rmq_on:
        # exchange 를 먼저 선언해야 HTTP 서브프로세스의 shadow monitor(passive)가 붙는다
        async def _declare():
            import aio_pika
            c = await aio_pika.connect_robust(host="127.0.0.1", port=5672,
                                              login="guest", password="guest")
            ch = await c.channel()
            await ch.declare_exchange(RMQ_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
            await c.close()
        asyncio.run(_declare())

    print("=== 1. 실 HTTP 서버(uvicorn) 부팅 + 실제 HTTP 호출 ===")
    print(f"  (RabbitMQ broker = {'UP' if rmq_on else 'down'})")
    real_http_smoke(env)

    print("\n=== 2. 실 UDP 주입 + 실 SQLite/파일 + 검증 루프 ===")
    cfg = load_config()
    # FakeSUT 는 단일 RTP 포트만 바인드 → 순차 발언이 같은 포트를 재사용하도록 1개로 제한
    # (실 VCMM 은 10001~11000 전 범위를 수신하므로 실서버에선 불필요)
    cfg.tapper.rtp_port_count = 1
    # SQLite 행에 row_to_record 가 매핑되도록 RecordInfo 사용 확인용 no-op
    _ = RecordInfo
    asyncio.run(live_loop(cfg, db_path, rec_root))
    print(f"\n(작업 디렉토리: {tmp})")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
