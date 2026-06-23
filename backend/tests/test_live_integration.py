"""실 연동 통합 테스트 (외부 서비스 없이 가능한 실 자원):
  - 실 SQLite DB → SqlAlchemyRecordInfoRepository 의 실제 SQL SELECT 경로
  - 실 UDP 소켓 → 주입한 SIP/RTP 가 와이어로 나가 정확히 도착하는지 캡처/파싱
"""

import asyncio
import socket
import sqlite3

from sim.platform.config import DbConfig, TapperConfig
from sim.platform.db import SqlAlchemyRecordInfoRepository
from sim.platform.eventbus import EventBus
from sim.rtp import RtpPacket
from sim.rtp.amrwb import parse_oa
from sim.scenario import ScenarioEngine
from sim.scenario.loader import Scenario
from sim.sip.messages import SipMessage
from sim.tapper.port_alloc import RtpPortAllocator
from sim.tapper.udp_sender import TapperFeeder
from sim.validator import Validator
from sim.validator.reconstruct import reconstruct_from_packets

_DDL = """
CREATE TABLE TBL_RECORD_INFO (
  SIP_CALLID TEXT, FILE_INDEX INTEGER, RECORD_TYPE TEXT, AUDIO_EXTENSION TEXT,
  VIDEO_EXTENSION TEXT, CREATE_TIME TEXT, END_TIME TEXT, DURATION_TIME TEXT,
  CALLER_FILE_NAME TEXT, CALLEE_FILE_NAME TEXT, REASON_CODE INTEGER, REASON_STR TEXT,
  FILE_STATUS INTEGER, MCPTT_GROUP_ID TEXT, GROUP_DISPLAY_NAME TEXT, USER_NAME TEXT, FPS TEXT
);
"""


def test_real_sqlite_repository(tmp_path):
    """실 SQLite 에 TBL_RECORD_INFO 를 만들고 실제 SQL SELECT 로 조회."""
    db_path = str(tmp_path / "uvcs.db")
    con = sqlite3.connect(db_path)
    con.executescript(_DDL)
    con.execute(
        "INSERT INTO TBL_RECORD_INFO (SIP_CALLID, FILE_INDEX, RECORD_TYPE, AUDIO_EXTENSION,"
        " FILE_STATUS, MCPTT_GROUP_ID, CALLER_FILE_NAME) VALUES (?,?,?,?,?,?,?)",
        ("call-xyz", 5008, "AUDIO", "awb", 2, "98152020001", "M_call-xyz_585102802_x"))
    con.execute(
        "INSERT INTO TBL_RECORD_INFO (SIP_CALLID, FILE_INDEX, AUDIO_EXTENSION, FILE_STATUS)"
        " VALUES (?,?,?,?)", ("call-xyz", 5007, "awb", 2))
    con.commit()
    con.close()

    repo = SqlAlchemyRecordInfoRepository(
        DbConfig(driver="sqlite", database=db_path, readonly=True))
    rows = repo.by_call_id("call-xyz")
    assert [r.file_index for r in rows] == [5007, 5008]    # FILE_INDEX ASC, 실 SQL ORDER BY
    r = repo.by_call_id_file_index("call-xyz", 5008)
    assert r.record_type == "AUDIO" and r.file_status == 2
    assert r.mcptt_group_id == "98152020001"
    assert repo.by_call_id_file_index("call-xyz", 9999) is None


def _mcptt_scenario() -> Scenario:
    return Scenario.model_validate({
        "id": "LIVE", "service_type": "MCPTT",
        "media": {"mode_set": [8], "pt": 98},
        "mcptt": {"group_id": "98152020001", "members": [{"mdn": "tel:+82585102802"}]},
        "floor_sequence": [{"talker": "tel:+82585102802", "duration_sec": 0.2}],
    })


