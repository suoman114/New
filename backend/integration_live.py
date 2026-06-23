#!/usr/bin/env python3
"""실 연동 라이브 데모 — 실 자원으로 전체 루프를 돈다 (HTTP/UDP/DB/RMQ).

구성(모두 실제):
  1) 실 uvicorn HTTP 서버 부팅 → /api/health, /api/integration/health 호출(실 HTTP)
  2) FakeSUT: 실 UDP 소켓으로 주입된 SIP/RTP 를 수신(녹취서버 대역 모방)
  3) 실 DB(있으면 MariaDB+pymysql, 없으면 SQLite) TBL_RECORD_INFO + 실 파일시스템 기록
  4) (브로커 가동 시) 실 RabbitMQ shadow monitor 로 floor(TAKEN/IDLE) consume
  5) AppState.validate_session 으로 FILE/DB/AUDIO/RMQ 대조 → 검증 리포트 출력

실제 uVCS 가 있으면 UVCS_DB_*/RMQ_*/REC_* 환경변수만 바꿔 그대로 붙는다.

실행:  cd backend && python integration_live.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

from sim.platform.config import SimConfig, load_config
from sim.rtp import RtpPacket
from sim.validator.reconstruct import reconstruct_from_packets

RMQ_EXCHANGE = "uvcs.live"

SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS TBL_RECORD_INFO (
  SIP_CALLID TEXT, FILE_INDEX INTEGER, RECORD_TYPE TEXT, AUDIO_EXTENSION TEXT,
  VIDEO_EXTENSION TEXT, CREATE_TIME TEXT, END_TIME TEXT, DURATION_TIME TEXT,
  CALLER_FILE_NAME TEXT, CALLEE_FILE_NAME TEXT, REASON_CORD INTEGER, REASON_STR TEXT,
  FILE_STATUS INTEGER, MCPTT_GROUP_ID TEXT, GROUP_DISPLAY_NAME TEXT, USER_NAME TEXT, FPS TEXT
);"""

