"""dashboard-backend: FastAPI REST + WebSocket, 이벤트 중계, 결과 API."""

from .state import AppState
from .main import create_app, app

__all__ = ["AppState", "create_app", "app"]
