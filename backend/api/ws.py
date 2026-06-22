"""WebSocket 게이트웨이: /ws/flow.

EventBus 를 구독하여 FlowEvent 를 실시간 push 한다. 연결 시 backfill(최근 이벤트)부터.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/flow")
async def ws_flow(websocket: WebSocket):
    await websocket.accept()
    app = websocket.app.state.app
    backfill = int(websocket.query_params.get("backfill", "100"))
    try:
        async for ev in app.bus.subscribe(backfill=backfill):
            await websocket.send_json(ev.model_dump())
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001  (클라이언트 종료 등)
        return