INSERT_SQL = (
    "INSERT INTO TBL_RECORD_INFO (SIP_CALLID, FILE_INDEX, RECORD_TYPE, AUDIO_EXTENSION,"
    " CREATE_TIME, END_TIME, DURATION_TIME, CALLER_FILE_NAME, REASON_CORD, REASON_STR,"
    " FILE_STATUS, MCPTT_GROUP_ID) VALUES (:cid,:fi,:rt,:ae,:ct,:et,:dt,:cf,:rc,:rs,:fs,:gid)")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _port_up(host: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def _mariadb_up() -> bool:
    return _port_up("127.0.0.1", 3306)


def _broker_up() -> bool:
    return _port_up("127.0.0.1", 5672)


def http_get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read().decode()


def real_http_smoke(env: dict) -> None:
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
        print("  [HTTP] /api/health             →", http_get(base + "/api/health"))
        print("  [HTTP] /api/integration/health →", http_get(base + "/api/integration/health"))
    finally:
        proc.terminate()
        proc.wait(timeout=5)


async def _publish_floor(call_id: str, talk_spurts) -> None:
    """실 브로커로 VCMM→VCMC recording_change(req+res, TAKEN/IDLE) 발행."""
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
            req = {"header": {"type": "recording_change_req", "callId": call_id,
                              "transactionId": txn, "msgFrom": "VCMM_0", "trxType": 0,
                              "reasonCode": 2000, "reason": "Success"},
                   "body": {"type": floor, "caller_mdn": sp.talker_mdn,
                            "audio_extension": "awb"}}
            res = {"header": {"type": "recording_change_res", "callId": call_id,
                              "transactionId": txn, "msgFrom": "VCMC", "trxType": 0,
                              "reasonCode": 0},
                   "body": {"type": floor, "file_index": 5000 + n,
                            "save_file_name": f"M_{call_id}_{sp.talker_digits}"}}
            for m in (req, res):
                await ex.publish(aio_pika.Message(json.dumps(m).encode()),
                                 routing_key="rec.change")
    await conn.close()


class FakeSUT(asyncio.DatagramProtocol):
    """실 UDP 소켓으로 RTP 를 수신하는 녹취서버 대역."""

    def __init__(self):
        self.rtp: list[bytes] = []

    def datagram_received(self, data, addr):
        try:
            if data[:1] and (data[0] >> 6) == 2:        # RTP V=2
                self.rtp.append(data)
        except Exception:
            pass


def _sut_write_db(cfg: SimConfig, rows: list[dict]) -> None:
    """FakeSUT(녹취서버) 산출물: TBL_RECORD_INFO 에 실제 INSERT (sqlite/mysql 공통)."""
    eng = create_engine(cfg.sut.db.url())
    with eng.begin() as cx:
        if cfg.sut.db.driver.startswith("sqlite"):
            cx.execute(text(SQLITE_DDL))
        cx.execute(text("DELETE FROM TBL_RECORD_INFO"))
        for r in rows:
            cx.execute(text(INSERT_SQL), r)
    eng.dispose()


async def live_loop(cfg: SimConfig, rec_root: str) -> None:
    from api.state import AppState

    loop = asyncio.get_running_loop()
    sink = FakeSUT()
    rtp_t, _ = await loop.create_datagram_endpoint(
        lambda: sink, local_addr=(cfg.tapper.rtp_host, cfg.tapper.rtp_port_base))
    rtp_t.get_extra_info("socket").setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                                              16 * 1024 * 1024)
    sip_t, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, local_addr=(cfg.tapper.sip_host, cfg.tapper.sip_port))

    state = AppState(config=cfg)
    rmq_live = cfg.rmq.enabled and _broker_up()
    if rmq_live:
        import aio_pika
        c = await aio_pika.connect_robust(host=cfg.rmq.host, port=cfg.rmq.port,
                                          login=cfg.rmq.user, password=cfg.rmq.password)
        cch = await c.channel()
        await cch.declare_exchange(RMQ_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
        await c.close()
        connected = await state.start_rmq()
        print(f"  [RMQ ] shadow monitor connected = {connected}")
    try:
        sid = (await state.run_scenario("MCPTT-GROUP-FLOOR", wait=True))[0]
        run = state.run_results[sid]
        await asyncio.sleep(0.1)
        print(f"  [WIRE] FakeSUT 수신 RTP packets = {len(sink.rtp)}")

        if rmq_live:
            await _publish_floor(run.call_id, run.expectations.talk_spurts)
            for _ in range(50):
                tr = state.rmq.trackers.get(run.call_id)
                if tr and tr.change_sequence == run.expectations.rmq_change_sequence:
                    break
                await asyncio.sleep(0.1)
            tr = state.rmq.trackers.get(run.call_id)
            print(f"  [RMQ ] consume floor seq = {tr.change_sequence if tr else None}")

        # FakeSUT 산출물: 수신 RTP → .awb 파일 + TBL_RECORD_INFO 행
        captured = sorted((RtpPacket.unpack(p) for p in sink.rtp), key=lambda r: r.sequence)
        by_ssrc: dict[int, list[RtpPacket]] = {}
        for pk in captured:
            by_ssrc.setdefault(pk.ssrc, []).append(pk)
        ne = [s for s in run.expectations.talk_spurts if not s.expect_empty]
        sent = [s for s in run.spurts if s.sent_packets]
        db_rows = []
        for i, (exp, sr) in enumerate(zip(ne, sent)):
            awb = reconstruct_from_packets(by_ssrc.get(sr.ssrc, []), mode_set_max=8)
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            fidx = 5000 + i
            name = f"M_{run.call_id}_{exp.talker_digits}_{exp.group_id}_{ts}_{fidx}"
            d = Path(rec_root) / "MCPTT" / "VOICE"
            d.mkdir(parents=True, exist_ok=True)
            (d / (name + ".awb")).write_bytes(awb)
            db_rows.append(dict(cid=run.call_id, fi=fidx, rt="AUDIO", ae="awb",
                                ct=str(datetime.now()), et=str(datetime.now()),
                                dt=str(timedelta(seconds=1)), cf=name, rc=2, rs="SUCCESS",
                                fs=2, gid=exp.group_id))
        _sut_write_db(cfg, db_rows)
        print(f"  [SUT ] .awb {len(db_rows)}개 + TBL_RECORD_INFO {len(db_rows)}행 "
              f"({cfg.sut.db.driver.split('+')[0]})")

        result = await state.validate_session(sid)
        print(f"\n  [검증] call_id={run.call_id}")
        for it in result.items:
            mark = "✓" if it.status == "PASS" else ("·" if it.status == "SKIP" else "✗")
            print(f"     {mark} [{it.category:<5}] {it.name:<26} {it.status}  {it.detail}")
        npass = sum(1 for i in result.items if i.status == "PASS")
        nfail = sum(1 for i in result.items if i.status == "FAIL")
        print(f"\n  == 최종: {'PASS ✅' if result.passed else 'FAIL ❌'} "
              f"({npass} PASS / {nfail} FAIL) ==")
    finally:
        if rmq_live:
            await state.rmq.close()
        rtp_t.close()
        sip_t.close()


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="uvcs-live-")
    rec_root = os.path.join(tmp, "ramdisk")
    os.makedirs(rec_root, exist_ok=True)

    maria = _mariadb_up()
    if maria:
        dbenv = {"UVCS_DB_DRIVER": "mysql+pymysql", "UVCS_DB_HOST": "127.0.0.1",
                 "UVCS_DB_PORT": "3306", "UVCS_DB_USER": "uvcs",
                 "UVCS_DB_PASSWORD": "uvcspw", "UVCS_DB_NAME": "uvcs"}
    else:
        dbenv = {"UVCS_DB_DRIVER": "sqlite", "UVCS_DB_NAME": os.path.join(tmp, "uvcs.db")}
    rmq_on = _broker_up()
    env = {**dbenv, "UVCS_RMQ_ENABLED": "true" if rmq_on else "false",
           "UVCS_RMQ_EXCHANGE": RMQ_EXCHANGE,
           "UVCS_REC_RAMDISK": rec_root, "UVCS_REC_NAS": rec_root}
    for k, v in env.items():
        os.environ[k] = v

    if rmq_on:
        async def _declare():
            import aio_pika
            c = await aio_pika.connect_robust(host="127.0.0.1", port=5672,
                                              login="guest", password="guest")
            ch = await c.channel()
            await ch.declare_exchange(RMQ_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
            await c.close()
        asyncio.run(_declare())

    print(f"=== 실 자원: DB={'MariaDB' if maria else 'SQLite'}  "
          f"RabbitMQ={'UP' if rmq_on else 'down'} ===\n")
    print("=== 1. 실 HTTP 서버(uvicorn) 부팅 + 실제 HTTP 호출 ===")
    real_http_smoke(env)

    print("\n=== 2. 실 UDP 주입 + 실 DB/파일 + (실 RMQ) + 검증 루프 ===")
    cfg = load_config()
    cfg.tapper.rtp_port_count = 1     # FakeSUT 단일 RTP 포트 재사용
    asyncio.run(live_loop(cfg, rec_root))
    print(f"\n(작업 디렉토리: {tmp})")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
