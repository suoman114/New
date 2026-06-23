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
    try:
        # 1) 시나리오 실행 → 실제 UDP 로 SIP/RTP 주입(FakeSUT 가 수신)
        sids = await state.run_scenario("MCPTT-GROUP-FLOOR", wait=True)
        sid = sids[0]
        run = state.run_results[sid]
        await asyncio.sleep(0.1)
        print(f"  [WIRE] FakeSUT 수신 RTP packets = {len(sink.rtp)}")

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
        rtp_t.close()
        sip_t.close()


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="uvcs-live-")
    db_path = os.path.join(tmp, "uvcs.db")
    rec_root = os.path.join(tmp, "ramdisk")
    os.makedirs(rec_root, exist_ok=True)

    env = {
        "UVCS_DB_DRIVER": "sqlite", "UVCS_DB_NAME": db_path,
        "UVCS_RMQ_ENABLED": "false",
        "UVCS_REC_RAMDISK": rec_root, "UVCS_REC_NAS": rec_root,
    }
    for k, v in env.items():
        os.environ[k] = v

    print("=== 1. 실 HTTP 서버(uvicorn) 부팅 + 실제 HTTP 호출 ===")
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
