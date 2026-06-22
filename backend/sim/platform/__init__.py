"""platform: 공통 기반(config, logging, EventBus, models, DB client).

다른 모든 에이전트/엔진이 의존하는 토대다. 권위 스펙: CLAUDE.md §3.1, §8,
docs/specs/observed-from-logs.md (DB = TBL_RECORD_INFO).
"""

from .models import (
    Channel,
    Direction,
    Severity,
    FlowEvent,
    ValidationItem,
    ValidationResult,
    RecordInfo,
    SessionInfo,
)
from .eventbus import EventBus
from .config import SimConfig, load_config, find_config_path

__all__ = [
    "Channel",
    "Direction",
    "Severity",
    "FlowEvent",
    "ValidationItem",
    "ValidationResult",
    "RecordInfo",
    "SessionInfo",
    "EventBus",
    "SimConfig",
    "load_config",
    "find_config_path",
]
