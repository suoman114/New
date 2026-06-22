# LTE-R 녹취서버(uVCS) 검증 자동화 시뮬레이터

IMS / McPTT 망의 **SIP + AMR-WB(RTP) 음성**을 생성하여 Tapper UDP 포워딩 방식으로
**LTE-R 녹취서버(uVCS)** 에 주입하고, 서버가 만든 **녹취 파일 / DB / RMQ 메시지**를
수집·검증하는 자동화 시뮬레이터다. 웹 대시보드에서 모든 기능을 제어하고,
**호처리 흐름(ladder)** 을 실시간으로 보여주며, **메시지 클릭 시 로그**를 드릴다운한다.

## 개발 방식 — 오케스트레이션
이 저장소는 **`CLAUDE.md`(마스터 컨텍스트) + `.claude/agents/`(서브 에이전트)** 구조로 개발한다.
Claude Code 가 작업을 받으면 `CLAUDE.md` 의 에이전트 카탈로그에 따라 담당 에이전트에 위임한다.

- 전체 설계/계약: [`CLAUDE.md`](./CLAUDE.md)
- 상세 스펙: [`docs/specs/`](./docs/specs/)
  - `rmq-protocol.md` — VCSM↔VCMM RMQ(JSON) 메시지
  - `db-schema.md` — call_session / record_file
  - `sip-sdp.md` — SIP/SDP 규격, INVITE 샘플
  - `amr-wb-rtp.md` — RTP·AMR-WB payload→file 변환(부록 5 의사코드)
  - `silence-packets.md` — 묵음 패킷 byte 표(부록 7)
  - `file-storage.md` — 파일명/디렉토리 규칙
  - `h264.md` — H.264 (2차)
- 에이전트 정의: [`.claude/agents/`](./.claude/agents/)
- 설정: [`config/sim.yaml`](./config/sim.yaml), 시나리오: [`config/scenarios/`](./config/scenarios/)

## 기술 스택
- Backend: **Python** (asyncio, FastAPI, WebSocket, aio-pika, SQLAlchemy)
- Frontend: **React + TypeScript** (Vite, WebSocket)

## 시험 대상 / 주입 방식
- 시험 대상: **실 서버(uVCS)** 만 (Mock 미포함).
- 주입: **Tapper UDP 포워딩 모방** — SIP→`VCTP:10000`, RTP→`VCTP:10001~11000`.

## 빠른 시작 (개발 진행 후 동기화)
```bash
# backend
cd backend && pip install -e . && pytest
uvicorn api.main:app --reload

# frontend
cd frontend && npm install && npm run dev
```

> 현재는 설계/오케스트레이션 골격 단계다. 각 에이전트가 `backend/`·`frontend/` 구현을 채운다.
> 진행 상태는 `CLAUDE.md §10` 보드에서 관리한다.
