# LTE-R 녹취서버(uVCS) 검증 자동화 시뮬레이터

IMS / McPTT 망의 **SIP + AMR-WB(RTP) 음성**을 생성하여 Tapper UDP 포워딩 방식으로
**LTE-R 녹취서버(uVCS)** 에 주입하고, 서버가 만든 **녹취 파일 / DB / RMQ 메시지**를
수집·검증하는 자동화 시뮬레이터다. 웹 대시보드에서 모든 기능을 제어하고,
**호처리 흐름(ladder)** 을 실시간으로 보여주며, **메시지 클릭 시 로그**를 드릴다운한다.

> 상세 설계/계약은 [`CLAUDE.md`](./CLAUDE.md), 스펙은 [`docs/specs/`](./docs/specs/),
> 실 서버 연동은 [`docs/specs/integration.md`](./docs/specs/integration.md) 참조.

---

## 1. 빠른 시작

### 사전 요구
- Python ≥ 3.11, Node ≥ 18

### 백엔드 (대시보드 API + 시뮬레이터 엔진)
```bash
cd backend
pip install -e ".[dev]"
pytest                                  # 전체 테스트 (117건)
uvicorn api.main:app --reload           # http://localhost:8000  (REST + /ws/flow)
```

### 프론트엔드 (대시보드 UI)
```bash
cd frontend
npm install
npm run dev                             # http://localhost:5173  (/api·/ws 프록시 → :8000)
```

### CLI 데모 (대시보드 없이 엔드투엔드 주입)
```bash
cd backend
python run_demo.py                                  # MCPTT-GROUP-FLOOR (빠른 모드)
python run_demo.py --scenario IMS-VOICE-INBOUND
python run_demo.py --scenario MCPTT-BE --realtime   # 실시간 20ms 페이싱
```
데모는 SIP+RTP 를 `config/sim.yaml` 의 VCSM/VCMM 포트로 실제 UDP 주입하고 ladder/기대값/로그를 출력한다.

---

## 2. 구조

```
자극 생성·주입                                   결과 검증
─────────────                                  ─────────
scenario(타임라인) ─ sip-engine(SIP/SDP) ─┐     rmq-monitor(floor TAKEN/IDLE)
                  ├ rtp-media(AMR-WB OA/BE)├─▶  validator(파일/DB/오디오 골든 재구성)
                  └ tapper-feed(UDP 주입) ─┘     ├ TBL_RECORD_INFO(MariaDB)
                                                 ├ 램디스크/NAS 파일
   SIP→VCSM:10000  RTP→VCMM:10001~11000          └ 부록5 timestamp-gap 묵음 채움
                       │
              [ uVCS 녹취서버 (SUT) ]  VCTP / VCSM / VCMM / VCMC / RabbitMQ / DB
                       │
       대시보드 ◀ EventBus(FlowEvent) ─ ladder + 로그 드릴다운 + 검증 리포트 + 성능
```

### 백엔드 모듈 (`backend/sim/`, `backend/api/`)
| 모듈 | 역할 |
|---|---|
| `platform/` | config(+env override)·structured logging(로그 드릴다운)·EventBus·models(FlowEvent)·DB client(TBL_RECORD_INFO read-only) |
| `sip/` | SIP 메시지/SDP 빌더·파서, CallerUA 상태머신 (IMS·MCPTT) |
| `rtp/` | RTP 헤더 + AMR-WB **OA/BE** 패킷화·파싱, 묵음/손실/지터, `h264.py`(de-pkt/DON/Annex B) |
| `tapper/` | Tapper UDP 송신(SIP→VCSM/RTP→VCMM), 포트 할당, 페이싱 |
| `scenario/` | YAML 로더 + 기대값 산출 + MCPTT(floor)/IMS(caller·callee) 타임라인 엔진 |
| `validator/` | 골든 재구성(부록4/5)·묵음표(부록7)·파일/DB/오디오/H.264 검증 facade |
| `rmq/` | RMQ(AMQP/JSON) shadow monitor·디코드·floor 시퀀스/txn 검증 (graceful degrade) |
| `perf/` | ramp-up 부하 + 메트릭(p50/p95/p99), **멀티프로세스 분산(~2000+)** |
| `api/` | FastAPI REST + `/ws/flow` WebSocket, run/stop/validate/perf 오케스트레이션 |

