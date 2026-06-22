"""시나리오 YAML 로더.

config/scenarios/*.yaml → 타입 검증된 `Scenario` 모델. IMS/MCPTT 양식을 모두 수용한다
(extra 필드는 무시). 권위: CLAUDE.md §6, observed-from-logs.md §8.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field


class MediaSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    codec: str = "AMR-WB"
    clock: int = 16000
    octet_align: bool = True
    mode_set: list[int] = Field(default_factory=lambda: [8])
    source_audio: Optional[str] = None
    duration_sec: float = 10
    pt: int = 98


class ImpairSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    packet_loss_pct: float = 0.0
    jitter_ms: int = 0
    inject_silence: bool = False


class FloorEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    talker: str
    duration_sec: float = 0


class McpttSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    group_id: str
    group_display_name: Optional[str] = None
    members: list[dict] = Field(default_factory=list)


class CallSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    outbound: int = 0
    from_no: str = ""
    to_no: str = ""
    conference_id: Optional[int] = None


class Scenario(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str = ""
    service_type: str = "MCPTT"             # IMS | MCPTT
    media: MediaSpec = Field(default_factory=MediaSpec)
    impair: ImpairSpec = Field(default_factory=ImpairSpec)
    mcptt: Optional[McpttSpec] = None
    call: Optional[CallSpec] = None
    floor_sequence: list[FloorEntry] = Field(default_factory=list)
    expect: dict = Field(default_factory=dict)


def load_scenario(path: str | Path) -> Scenario:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Scenario.model_validate(data)


def load_all(scenarios_dir: str | Path) -> dict[str, Scenario]:
    out: dict[str, Scenario] = {}
    for p in sorted(Path(scenarios_dir).glob("*.yaml")):
        sc = load_scenario(p)
        out[sc.id] = sc
    return out
