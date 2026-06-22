"""설정 로더.

`config/sim.yaml` 을 읽어 타입 검증된 `SimConfig` 로 제공한다.
하드코딩 금지 원칙(CLAUDE.md §8.3): 모든 host/port/경로는 여기서만 온다.
"""

from __future__ import annotations

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
    """YAML 을 읽어 SimConfig 로 검증/반환. path 미지정 시 자동 탐색."""
    cfg_path = Path(path) if path else find_config_path()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return SimConfig.model_validate(data)
