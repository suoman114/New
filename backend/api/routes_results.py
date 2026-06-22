"""세션 테이블 / 검증 리포트 / 성능 메트릭 조회 API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["results"])


@router.get("/sessions")
async def list_sessions(request: Request):
    app = request.app.state.app
    return [s.model_dump() for s in app.sessions.values()]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    app = request.app.state.app
    info = app.sessions.get(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail="session not found")
    run = app.run_results.get(session_id)
    return {
        "session": info.model_dump(),
        "run": _run_summary(run) if run else None,
    }


@router.get("/results")
async def list_results(request: Request):
    app = request.app.state.app
    return {sid: r.model_dump() for sid, r in app.results.items()}


@router.get("/results/{session_id}")
async def get_result(session_id: str, request: Request):
    app = request.app.state.app
    res = app.results.get(session_id)
    if res is None:
        raise HTTPException(status_code=404, detail="no validation result")
    return res.model_dump()


@router.get("/metrics")
async def metrics(request: Request):
    return request.app.state.app.metrics()


def _run_summary(run) -> dict:
    return {
        "session_id": run.session_id,
        "call_id": run.call_id,
        "scenario_id": run.scenario_id,
        "service_type": run.service_type,
        "sip_count": run.sip_count,
        "spurts": [
            {"index": s.index, "talker_mdn": s.talker_mdn, "rtp_port": s.rtp_port,
             "ssrc": s.ssrc, "sent_packets": s.sent_packets, "dropped": s.dropped,
             "play_time_ms": s.stats.play_time_ms}
            for s in run.spurts
        ],
        "expectations": run.expectations.model_dump(),
    }
