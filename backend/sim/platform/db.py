"""SUT DB(MariaDB) read-only client — `TBL_RECORD_INFO` 조회 전용.

⚠️ 절대 INSERT/UPDATE/DELETE 금지 (CLAUDE.md platform 계약).
repository 패턴으로 실제 DB 없이도 단위테스트가 가능하도록 인터페이스를 분리한다:
  - `RecordInfoRepository` (Protocol)
  - `SqlAlchemyRecordInfoRepository` (실 DB)
  - `InMemoryRecordInfoRepository` (테스트/오프라인)

컬럼 매핑은 as-built 실제 스키마(docs/specs/observed-from-logs.md §4)를 따른다.
"""

from __future__ import annotations

from typing import Iterable, Optional, Protocol, runtime_checkable

from .config import DbConfig
from .models import RecordInfo

# DB 컬럼(대문자) → RecordInfo 필드(소문자) 매핑
_COLUMN_MAP: dict[str, str] = {
    "SIP_CALLID": "sip_callid",
    "FILE_INDEX": "file_index",
    "FTEL": "ftel",
    "ETEL": "etel",
    "CALL_TYPE": "call_type",
    "RECORD_TYPE": "record_type",
    "AUDIO_EXTENSION": "audio_extension",
    "VIDEO_EXTENSION": "video_extension",
    "CREATE_TIME": "create_time",
    "END_TIME": "end_time",
    "DURATION_TIME": "duration_time",
    "CALLER_FILE_NAME": "caller_file_name",
    "CALLEE_FILE_NAME": "callee_file_name",
    "FILE_STATUS": "file_status",
    "REASON_CODE": "reason_code",
    "REASON_STR": "reason_str",
    "FPS": "fps",
    "MCPTT_GROUP_ID": "mcptt_group_id",
    "GROUP_DISPLAY_NAME": "group_display_name",
    "USER_NAME": "user_name",
}


def row_to_record(row: dict) -> RecordInfo:
    """DB row(dict) → RecordInfo. 컬럼명 대소문자 무관, 존재하는 컬럼만 매핑."""
    up = {(k.upper() if isinstance(k, str) else k): v for k, v in row.items()}
    kwargs = {field: up.get(col) for col, field in _COLUMN_MAP.items() if col in up}
    return RecordInfo.model_validate(kwargs)


@runtime_checkable
class RecordInfoRepository(Protocol):
    """검증기가 의존하는 read-only 조회 인터페이스."""

    def by_call_id(self, sip_callid: str) -> list[RecordInfo]:
        """해당 호의 모든 파일 레코드(FILE_INDEX 오름차순)."""
        ...

    def by_call_id_file_index(self, sip_callid: str, file_index: int) -> Optional[RecordInfo]:
        ...


class InMemoryRecordInfoRepository:
    """테스트/오프라인용 인메모리 구현."""

    def __init__(self, rows: Iterable[RecordInfo] | None = None) -> None:
        self._rows: list[RecordInfo] = list(rows or [])

    def add(self, rec: RecordInfo) -> None:
        self._rows.append(rec)

    def by_call_id(self, sip_callid: str) -> list[RecordInfo]:
        out = [r for r in self._rows if r.sip_callid == sip_callid]
        return sorted(out, key=lambda r: r.file_index)

    def by_call_id_file_index(self, sip_callid: str, file_index: int) -> Optional[RecordInfo]:
        for r in self._rows:
            if r.sip_callid == sip_callid and r.file_index == file_index:
                return r
        return None


class SqlAlchemyRecordInfoRepository:
    """실 MariaDB 조회 구현. SELECT 만 수행한다.

    engine 은 지연 생성하며, readonly=False 인 설정은 거부한다(안전장치).
    """

    def __init__(self, cfg: DbConfig) -> None:
        if not cfg.readonly:
            raise ValueError("platform.db 는 read-only 전용입니다 (cfg.readonly=True 필요).")
        self._cfg = cfg
        self._engine = None
        self._table = cfg.table

    def _get_engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine  # 지연 임포트(테스트 시 불필요)

            # 읽기 전용 + 자동커밋 비활성
            self._engine = create_engine(self._cfg.url(), pool_pre_ping=True,
                                         future=True, isolation_level="AUTOCOMMIT")
        return self._engine

    def _query(self, where_sql: str, params: dict) -> list[RecordInfo]:
        from sqlalchemy import text

        # SELECT * 로 스키마 내성 확보(실 테이블의 컬럼이 달라도/추가돼도 안 깨짐).
        # 매핑은 존재하는 컬럼만, 정렬은 Python 에서(FILE_INDEX 없을 수도 있음).
        sql = text(f"SELECT * FROM {self._table} WHERE {where_sql}")
        with self._get_engine().connect() as conn:
            result = conn.execute(sql, params)
            rows = [row_to_record(dict(r._mapping)) for r in result]
        rows.sort(key=lambda r: r.file_index if r.file_index is not None else 0)
        return rows

    def by_call_id(self, sip_callid: str) -> list[RecordInfo]:
        return self._query("SIP_CALLID = :cid", {"cid": sip_callid})

    def by_call_id_file_index(self, sip_callid: str, file_index: int) -> Optional[RecordInfo]:
        rows = self._query("SIP_CALLID = :cid AND FILE_INDEX = :fi",
                           {"cid": sip_callid, "fi": file_index})
        return rows[0] if rows else None


def make_repository(cfg: DbConfig) -> RecordInfoRepository:
    """설정에 따라 실 DB repository 를 생성(검증기/대시보드에서 사용)."""
    return SqlAlchemyRecordInfoRepository(cfg)