async def test_real_udp_injection_roundtrip():
    """실 UDP 소켓으로 주입한 SIP/RTP 를 캡처해 와이어 바이트가 정확함을 검증."""
    loop = asyncio.get_running_loop()
    sip_pkts: list[bytes] = []
    rtp_pkts: list[bytes] = []

    class SipSink(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            sip_pkts.append(data)

    class RtpSink(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            rtp_pkts.append(data)

    sip_t, _ = await loop.create_datagram_endpoint(SipSink, local_addr=("127.0.0.1", 0))
    rtp_t, _ = await loop.create_datagram_endpoint(RtpSink, local_addr=("127.0.0.1", 0))
    sip_port = sip_t.get_extra_info("sockname")[1]
    rtp_port = rtp_t.get_extra_info("sockname")[1]

    cfg = TapperConfig(sip_host="127.0.0.1", sip_port=sip_port,
                       rtp_host="127.0.0.1", rtp_port_base=rtp_port, rtp_port_count=1)
    bus = EventBus()
    feeder = TapperFeeder(cfg, bus=bus)
    await feeder.start()
    try:
        engine = ScenarioEngine(feeder, bus=bus,
                                port_alloc=RtpPortAllocator(rtp_port, 1), realtime=False)
        run = await engine.run(_mcptt_scenario(), session_id="live-1")
        await asyncio.sleep(0.1)                      # 와이어 도착 대기
    finally:
        await feeder.close()
        sip_t.close()
        rtp_t.close()

    # SIP: INVITE/ACK/BYE 가 실제로 와이어에 도착
    methods = [SipMessage.parse(p).method for p in sip_pkts]
    assert "INVITE" in methods and "ACK" in methods and "BYE" in methods

    # RTP: 10 패킷(0.2s) 도착, 파싱되어 AMR-WB frame 복원
    assert len(rtp_pkts) == 10
    captured = sorted((RtpPacket.unpack(p) for p in rtp_pkts), key=lambda r: r.sequence)
    assert all(r.payload_type == 98 for r in captured)
    assert parse_oa(captured[0].payload)[0].ft == 8

    # 캡처한 와이어 패킷으로 재구성한 골든 == 엔진이 의도한 골든 (전송 무손실 입증)
    wire_golden = reconstruct_from_packets(captured, mode_set_max=8)
    intended_golden = Validator(mode_set_max=8).reconstruct_golden(run.spurts[0])
    assert wire_golden == intended_golden


def _maria_repo():
    """실 MariaDB(uvcs) 연결 가능하면 production 리포지토리, 아니면 None."""
    if not _port_up("127.0.0.1", 3306):
        return None
    try:
        import pymysql
        con = pymysql.connect(host="127.0.0.1", port=3306, user="uvcs",
                              password="uvcspw", database="uvcs", connect_timeout=2)
        con.close()
        return DbConfig(driver="mysql+pymysql", host="127.0.0.1", port=3306,
                        user="uvcs", password="uvcspw", database="uvcs", readonly=True)
    except Exception:
        return None


def _port_up(host: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def test_real_mariadb_repository():
    """실 MariaDB + production 드라이버(mysql+pymysql) SELECT + TIME→str 정규화."""
    cfg = _maria_repo()
    if cfg is None:
        import pytest
        pytest.skip("MariaDB(uvcs) 미가동")
    import pymysql
    con = pymysql.connect(host="127.0.0.1", port=3306, user="uvcs",
                          password="uvcspw", database="uvcs")
    with con.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS TBL_RECORD_INFO ("
            "SIP_CALLID VARCHAR(255), FILE_INDEX INT, RECORD_TYPE VARCHAR(32),"
            "AUDIO_EXTENSION VARCHAR(16), VIDEO_EXTENSION VARCHAR(16), CREATE_TIME DATETIME,"
            "END_TIME DATETIME, DURATION_TIME TIME, CALLER_FILE_NAME VARCHAR(512),"
            "CALLEE_FILE_NAME VARCHAR(512), REASON_CODE INT, REASON_STR VARCHAR(64),"
            "FILE_STATUS INT, MCPTT_GROUP_ID VARCHAR(64), GROUP_DISPLAY_NAME VARCHAR(128),"
            "USER_NAME VARCHAR(128), FPS VARCHAR(16))")
        cur.execute("DELETE FROM TBL_RECORD_INFO WHERE SIP_CALLID=%s", ("pytest-maria",))
        cur.execute(
            "INSERT INTO TBL_RECORD_INFO (SIP_CALLID,FILE_INDEX,RECORD_TYPE,AUDIO_EXTENSION,"
            "DURATION_TIME,FILE_STATUS,MCPTT_GROUP_ID,CALLER_FILE_NAME) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            ("pytest-maria", 5008, "AUDIO", "awb", "00:00:01", 2, "98152020001",
             "M_pytest-maria_585102802_x"))
    con.commit()
    con.close()

    repo = SqlAlchemyRecordInfoRepository(cfg)
    r = repo.by_call_id_file_index("pytest-maria", 5008)
    assert r is not None and r.file_status == 2 and r.audio_extension == "awb"
    assert r.mcptt_group_id == "98152020001"
    # MariaDB TIME → timedelta → str 정규화 검증
    assert isinstance(r.duration_time, str) and "0:00:01" in r.duration_time