### 프론트엔드 (`frontend/src/`)
ladder diagram · 로그 드릴다운 · 시나리오 제어 · 세션 테이블(검증) · 검증 리포트 · 성능 패널 · 통합 헬스칩

---

## 3. 시나리오 (`config/scenarios/`)
| ID | 설명 |
|---|---|
| `MCPTT-GROUP-FLOOR` | **(최우선)** MCPTT 그룹콜, floor TAKEN/IDLE talk-spurt 녹취, 다발언자 |
| `IMS-VOICE-INBOUND` | IMS 음성 인바운드, **caller/callee 분리 파일**(2레그) |
| `MCPTT-BE` | AMR-WB **BE(Bandwidth-Efficient) 모드** |
| `PACKET-LOSS` | RTP 손실/지터 → timestamp-gap 묵음 채움 검증 |
| `SILENCE-DTX` | 묵음(DTX) 구간 → 묵음 패킷 변환 검증 |
| `IMS-VIDEO` | H.264 영상 녹취 (검증 라이브러리 기반) |

대시보드/CLI 에서 선택 실행. 새 시나리오는 YAML 한 파일로 추가된다.

---

## 4. 실 서버(uVCS) 통합시험
오프라인(인메모리/tmp)으로 전부 검증되며, 실 서버 연동은 **환경변수**로 주입한다(미연결 시 graceful degrade).

```bash
export UVCS_DB_HOST=10.x.x.x UVCS_DB_USER=readonly UVCS_DB_PASSWORD=*** UVCS_DB_NAME=uvcs
export UVCS_RMQ_HOST=10.x.x.x UVCS_RMQ_USER=*** UVCS_RMQ_PASSWORD=***
export UVCS_REC_RAMDISK=/home/vcs/ramdisk UVCS_REC_NAS=/home/vcs/nas
uvicorn api.main:app
```
- `GET /api/integration/health` — DB/RMQ/FS 연동 상태 (대시보드 상단 칩)
- 시나리오 실행 후 `POST /api/validate?session_id=...` 또는 세션 테이블의 **검증** 버튼
  → 파일/DB(TBL_RECORD_INFO)/오디오 골든/RMQ floor 를 한 번에 대조 → 검증 리포트

자세한 절차/환경변수표: [`docs/specs/integration.md`](./docs/specs/integration.md).

---

## 5. 성능시험
- 대시보드 **성능 패널**: 총 세션수 + 워커수 입력 → `⚡ 부하 시험`
- `workers=1`: 단일 프로세스(asyncio), 50세션 초과 시 이벤트 발행 억제(샘플링)
- `workers>1`: **멀티프로세스 분산** — 500세션/8워커 ≈ 0.6s, ~800 sess/s (단일 노드 ~2000+ 확장)
- API: `POST /api/perf/run {scenario_id,total,cps,workers}`, `GET /api/perf`

---

## 6. 주요 설계 메모 (as-built 우선)
실 운영 로그 분석 결과([`docs/specs/observed-from-logs.md`](./docs/specs/observed-from-logs.md))가 설계서 v1.0.0 보다 우선한다.
- 프로세스 **VCMC** 추가(MCPTT 시그널링/DB), 메시지 `recording_change`(floor)/`recording_update`
- transactionId=UUID, 성공 reasonCode=**2000**(3001=Callee SDP null / 4001=Session not exist)
- DB 단일 테이블 **`TBL_RECORD_INFO`**(MariaDB), 파일 램디스크 `.awb.ing` → NAS
- 파일명 `M_{callid}_{mdn}_{groupid}_{ts}_{fileindex}.awb`(MCPTT) / `I_{callid}_{from}_{to}_{ts}.awb`(IMS)

---

## 7. 개발
```bash
cd backend && ruff check sim api tests && pytest    # lint + test
cd frontend && npm run build                        # tsc + vite
```
- 개발 브랜치: `claude/eager-carson-49av4h`. 스펙 변경은 `docs/specs` + `CLAUDE.md` 동시 갱신.
- 진행 상태 보드: `CLAUDE.md §10`.

### 남은 확장 지점 (실 미디어 소스/네이티브 라이브러리 필요)
- H.264 **영상 트래픽 송출** 타임라인 엔진 (검증 라이브러리는 완성)
- opencore-amr/ffmpeg **실 음원 인코딩** (`encode_source` 인터페이스 개방)
- `pcap_mirror` 주입 모드(실 VCTP 까지 시험)
