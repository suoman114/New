# CLAUDE.md — LTE-R 녹취서버 검증 자동화 시뮬레이터 (uVCS Verification Simulator)

> 이 문서는 **오케스트레이션 마스터 컨텍스트**다. Claude Code 가 이 저장소에서 작업할 때
> 항상 이 파일을 읽고, 아래 정의된 **서브 에이전트**(`.claude/agents/*.md`)에게 작업을 위임한다.
> 모든 설계 근거는 본 문서 및 `docs/specs/*.md` 에 embed 되어 있으며, 각 에이전트는
> 자신의 담당 영역 스펙만으로 독립 개발이 가능하도록 작성되었다.
>
> ⚠️ **스펙 우선순위**: 실 운영 로그 분석 결과인 **`docs/specs/observed-from-logs.md` (as-built)** 가
> 설계서 v1.0.0 기반 스펙보다 **우선**한다. 실제 시스템은 **MCPTT 중심**으로 진화했고, 프로세스(**VCMC** 추가),
> 메시지(`recording_change`/`recording_update`, UUID transactionId, reasonCode `2000`=성공),
> DB 테이블(`TBL_RECORD_INFO`), 파일명/경로(램디스크 `.ing`)가 설계서와 다르다. **반드시 as-built 우선.**

---

## 0. 한눈에 보기 (TL;DR)

- **무엇을 만드나**: 실제 **LTE-R 녹취서버(uVCS)** 를 시험하는 **검증 자동화 시뮬레이터**.
- **핵심 동작**: IMS / McPTT 망의 **SIP 시그널링 + AMR-WB(RTP) 음성**을 생성하여
  Tapper 를 모방한 **UDP 포워딩**으로 녹취서버(VCTP)에 주입하고, 녹취서버가 만든
  **녹취 파일 / DB / RMQ 메시지**를 수집·검증한다.
- **대시보드**: 모든 기능을 단일 웹 대시보드에서 제어하고, **호처리 흐름(ladder diagram)** 을
  실시간 시각화하며, **메시지를 클릭하면 해당 로그**를 드릴다운한다.
- **성능시험**: 1차는 **기능검증 위주**, 단 구조는 동시 세션 확장(목표 ~2000 세션)이 가능하도록 설계.
- **기술 스택**: Backend = **Python**(asyncio, FastAPI, WebSocket), Frontend = **React + TypeScript**.
- **시험 대상**: **실 서버만** 시험 (Mock 미포함). 시뮬레이터는 Tapper/UA 역할 + 검증기 역할.

---

## 1. 시험 대상 시스템 (SUT) — uVCS 녹취서버

> 시뮬레이터는 아래 시스템을 **블랙박스/그레이박스**로 시험한다. 우리가 구현하는 것이 아니라
> **외부에서 자극을 주고 결과를 검증**하는 대상이다.

```
        [ 시뮬레이터(우리) = Tapper + UA 모방 ]
                       │  UDP
        ┌──────────────┼───────────────────────────┐
        │              ▼                           ▼
        │   SIP → 127.0.0.1:10000           RTP → 127.0.0.1:10001~11000
        │              │                           │
  ┌─────┴──────────────┴───────────────────────────┴────────────────────┐
  │                         uVCS 녹취서버 (SUT)                          │
  │                                                                      │
  │   ┌────────┐      SIP(UDP)     ┌────────┐    RMQ(AMQP/JSON)  ┌──────┐ │
  │   │  VCTP  │ ───────────────▶  │  VCSM  │ ◀───────────────▶ │ VCMM │ │
  │   │(Tapper │                   │(Signal │                   │(Media│ │
  │   │ 수신/  │ ──── RTP(UDP) ───────────────────────────────▶ │ 수집/│ │
  │   │ 분배)  │                   │ 세션/  │                   │ 저장)│ │
  │   └────────┘                   │ LB/통계│                   └──┬───┘ │
  │                                └───┬────┘                      │     │
  │                                    │ ODBC                      │ 파일 │
  │                                    ▼                           ▼     │
  │                                 [  DB  ] ◀───────────────── [ ~/REC ]│
  │                              call_session                            │
  │                              record_file                             │
  └──────────────────────────────────────────────────────────────────────┘
```

