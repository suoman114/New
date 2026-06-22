"""이벤트 조회 + 로그 드릴다운 API.

핵심: GET /api/events/{event_id}/logs — ladder 메시지 클릭 시
raw + 파싱 결과(payload) + 관련 로그 라인을 반환 (CLAUDE.md §3.1 로그 드릴다운 계약).
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def list_events(request: Request, session_id: str | None = None,
                      call_id: str | None = None, channel: str | None = None,
                      limit: int = 200):
    app = request.app.state.app
    events = app.bus.recent(limit=limit, session_id=session_id, call_id=call_id,
                            channel=channel)
    return [e.model_dump() for e in events]


@router.get("/events/{event_id}")
async def get_event(event_id: str, request: Request):
    app = request.app.state.app
    ev = app.bus.get(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="event not found")
    return ev.model_dump()


@router.get("/events/{event_id}/logs")
async def get_event_logs(event_id: str, request: Request):
    """로그 드릴다운: 이벤트 원문(payload) + 태깅된 로그 라인."""
    app = request.app.state.app
    ev = app.bus.get(event_id)
    lines = app.logs.get(event_id)
    if ev is None and not lines:
        raise HTTPException(status_code=404, detail="event/logs not found")
    return {
        "event_id": event_id,
        "event": ev.model_dump() if ev else None,
        "payload": ev.payload if ev else {},
        "raw": (ev.payload.get("raw") if ev else None),
        "logs": [asdict(ln) for ln in lines],
    }
