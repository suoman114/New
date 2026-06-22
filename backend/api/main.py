"""dashboard-backend: FastAPI REST + WebSocket 게이트웨이.

실행:
    cd backend && uvicorn api.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sim.platform.logging import configure_logging

from .routes_events import router as events_router
from .routes_results import router as results_router
from .routes_scenario import router as scenario_router
from .state import AppState
from .ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    state = AppState()
    app.state.app = state
    await state.start_rmq()          # RMQ shadow monitor (graceful degrade)
    yield
    await state.rmq.close()


def create_app(state: AppState | None = None) -> FastAPI:
    app = FastAPI(title="uVCS 검증 시뮬레이터 대시보드", version="0.1.0", lifespan=lifespan)
    cors_origins = ["*"]
    if state is not None:
        # 테스트/주입용: lifespan 대신 외부 상태 사용
        app.state.app = state
        cors_origins = state.config.api.cors_origins

        @asynccontextmanager
        async def _noop_lifespan(_app: FastAPI):
            yield
        app.router.lifespan_context = _noop_lifespan

    app.add_middleware(
        CORSMiddleware, allow_origins=cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(scenario_router)
    app.include_router(events_router)
    app.include_router(results_router)
    app.include_router(ws_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