### 1.1 프로세스 역할 (as-built, `observed-from-logs.md` 우선)
| 프로세스 | 역할 |
|---|---|
| **VCTP** | NIC **libpcap 미러 캡처** + IP fragment 재조립 → **SIP 는 VCSM**, **RTP 는 VCMM** 으로 전달 (SIP 5060=IMS, 5080=MCPTT) |
| **VCSM** | (IMS 브레인) SIP 파싱 → Call-ID 세션맵, 다중 VCMM 로드밸런싱, RMQ `recording_start/update/stop` 전달, `TBL_RECORD_INFO` 기록, 통계, 이중화 |
| **VCMM** (`VCMM_0`) | RTP 수신 → **AMR-WB `.awb` 파일 저장**(램디스크). MCPTT **floor 처리**, `heartbeat_indi` 송신, floor 변화를 `recording_change`로 VCMC 통지 |
| **VCMC** | (MCPTT 브레인, **설계서엔 없던 실제 프로세스**) MCPTT 녹취 클라이언트 SIP REGISTER(OWN/HEALTH), `recording_change` 처리, `TBL_RECORD_INFO` INSERT/UPDATE, 완료 처리 |
| **RabbitMQ** | VCSM/VCMC ↔ VCMM 간 JSON 제어 메시지 미들웨어(AMQP) |

- **IMS 경로**: VCTP→VCSM(SIP), VCSM⇄VCMM(`recording_start/update/stop`), VCSM→DB.
- **MCPTT 경로**: VCMC(REGISTER 가입), VCMM⇄VCMC(`recording_change` floor TAKEN/IDLE), VCMC→DB.
  MCPTT 는 **floor(talk spurt) 단위로 파일 1개**씩 생성(FILE_INDEX 증가). ← **실 트래픽 대다수**.

### 1.2 연동 포트 (설계서 2.7 / 2.8)
- **VCTP → VCSM (SIP)**: IP `127.0.0.1`, Port `10000` (UDP, Config)
- **VCTP → VCMM (RTP)**: IP `127.0.0.1`, Port `10001 ~ 11000` (UDP, Config)
- **시뮬레이터는 Tapper 역할**로 위 포트에 UDP 송신한다. (대상 host/port 는 모두 config 화)

---

## 2. 시뮬레이터 목표 & 검증 범위

### 2.1 기능 목표
1. **SIP 시그널 생성**: IMS / McPTT 녹취 호 시작·종료 (INVITE→ … →BYE) 시나리오를 Tapper 입장에서 미러링하여 주입.
2. **RTP/AMR-WB 미디어 생성**: 알려진 원본 음원을 AMR-WB(및 AMR-NB) 로 패킷화하여 송출. 묵음/패킷손실/지터 시뮬레이션 옵션.
3. **트래픽 주입**: Tapper UDP 포워딩 모방 (SIP→10000, RTP→10001~11000).
4. **결과 검증(핵심)**:
   - 녹취 **파일 생성 여부 / 파일명 규칙 / 디렉토리 구조** (설계서 2.6)
   - **AMR-WB 파일 무결성**: 우리가 송출한 음원과 서버 저장 파일을 디코딩/비교 (부록 5 의사코드 역검증)
   - **DB 검증**: `call_session`, `record_file` 레코드의 각 컬럼 값 정합성 (DB 규격서)
   - **RMQ 메시지 검증**: `login/heartbeat/recording_start/recording_stop` 의 header/body, error code (RMQ 규격서)
5. **대시보드**: 시나리오 제어, 실시간 호처리 ladder, 메시지 클릭→로그 드릴다운, 검증 결과 리포트.
6. **성능시험(확장)**: 동시 세션 ramp-up, CPS, 메모리/지연 메트릭. 1차는 구조만, 목표 ~2000 세션.

