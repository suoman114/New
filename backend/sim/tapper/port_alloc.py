"""세션별 RTP 포트 할당/회수 (VCMM 수신 포트 범위 10001~11000, config).

설계서 2.8 / observed-from-logs.md §7.
"""

from __future__ import annotations

import threading


class RtpPortAllocator:
    def __init__(self, base: int = 10001, count: int = 1000) -> None:
        self._base = base
        self._count = count
        self._free: list[int] = list(range(base, base + count))
        self._used: set[int] = set()
        self._lock = threading.Lock()

    def allocate(self) -> int:
        with self._lock:
            if not self._free:
                raise RuntimeError("RTP 포트 고갈 (10001~11000 모두 사용중)")
            port = self._free.pop(0)
            self._used.add(port)
            return port

    def release(self, port: int) -> None:
        with self._lock:
            if port in self._used:
                self._used.discard(port)
                self._free.append(port)

    @property
    def in_use(self) -> int:
        return len(self._used)

    @property
    def capacity(self) -> int:
        return self._count
