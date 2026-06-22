"""구조화 로깅 + event_id 태깅 로그 저장소.

CLAUDE.md §3.1 로그 드릴다운 계약:
  프론트가 ladder 노드(FlowEvent) 클릭 → GET /api/events/{event_id}/logs
  → 해당 이벤트의 raw(hex/text) + 파싱 결과 + 관련 로그 라인을 반환.

`LogStore` 는 event_id → 로그 라인 리스트를 보관한다. 각 엔진은 `log_for(event, ...)` 로
이벤트에 귀속되는 로그를 남기고, dashboard-backend 가 `LogStore.get(event_id)` 로 조회한다.
"""

from __future__ import annotations

import logging
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import FlowEvent

_LEVELS = {"info": logging.INFO, "warn": logging.WARNING, "error": logging.ERROR,
           "debug": logging.DEBUG}


@dataclass
class LogLine:
    ts: float                      # epoch ms
    level: str                     # info/warn/error/debug
    message: str
    session_id: str = ""
    call_id: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


class LogStore:
    """event_id 로 태깅된 로그 라인 저장소(메모리, LRU 상한)."""

    def __init__(self, max_events: int = 20000, max_lines_per_event: int = 200) -> None:
        self._max_events = max_events
        self._max_lines = max_lines_per_event
        self._store: "OrderedDict[str, list[LogLine]]" = OrderedDict()

    def append(self, event_id: str, line: LogLine) -> None:
        lines = self._store.get(event_id)
        if lines is None:
            lines = []
            self._store[event_id] = lines
            self._store.move_to_end(event_id)
            while len(self._store) > self._max_events:
                self._store.popitem(last=False)
        if len(lines) < self._max_lines:
            lines.append(line)

    def get(self, event_id: str) -> list[LogLine]:
        return list(self._store.get(event_id, []))

    def clear(self) -> None:
        self._store.clear()


# 프로세스 전역 기본 저장소(테스트에서는 별도 인스턴스 사용 가능)
default_store = LogStore()


def log_for(
    event: FlowEvent,
    message: str,
    *,
    level: str = "info",
    store: LogStore | None = None,
    logger: logging.Logger | None = None,
    **extra: Any,
) -> LogLine:
    """FlowEvent 에 귀속되는 로그 라인을 저장하고 표준 로거에도 출력한다."""
    store = store or default_store
    line = LogLine(
        ts=round(time.time() * 1000.0, 3),
        level=level,
        message=message,
        session_id=event.session_id,
        call_id=event.call_id,
        extra=extra,
    )
    store.append(event.log_ref or event.event_id, line)
    if logger is not None:
        logger.log(_LEVELS.get(level, logging.INFO),
                   "[%s][%s][%s] %s",
                   event.event_id, event.session_id, event.call_id or "-", message)
    return line


class _ContextFormatter(logging.Formatter):
    """실 운영 로그와 유사한 포맷: [ts][LEVEL][thread] msg - (file:line)."""

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        ms = int(record.msecs)
        return (f"[{ts}.{ms:03d}][{record.levelname:<5}][{record.threadName}] "
                f"{record.getMessage()} - ({record.filename}:{record.lineno})")


def configure_logging(level: str = "info") -> None:
    """루트 로거를 구조화 포맷으로 설정(중복 핸들러 방지)."""
    root = logging.getLogger()
    root.setLevel(_LEVELS.get(level, logging.INFO))
    if any(getattr(h, "_uvcs", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ContextFormatter())
    handler._uvcs = True  # type: ignore[attr-defined]
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