### 2.2 비범위 (Out of Scope, 1차)
- uVCS 내부 로직 구현 (실 서버만 시험, Mock 미포함).
- H.264 영상 녹취 **생성**은 2차 (단, 스펙은 `docs/specs/h264.md` 에 보존하고 검증기 인터페이스는 확장 가능하게).

---

## 3. 시뮬레이터 아키텍처

```
┌──────────────────────────── Frontend (React + TS) ────────────────────────────┐
│  Scenario Control │ Call-Flow Ladder │ Message→Log Drilldown │ Validation │Perf │
└───────────────────────────────── WebSocket / REST ────────────────────────────┘
                                       │
┌──────────────────────────── Backend (Python / asyncio) ───────────────────────┐
│  api/        FastAPI REST + WebSocket gateway  (dashboard-backend)              │
│  ─────────────────────────────────────────────────────────────────────────    │
│  sim/scenario/    시나리오 오케스트레이션 (시간선/상태머신)  (scenario)         │
│  sim/sip/         SIP UA & 메시지 생성/파싱, SDP            (sip-engine)        │
│  sim/rtp/         RTP + AMR-WB 패킷화/송출, 손실/지터       (rtp-media)         │
│  sim/tapper/      Tapper UDP 포워딩 (SIP/RTP 송신)          (tapper-feed)       │
│  sim/validator/   기준 녹취 + 파일/DB/오디오 비교 검증      (validator)         │
│  sim/rmq/         RMQ 메시지 패시브 모니터/검증             (rmq-monitor)       │
│  sim/perf/        부하 생성/메트릭 수집                     (perf)              │
│  sim/platform/    공통: config, logging, EventBus, models, DB client (platform) │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 공통 이벤트 모델 (모든 에이전트가 준수 — `sim/platform/models.py`)
모든 엔진은 **EventBus** 로 구조화 이벤트를 발행하고, dashboard-backend 가 이를 WebSocket 으로 중계한다.
호처리 흐름과 로그 드릴다운은 **이 이벤트 모델 위에서만** 구현된다.

```python
# 상관키: 모든 이벤트는 session_id(시뮬레이터) 와 call_id(SIP Call-ID) 로 상관된다.
class FlowEvent:
    event_id: str            # 고유 ID (로그 드릴다운 키)
    ts: float                # epoch (ms 정밀도)
    session_id: str          # 시뮬레이터 테스트 세션 ID
    call_id: str | None      # SIP Call-ID (호 상관)
    channel: str             # "SIP" | "RTP" | "RMQ" | "DB" | "VALIDATION" | "SYS"
    direction: str           # "SIM->SUT" | "SUT->SIM" | "SUT-INTERNAL" | "SIM-INTERNAL"
    peer: str                # 예: "VCTP", "VCSM", "VCMM_0", "UA-Caller"
    label: str               # ladder 노드 라벨 (예: "INVITE", "recording_start_req")
    summary: str             # 한 줄 요약
    payload: dict            # 구조화 본문 (SIP 헤더/SDP, RMQ header/body, RTP stat 등)
    log_ref: str             # 상세 로그 위치 (event_id 로 조회 가능)
    severity: str            # "info" | "warn" | "error"
