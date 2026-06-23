"""설정 로더.

`config/sim.yaml` 을 읽어 타입 검증된 `SimConfig` 로 제공한다.
하드코딩 금지 원칙(CLAUDE.md §8.3): 모든 host/port/경로는 여기서만 온다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class TapperConfig(BaseModel):
    sip_host: str = "127.0.0.1"
    sip_port: int = 10000
    rtp_host: str = "127.0.0.1"
    rtp_port_base: int = 10001
    rtp_port_count: int = 1000


class DbConfig(BaseModel):
    driver: str = "mysql+pymysql"
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "readonly"
    password: str = ""
    database: str = "uvcs"
    table: str = "TBL_RECORD_INFO"
    charset: str = "euckr"
    readonly: bool = True

    def url(self) -> str:
        # SQLite(경량 실 DB: 통합/오프라인) 지원: driver=sqlite, database=파일경로
        if self.driver.startswith("sqlite"):
            return f"sqlite:///{self.database}"
        return (f"{self.driver}://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}?charset={self.charset}")


class SutConfig(BaseModel):
    rec_ramdisk: str = "/home/vcs/ramdisk"
    rec_nas: str = "/home/vcs/nas"
    db: DbConfig = Field(default_factory=DbConfig)


class RmqConfig(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 5672
    vhost: str = "/"
    user: str = "guest"
    password: str = "guest"
    exchange: str = ""


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class SimSection(BaseModel):
    scenarios_dir: str = "config/scenarios"
    audio_dir: str = "audio"
    event_ring_size: int = 5000
    log_dir: str = "logs"


class SimConfig(BaseModel):
    tapper: TapperConfig = Field(default_factory=TapperConfig)
    sut: SutConfig = Field(default_factory=SutConfig)
    rmq: RmqConfig = Field(default_factory=RmqConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    sim: SimSection = Field(default_factory=SimSection)
    inject_mode: str = "tapper_udp"   # tapper_udp(기본) | pcap_mirror(2차)


def find_config_path(start: Optional[Path] = None) -> Path:
    """저장소 루트의 config/sim.yaml 을 탐색한다."""
    here = (start or Path(__file__).resolve()).parent
    for base in [here, *here.parents]:
        candidate = base / "config" / "sim.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("config/sim.yaml 을 찾을 수 없습니다.")


def load_config(path: Optional[str | Path] = None) -> SimConfig:
    """YAML 을 읽어 SimConfig 로 검증/반환. path 미지정 시 자동 탐색.

    비밀정보/배포 환경값은 환경변수로 override 한다(yaml 에 비밀 미기재).
    """
    cfg_path = Path(path) if path else find_config_path()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg = SimConfig.model_validate(data)
    return _apply_env(cfg)


def _apply_env(cfg: SimConfig) -> SimConfig:
    """환경변수 override (실 서버 통합시험용). 미설정 시 yaml 값 유지."""
    g = os.getenv
    db = cfg.sut.db
    db.driver = g("UVCS_DB_DRIVER", db.driver)     # sqlite 등 실 DB 드라이버 override
    db.host = g("UVCS_DB_HOST", db.host)
    db.port = int(g("UVCS_DB_PORT", str(db.port)))
    db.user = g("UVCS_DB_USER", db.user)
    db.password = g("UVCS_DB_PASSWORD", db.password)
    db.database = g("UVCS_DB_NAME", db.database)
    db.charset = g("UVCS_DB_CHARSET", db.charset)

    r = cfg.rmq
    if g("UVCS_RMQ_ENABLED") is not None:
        r.enabled = g("UVCS_RMQ_ENABLED", "").lower() in ("1", "true", "yes")
    r.host = g("UVCS_RMQ_HOST", r.host)
    r.port = int(g("UVCS_RMQ_PORT", str(r.port)))
    r.user = g("UVCS_RMQ_USER", r.user)
    r.password = g("UVCS_RMQ_PASSWORD", r.password)
    r.exchange = g("UVCS_RMQ_EXCHANGE", r.exchange)

    cfg.sut.rec_ramdisk = g("UVCS_REC_RAMDISK", cfg.sut.rec_ramdisk)
    cfg.sut.rec_nas = g("UVCS_REC_NAS", cfg.sut.rec_nas)
    cfg.inject_mode = g("UVCS_INJECT_MODE", cfg.inject_mode)
    return cfg
