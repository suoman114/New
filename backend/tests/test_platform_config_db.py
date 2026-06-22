"""platform.config / platform.db 계약 테스트."""

import pytest

from sim.platform.config import load_config, find_config_path, DbConfig
from sim.platform.db import (
    InMemoryRecordInfoRepository,
    RecordInfoRepository,
    SqlAlchemyRecordInfoRepository,
    row_to_record,
)
from sim.platform.models import RecordInfo


def test_load_repo_config():
    cfg = load_config(find_config_path())
    # as-built 기본값 확인
    assert cfg.tapper.sip_port == 10000
    assert cfg.tapper.rtp_port_base == 10001
    assert cfg.sut.db.table == "TBL_RECORD_INFO"
    assert cfg.sut.db.readonly is True
    assert cfg.inject_mode == "tapper_udp"


def test_db_url_contains_charset():
    db = DbConfig(host="h", port=3306, user="u", password="p", database="d", charset="euckr")
    assert "charset=euckr" in db.url()
    assert db.url().startswith("mysql+pymysql://u:p@h:3306/d")


def test_row_to_record_maps_uppercase_columns():
    row = {
        "SIP_CALLID": "call-abc",
        "FILE_INDEX": 5008,
        "RECORD_TYPE": "AUDIO",
        "AUDIO_EXTENSION": "awb",
        "FILE_STATUS": 2,
        "MCPTT_GROUP_ID": "98152020001",
    }
    rec = row_to_record(row)
    assert isinstance(rec, RecordInfo)
    assert rec.sip_callid == "call-abc"
    assert rec.file_index == 5008
    assert rec.file_status == 2


def test_inmemory_repository_queries():
    repo = InMemoryRecordInfoRepository([
        RecordInfo(sip_callid="c1", file_index=2, file_status=2),
        RecordInfo(sip_callid="c1", file_index=1, file_status=2),
        RecordInfo(sip_callid="c2", file_index=1, file_status=0),
    ])
    # Protocol 준수
    assert isinstance(repo, RecordInfoRepository)

    rows = repo.by_call_id("c1")
    assert [r.file_index for r in rows] == [1, 2]  # FILE_INDEX 오름차순
    assert repo.by_call_id_file_index("c1", 2).file_status == 2
    assert repo.by_call_id_file_index("c2", 99) is None


def test_sqlalchemy_repo_rejects_writable_config():
    with pytest.raises(ValueError):
        SqlAlchemyRecordInfoRepository(DbConfig(readonly=False))