```

- **로그 드릴다운 계약**: 프론트가 ladder 노드(=FlowEvent) 클릭 → `GET /api/events/{event_id}/logs`
  → 해당 이벤트의 **원문(raw bytes/hex), 파싱 결과, 관련 로그 라인**을 반환.
- **로그 저장**: `sim/platform/logging.py` 가 `event_id` 를 모든 로그 라인에 태깅(structured log)한다.

### 3.2 모듈 간 인터페이스 (계약)
- `scenario` → `sip-engine`/`rtp-media`: 시나리오가 호별 타임라인을 만들고 각 엔진의 송출 API 호출.
- `sip-engine`/`rtp-media` → `tapper-feed`: 직렬화된 바이트를 Tapper 송신기로 전달(SIP/RTP 분리).
- 모든 엔진 → `platform.EventBus.publish(FlowEvent)`.
- `validator`/`rmq-monitor` → SUT 의 산출물(파일/DB/RMQ)을 읽어 `FlowEvent(channel=VALIDATION)` 발행.
- `dashboard-backend` → `EventBus` 구독 + REST(시나리오 제어, 결과 조회) + WebSocket(실시간 push).

---

## 4. 오케스트레이션 방식 (Claude Code 사용법)

이 저장소는 **오케스트레이터(이 CLAUDE.md) + 서브 에이전트** 구조로 개발한다.

### 4.1 에이전트 카탈로그 (`.claude/agents/`)
| 에이전트 | 파일 | 담당 | 주 스펙 |
|---|---|---|---|
| **platform** | `platform.md` | config, logging, EventBus, 공통 models, DB client | §3.1, `observed-from-logs.md`(TBL_RECORD_INFO) |
| **sip-engine** | `sip-engine.md` | SIP UA/메시지/SDP, IMS·McPTT call flow | `sip-sdp.md` + `observed-from-logs.md §6` |
| **rtp-media** | `rtp-media.md` | RTP + AMR-WB 패킷화/송출, 묵음/손실/지터 | `amr-wb-rtp.md` |
| **tapper-feed** | `tapper-feed.md` | Tapper UDP 포워딩(SIP→10000, RTP→10001~11000) | §1.2, `observed-from-logs.md §7` |
| **scenario** | `scenario.md` | 시나리오 상태머신/타임라인 오케스트레이션 | §6 + `observed-from-logs.md §8`(MCPTT floor 우선) |
| **validator** | `validator.md` | 기준 녹취 + 파일/DB/오디오 비교 검증 | `amr-wb-rtp.md`, `observed-from-logs.md`(DB/파일/통계), `file-storage.md` |
| **rmq-monitor** | `rmq-monitor.md` | RMQ 메시지 모니터/검증 | `observed-from-logs.md §2`(우선) + `rmq-protocol.md` |
| **dashboard-backend** | `dashboard-backend.md` | FastAPI REST + WebSocket, 이벤트 중계, 결과 API | §3.1 |
| **dashboard-frontend** | `dashboard-frontend.md` | React/TS UI: ladder, 로그 드릴다운, 제어, 결과 | §3.1, §5 |
| **perf** | `perf.md` | 부하 생성/메트릭, 동시 세션 확장 | §7 |

### 4.2 오케스트레이터(=메인 세션) 규칙
1. 작업 요청을 받으면 **어느 에이전트 담당인지 매핑** 후 해당 에이전트에 위임한다.
2. 여러 에이전트가 필요한 작업은 **인터페이스(§3.2) 우선 합의 → 병렬 위임** 한다.
3. 에이전트 간 **공유 계약(FlowEvent, 포트, 메시지 스펙)** 변경은 반드시 이 CLAUDE.md / `docs/specs` 를 먼저 갱신한 뒤 진행한다.
4. 새 기능은 **TDD 우선**: `backend/tests/` 에 계약 테스트 먼저.
5. 모든 구현은 §8 규약(디렉토리/네이밍/포트/config)을 따른다.

---

## 5. 대시보드 요구사항 (필수 기능)
1. **시나리오 제어판**: 시나리오 선택(IMS/McPTT, in/outbound, conference, codec, 묵음/손실), 세션 수, 시작/중지.
2. **실시간 호처리 Ladder Diagram**: X축 = 노드(UA / VCTP / VCSM / VCMM / DB), 세로 = 시간.
   - SIP / RMQ / RTP(요약) / DB / VALIDATION 이벤트를 화살표로 표시.
   - 색상: info/warn/error, 채널별 구분.
3. **메시지 클릭 → 로그 드릴다운**: ladder 의 메시지(노드) 클릭 시 우측 패널에
   **raw(hex/text) + 파싱 결과 + 관련 로그 라인** 표시. (`GET /api/events/{event_id}/logs`)
4. **세션 테이블**: 진행 중/완료 세션, call_id, 상태, 검증 결과 요약.
5. **검증 리포트**: 파일/DB/오디오/RMQ 항목별 PASS/FAIL, diff 상세.
6. **성능 패널**: 동시 세션, CPS, 지연 분포, 리소스 메트릭 (확장 지점).

---

## 6. 테스트 시나리오 카탈로그 (scenario 에이전트)
> 각 시나리오는 `config/scenarios/*.yaml` 로 선언되고, scenario 엔진이 타임라인으로 전개한다.
> **우선순위(실 환경 반영, `observed-from-logs.md §8`)**: 실 트래픽은 MCPTT 중심이므로
> **MCPTT 그룹콜 + floor(TAKEN/IDLE) talk-spurt 녹취**를 최우선으로 구현한다.

| ID | 설명 | 검증 포인트 |
|---|---|---|
| `MCPTT-GROUP-FLOOR` | **(최우선)** MCPTT 그룹콜, floor TAKEN→RECORDING→IDLE, 다발언자 | talk-spurt별 파일 `M_..._{FILE_INDEX}.awb`, `recording_change`, TBL_RECORD_INFO, 통계(seq/ssrc/totalPackets) |
| `MCPTT-REINVITE` | recording_update(ReINVITE SDP 변경, file_index 증가) | update_req/res, file_index |
| `IMS-VOICE-INBOUND` | IMS 음성 인바운드(`outbound=0`) AMR-WB, **caller/callee 분리 파일** | 파일 `I_..._.awb` 2개, TBL_RECORD_INFO, recording_start/stop |
| `IMS-VOICE-OUTBOUND` | IMS 음성 아웃바운드(`outbound=1`) | 방향/번호 정합성 |
| `MCPTT-VOICE` | McPTT 음성, `service_type=MCPTT`, res 에 SDP 필수 | 파일 `M_..._.awb`, MCPTT 분기 |
| `IMS-AMRNB` | AMR-NB(`.amr`) 코덱 | 코덱 분기, 확장자 |
| `SILENCE-DTX` | 묵음/SID 구간 포함 | 부록 7 묵음 패킷 변환 검증 |
| `PACKET-LOSS` | seq 결손/지터 | timestamp 기반 묵음 채움(부록 5) |
| `CONFERENCE` | `conference_id` 포함 회의 통화 | conference 분기 |
| `NO-SDP-ERROR` | SDP 없는 INVITE | `recording_start` error 전송 검증 |
| `STOP-NORMAL` | 정상 BYE 종료 | recording_stop, END_TIME/DURATION |
| `LOAD-RAMP` | 동시 세션 ramp (perf) | 처리율/누락률 |

---

## 7. 성능시험 설계 (perf 에이전트, 확장)
- 1차: **기능검증 위주**. 단 아래 확장 지점을 비워둔다.
- 세션 생성기는 **프로세스/코루틴 풀** 기반. 단일 노드 목표 ~2000 동시 세션(설계서 heartbeat `session_total=2000` 참조).
- 메트릭: 세션 setup latency, RTP 송출 jitter, 파일 검증 throughput, 실패율.
- 결과는 `FlowEvent(channel=SYS)` + 별도 메트릭 시계열로 대시보드 성능 패널에 표시.

---

## 8. 개발 규약 (모든 에이전트 공통)

### 8.1 디렉토리 구조
```
/
├── CLAUDE.md                      # (이 파일) 오케스트레이션 마스터
├── README.md
├── .claude/agents/*.md            # 서브 에이전트 정의
├── docs/specs/*.md                # 상세 설계 스펙 (embed)
├── config/
│   ├── sim.yaml                   # 전역 설정(포트/host/경로)
│   └── scenarios/*.yaml           # 시나리오 정의
├── backend/
│   ├── pyproject.toml
│   ├── sim/
│   │   ├── platform/              # config, logging, eventbus, models, db
│   │   ├── sip/                   # sip-engine
│   │   ├── rtp/                   # rtp-media
│   │   ├── tapper/                # tapper-feed
│   │   ├── scenario/              # scenario
│   │   ├── validator/             # validator
│   │   ├── rmq/                   # rmq-monitor
│   │   └── perf/                  # perf
│   ├── api/                       # dashboard-backend (FastAPI)
│   └── tests/                     # pytest
├── frontend/                      # dashboard-frontend (React+TS, Vite)
└── audio/                         # 원본 음원(wav/pcm) 및 골든 파일
```

### 8.2 기술/도구
- Python ≥ 3.11, `asyncio`. 패키지: `fastapi`, `uvicorn`, `pydantic`, `pytest`, `pytest-asyncio`,
  `aio-pika`(RMQ), `sqlalchemy`/드라이버(DB), `numpy`(오디오 비교), `scapy`(옵션).
- AMR-WB: 가능 시 `ffmpeg`/`opencore-amr` 연동 또는 순수 파이썬 비트 패킹(부록 5 기준).
- Frontend: React + TypeScript + Vite, WebSocket, ladder 시각화(D3 또는 커스텀 SVG).
- Lint/format: `ruff` + `black`(py), `eslint` + `prettier`(ts).

### 8.3 설정 원칙
- **하드코딩 금지**: 모든 host/port/경로는 `config/sim.yaml`. 기본값은 설계서 포트(§1.2).
- 시뮬레이터는 SUT 와 **동일 host 또는 원격** 모두 지원(127.0.0.1 기본, config 로 변경).

### 8.4 빌드/실행/테스트 명령 (확정 후 README 와 동기화)
```bash
# backend
cd backend && pip install -e . && pytest
uvicorn api.main:app --reload          # 대시보드 백엔드

# frontend
cd frontend && npm install && npm run dev
```

### 8.5 Git
- 개발 브랜치: `claude/eager-carson-49av4h`. 명시 요청 없이는 PR 생성 금지.
- 커밋은 작고 의미 단위로. 스펙 변경은 `docs/specs` + CLAUDE.md 동시 갱신.

---

## 9. 핵심 설계 스펙 요약 (상세는 `docs/specs/`)

> 아래는 오케스트레이터가 빠르게 참조하는 요약이다. **권위 있는 전체 스펙은 각 `docs/specs/*.md`**.
> ⚠️ 아래 9.1~9.5 는 설계서 v1.0.0 기준이며, **실 동작은 `docs/specs/observed-from-logs.md` 가 우선**한다
> (메시지 타입/필드, reasonCode 2000, TBL_RECORD_INFO, caller/callee 분리, 파일명/램디스크 등).

### 9.1 RMQ 제어 메시지 (→ `docs/specs/rmq-protocol.md`)
- 포맷: **JSON**, `header` + `body`. Protocol = AMQP, Direction = VCSM ↔ VCMM.
- 헤더 필드: `type`(M), `callId`(O), `transactionId`(M), `msgFrom`(M), `trxType`(0=Indi,1=Req/Res), `reasonCode`, `reason`.
- 메시지: `login_req/res`, `heartbeat_req`, `recording_start_req/res`, `recording_stop_req/res`.
- 에러코드: `0`성공 / `-1`실패 / `-2`Timeout / `-3`Wrong Param / `-4`Already Exist.

### 9.2 DB 스키마 (→ `docs/specs/db-schema.md`)
- `call_session`: SIP_CALLID(PK), CALLER_MDN, CALLEE_MDN, CREATE_TIME, END_TIME, DURATION_TIME, SERVICE_TYPE(IMS/MCPTT), RECORD_TYPE(음성/영상), CALL_TYPE(개별/그룹).
- `record_file`: ID(PK,AI), SIP_CALLID, FTEL, ETEL, CALL_TYPE, RECORD_TYPE(AUDIO/VIDEO/AUDIO_VIDEO), AUDIO_EXTENSION(amr/awb), VIDEO_EXTENSION(h264), CREATE_TIME, END_TIME, DURATION_TIME, FILE_NAME, REASON_CODE, REASON_STR, FILE_STATUS(0 저장중/1 부분/2 완료/-1 실패).

### 9.3 SIP / SDP (→ `docs/specs/sip-sdp.md`)
- IMS INVITE 샘플 보존. SDP 공통: `v=0`, `c=` 로 IP, `m=` 로 port/proto/fmt, `a=rtpmap:` 로 코덱.
- 코덱: AMR-WB/16000, AMR/8000, telephone-event, H264/90000. `a=fmtp:` 의 `octet-align`, `mode-set` 해석.

### 9.4 RTP / AMR-WB (→ `docs/specs/amr-wb-rtp.md`, `file-storage.md`, `silence-packets.md`)
- RTP 헤더(RFC3550): V=2, PT=nego, SSRC 일관, seq 정렬, timestamp 증가분으로 손실/묵음 산출.
- AMR-WB payload: payload header + ToC(F/FT/Q) + speech data. BE/OA 모드. interleaving 미지원.
- 파일저장(RFC): magic `#!AMR-WB\n`, frame header + speech bits, SID/NO_DATA→묵음 패킷 변환(부록 7).
- 부록 5 의사코드: SDP 파싱→초기화, RTP→speech frame 기록 (검증기가 **역방향 재구성**으로 비교).

### 9.5 파일명/디렉토리 (설계서 2.6)
- 파일명: `{I|M}_{CALL-ID}_{MDN}_{HHMMSSsss}.{awb|amr|h264}` (I=IMS, M=MCPTT).
- 디렉토리: `~/REC/{IMS|MCPTT}/{VIDEO|VOICE|CONV}/{YYYY}/{MM}/{DD}/{HH}/`.

---

## 10. 진행 상태 보드 (오케스트레이터가 갱신)
- [x] platform: config/logging/eventbus/models/db client — 구현+테스트 17건 통과 (`backend/sim/platform/`)
- [x] sip-engine: SIP 메시지/SDP 빌더·파서, CallerUA 상태머신 (`backend/sim/sip/`)
- [x] rtp-media: AMR-WB OA 패킷화/RTP 스트림/통계, 묵음·손실·지터 (`backend/sim/rtp/`)
- [x] tapper-feed: UDP 송신기(SIP→VCSM/RTP→VCMM), 포트할당, 페이싱 (`backend/sim/tapper/`)
      — 위 3종 합계 테스트 35건 통과, ruff clean. (BE 모드/실 음원 인코딩은 2차)
- [x] scenario: YAML 로더 + 기대값 산출 + MCPTT-GROUP-FLOOR/IMS-VOICE-INBOUND 타임라인 엔진 (`backend/sim/scenario/`)
      — sip+rtp+tapper 구동 엔드투엔드(`backend/run_demo.py`). IMS는 caller/callee 분리 녹취(2레그)
- [x] validator: 묵음표(부록7)+골든 재구성(부록4/5)+오디오/파일/DB 검증 facade (`backend/sim/validator/`)
      — 53건 통과. SID/NO_DATA→묵음, 손실 timestamp-gap 채움은 v2 확장
- [x] rmq-monitor: RMQ 디코드/헤더검증/floor 시퀀스·txn 페어링·에러코드, shadow monitor graceful degrade (`backend/sim/rmq/`)
      — 63건 통과. 실 로그 메시지(heartbeat_indi/recording_change TAKEN·IDLE/3001 에러) 기준
- [x] dashboard-backend: FastAPI REST(시나리오/이벤트/세션/결과/메트릭) + /ws/flow WebSocket + 로그 드릴다운 (`backend/api/`)
      — 71건 통과. EventBus 중계, run/stop 오케스트레이션, TestClient 검증
- [x] dashboard-frontend: React+TS(Vite) ladder/로그드릴다운/제어/세션/검증/성능 (`frontend/`)
      — tsc 타입체크 + vite 빌드 통과, /ws/flow 실시간 + /api 프록시
- [x] perf: ramp-up 부하생성 + 메트릭(setup latency/duration p50·p95·p99/throughput/실패율) (`backend/sim/perf/`)
      — 77건 통과. /api/perf/run·/api/perf, 대시보드 부하시험 패널, perf 결과 SYS 이벤트. 대규모(~2000+)는 확장 지점
