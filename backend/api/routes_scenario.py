"""시나리오 제어 API: 목록/실행/중지."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["scenario"])


class RunRequest(BaseModel):
    scenario_id: str
    session_count: int = 1
    realtime: bool = False
    wait: bool = False          # true 면 실행 완료까지 대기 후 응답(테스트/동기 실행)


class RunResponse(BaseModel):
    session_ids: list[str]


@router.get("/scenarios")
async def list_scenarios(request: Request):
    app = request.app.state.app
    return [
        {"id": s.id, "title": s.title, "service_type": s.service_type,
         "floor_count": len(s.floor_sequence)}
        for s in app.scenarios.values()
    ]


@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest, request: Request):
    app = request.app.state.app
    try:
        ids = await app.run_scenario(req.scenario_id, session_count=req.session_count,
                                     realtime=req.realtime, wait=req.wait)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown scenario {req.scenario_id}")
    return RunResponse(session_ids=ids)


@router.post("/stop")
async def stop(session_id: str, request: Request):
    app = request.app.state.app
    ok = await app.stop_session(session_id)
    return {"stopped": ok, "session_id": session_id}
