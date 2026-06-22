# CLAUDE.md — 폐쇄망 PKG Init/Install 자동화 (Air-gapped Provisioning Orchestrator)

> 이 문서는 **오케스트레이션 마스터 컨텍스트**다. Claude Code 가 `pkg-installer/` 하위에서 작업할 때
> 항상 이 파일을 읽고, 루트 `.claude/agents/pkg-*.md` 에 정의된 **서브 에이전트**에게 작업을 위임한다.
> 각 에이전트는 자신의 담당 영역 스펙(`pkg-installer/docs/specs/*.md`)만으로 **독립 개발**이 가능하도록 작성되었다.
>
> ⚠️ **전제**: 대상 환경은 **인터넷이 없는 폐쇄망(air-gapped)** 이다. 모든 패키지/커널/의존성은
> **로컬 미러(오프라인 번들)** 에서만 설치한다. 어떤 역할/태스크도 외부 인터넷을 가정해선 안 된다.
> 외부 다운로드(`yum`/`dnf`/`pip`/`get_url` to internet)는 **금지**, 항상 로컬 repo/번들 경유.

---

## 0. 한눈에 보기 (TL;DR)

- **무엇을 만드나**: 폐쇄망에서 **OS(CentOS 7 / RHEL 8) 를 선택**하면 **Ansible** 로
  **커널 → 패키지 → 설정(config)** 까지 일괄 프로비저닝하는 **설치 자동화 + 관제 대시보드**.
- **핵심 동작**: 대시보드에서 OS/프로파일/대상호스트를 고르고 **실행** → 백엔드가 `ansible-runner`
  로 플레이북을 구동 → **태스크 단위 이벤트/로그를 실시간 스트리밍** → 끝나면 **설치 완료 보고서** 생성.
- **대시보드**: 모든 기능을 단일 웹 UI 에서 제어. **단계(stage) 진행도 + 호스트별 상태 + 실시간 로그**,
  **태스크 클릭 → 원문 stdout/stderr 드릴다운**, 완료 시 **보고서 미리보기/다운로드**.
- **폐쇄망 우선**: 오프라인 로컬 repo(yum/dnf) 미러와 번들이 1급 시민. 인터넷 의존 0.
- **기술 스택**: Backend = **Python**(asyncio, FastAPI, WebSocket, ansible-runner),
  Frontend = **React + TypeScript(Vite)**, 프로비저닝 = **Ansible**.
- **멱등성(idempotency)**: 모든 역할은 재실행 안전. 두 번 돌려도 동일 상태 수렴.

---

## 1. 대상 시스템 & 경계 (SUT / Scope)

```
            [ 관제 노드 (우리 = Controller) ]
   ┌────────────────────────────────────────────────┐
   │  Frontend(React/TS)  ──ws/rest──  Backend(FastAPI)│
   │                                      │            │
   │                                ansible-runner     │
   └──────────────────────────────────────┼───────────┘
                                           │ SSH (폐쇄망 내부)
              ┌────────────────────────────┼───────────────────────────┐
              ▼                            ▼                            ▼
      ┌──────────────┐            ┌──────────────┐            ┌──────────────┐
      │ Target host  │            │ Target host  │            │ Local Mirror │
      │ (CentOS 7)   │            │ (RHEL 8)     │            │ (offline repo│
      │ kernel/pkg/  │◀──yum/dnf──│ kernel/pkg/  │◀──yum/dnf──│  + 번들 tar) │
      │ config       │            │ config       │            └──────────────┘
      └──────────────┘            └──────────────┘
```

- **Controller**: 대시보드 백엔드가 도는 관제 노드. Ansible 제어 노드 역할.
- **Target host**: 프로비저닝 대상. OS 는 **CentOS 7(yum, kernel 3.10) 또는 RHEL 8(dnf, kernel 4.18)**.
- **Local Mirror**: 폐쇄망 내부의 오프라인 패키지 저장소(자체 yum/dnf repo) 또는 대상 호스트에
  복사되는 **오프라인 번들(tar)**. 외부 인터넷 대체재. (`pkg-offline-repo` 담당)

### 1.1 설치 단계(Stage) 상태머신 (권위: `docs/specs/install-stages.md`)
| 순서 | stage | 내용 | 담당 역할(role) |
|---|---|---|---|
| 1 | `preflight` | SSH 연결, OS/아키텍처 탐지, 디스크/메모리, 로컬 repo 가용성 확인 | `common` |
| 2 | `offline-repo` | 오프라인 미러/번들을 대상에 등록(.repo 작성, GPG 키, `yum clean`) | `offline_repo` |
| 3 | `kernel` | 커널 패키지 설치/업그레이드, 부트로더 갱신, 필요 시 재부팅 후 검증 | `kernel` |
| 4 | `packages` | 프로파일별 패키지 그룹 설치(로컬 repo 한정) | `packages` |
| 5 | `config` | 시스템 설정(sysctl, limits, systemd, 서비스, 템플릿) 적용 | `config` |
| 6 | `validate` | 설치 후 검증(버전/서비스/설정 정합성) — 멱등 체크 | `validate` |
| 7 | `report` | 수집된 facts/결과 → **설치 완료 보고서** 생성 | (backend `pkg-report`) |

- 각 stage 는 **실패 시 중단(fail-fast) 또는 계속(best-effort)** 정책을 config 로 선택.
- `kernel` 의 재부팅은 폐쇄망에서 위험하므로 **명시적 opt-in(`reboot_allowed: true`)** 일 때만 수행.

---

## 2. 자동화 목표 & 검증 범위

### 2.1 기능 목표
1. **OS 선택 분기**: CentOS 7(yum) / RHEL 8(dnf) 를 대시보드에서 선택 → 동일 플레이북이 OS별 분기.
2. **폐쇄망 설치**: 오프라인 로컬 repo/번들만으로 커널~패키지~설정 설치. 인터넷 0 의존.
3. **단계별 프로비저닝**: preflight→offline-repo→kernel→packages→config→validate.
4. **대시보드 관제(핵심)**:
   - OS/프로파일/대상호스트/옵션 선택, **실행/중지**.
   - **단계 진행도 + 호스트별 상태(ok/changed/failed/unreachable)** 실시간.
   - **실시간 로그 스트리밍** + **태스크 클릭 → 원문 stdout/stderr/diff 드릴다운**.
5. **설치 완료 보고서**: 성공/실패 요약, OS/커널/패키지 버전 목록, 변경 항목(changed), 검증 결과,
   소요시간, 호스트별 상세 → **HTML/Markdown(+PDF 옵션)** 으로 저장·다운로드.
6. **멱등성/안전성**: 재실행 안전, 폐쇄망 가드(외부망 차단), 재부팅 opt-in.

### 2.2 비범위 (Out of Scope, 1차)
- Windows 대상, 컨테이너(K8s) 프로비저닝(스펙은 확장 지점만 남김).
- 베어메탈 PXE 부팅/OS 설치 자체(우리는 **이미 OS 설치된 호스트** 위에서 동작).
- 멀티 사이트/멀티 미러 동기화(1차는 단일 미러 가정, 구조만 확장 가능).

---

## 3. 시스템 아키텍처

```
┌──────────────────────────── Frontend (React + TS / Vite) ───────────────────────┐
│  OS/Profile 선택 │ 실행 제어 │ Stage 진행도 │ 호스트 상태 │ 실시간 로그 │ 보고서 │
└──────────────────────────────── WebSocket / REST ───────────────────────────────┘
                                       │
┌──────────────────────────── Backend (Python / asyncio) ─────────────────────────┐
│  api/            FastAPI REST + WebSocket 게이트웨이        (pkg-installer-backend)│
│  ───────────────────────────────────────────────────────────────────────────    │
│  installer/runner.py   ansible-runner 구동/이벤트 변환     (pkg-platform)         │
│  installer/eventbus.py EventBus(pub/sub) + 링버퍼          (pkg-platform)         │
│  installer/models.py   TaskEvent/RunState/Report 모델      (pkg-platform)         │
│  installer/logging.py  structured log + event_id 태깅      (pkg-platform)         │
│  installer/config.py   installer.yaml 로더                 (pkg-platform)         │
│  installer/report.py   완료 보고서 생성기                  (pkg-report)           │
│  installer/validate.py 검증 결과 수집/판정                 (pkg-validator)        │
└──────────────────────────────────────────────────────────────────────────────────┘
                                       │ ansible-runner (SSH)
┌──────────────────────────────── Ansible ────────────────────────────────────────┐
│  playbooks/site.yml → roles: common, offline_repo, kernel, packages, config,     │
│  validate.  inventory/(대상호스트), group_vars/(OS별 변수).  (pkg-ansible)         │
│  오프라인 미러/번들 구성 + .repo 템플릿 + 번들 빌드 도구.   (pkg-offline-repo)      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 공통 이벤트 모델 (모든 에이전트 준수 — `backend/installer/models.py`)
모든 구성요소는 **EventBus** 로 구조화 이벤트를 발행하고, backend 가 이를 WebSocket 으로 중계한다.
단계 진행도와 로그 드릴다운은 **이 모델 위에서만** 구현된다. (uVCS 프로젝트의 FlowEvent 와 동일 철학)

```python
# 상관키: 모든 이벤트는 run_id(설치 실행) 와 host(대상 호스트) 로 상관된다.
class TaskEvent:
    event_id: str       # 고유 ID (로그 드릴다운 키)
    ts: float           # epoch (ms 정밀도)
    run_id: str         # 설치 실행 ID
    host: str           # 대상 호스트 (또는 "localhost"/"controller")
    os_target: str      # "centos7" | "rhel8"
    stage: str          # "preflight"|"offline-repo"|"kernel"|"packages"|"config"|"validate"|"report"
    role: str           # ansible role 이름
    task: str           # ansible task 이름
    action: str         # module/action (예: "yum", "copy", "command")
    status: str         # "running"|"ok"|"changed"|"failed"|"skipped"|"unreachable"
    summary: str        # 한 줄 요약
    payload: dict       # ansible result/facts/diff (구조화)
    log_ref: str        # 원문 로그 위치 (event_id 로 조회)
    severity: str       # "info" | "warn" | "error"
```

- **로그 드릴다운 계약**: 프론트가 태스크(=TaskEvent) 클릭 → `GET /api/runs/{run_id}/events/{event_id}/logs`
  → 해당 태스크의 **원문 stdout/stderr, ansible result(json), diff** 를 반환.
- **로그 저장**: `installer/logging.py` 가 `event_id` 를 모든 로그 라인에 태깅(structured log).
- **진행 상태(RunState)**: `run_id` 별 stage 진행/호스트별 상태/통계를 집계(대시보드 진행도 패널 소스).

### 3.2 모듈 간 인터페이스 (계약)
- `pkg-installer-backend` → `pkg-platform.runner`: 설치 실행/중지, ansible-runner 이벤트 콜백을 `TaskEvent` 로 변환.
- `pkg-platform.runner` → `EventBus.publish(TaskEvent)`: 모든 ansible 이벤트는 EventBus 로 발행.
- `pkg-ansible`(roles) ← config/profile: backend 가 extravars/inventory 를 생성해 runner 에 주입.
- `pkg-offline-repo` ⇄ `pkg-ansible`: offline_repo role 이 미러/번들 스펙(`docs/specs/offline-repo.md`)을 따른다.
- `pkg-validator` → validate role 산출(JSON)을 읽어 PASS/FAIL 판정 → `TaskEvent(stage=validate)`.
- `pkg-report` → RunState + validate 결과 + facts → 보고서 파일 생성, `GET /api/runs/{run_id}/report`.
- `pkg-dashboard-frontend` → REST(제어/조회) + WebSocket(`/ws/runs/{run_id}`) 구독.

---

## 4. 오케스트레이션 방식 (Claude Code 사용법)

이 프로젝트는 **오케스트레이터(이 CLAUDE.md) + 서브 에이전트** 구조로 개발한다.

### 4.1 에이전트 카탈로그 (루트 `.claude/agents/pkg-*.md`)
| 에이전트 | 파일 | 담당 | 주 스펙 |
|---|---|---|---|
| **pkg-platform** | `pkg-platform.md` | config, logging, EventBus, models(TaskEvent/RunState), ansible-runner 래퍼 | §3.1, `event-model.md`, `install-stages.md` |
| **pkg-ansible** | `pkg-ansible.md` | playbook/roles/inventory, OS(centos7/rhel8) 분기, kernel/packages/config/validate | `ansible-layout.md`, `os-matrix.md` |
| **pkg-offline-repo** | `pkg-offline-repo.md` | 폐쇄망 로컬 미러/번들, .repo 템플릿, GPG, 번들 빌드 도구 | `offline-repo.md` |
| **pkg-installer-backend** | `pkg-installer-backend.md` | FastAPI REST + WebSocket, 실행 제어, 로그 스트리밍, 진행도/드릴다운 API | §3.1, §5 |
| **pkg-dashboard-frontend** | `pkg-dashboard-frontend.md` | React/TS UI: OS선택/제어/진행도/호스트상태/실시간로그/보고서 | §3.1, §5 |
| **pkg-validator** | `pkg-validator.md` | 설치 후 검증(버전/서비스/설정), validate role 산출 판정 | `validation-spec.md`, `os-matrix.md` |
| **pkg-report** | `pkg-report.md` | 설치 완료 보고서 생성기(HTML/MD/PDF), 스키마/섹션 | `report-spec.md` |

### 4.2 오케스트레이터(=메인 세션) 규칙
1. 작업 요청을 받으면 **어느 에이전트 담당인지 매핑** 후 해당 에이전트에 위임한다.
2. 여러 에이전트가 필요한 작업은 **인터페이스(§3.2) 우선 합의 → 병렬 위임** 한다.
3. **공유 계약(TaskEvent, stage 정의, repo 스펙, 보고서 스키마)** 변경은 반드시 이 CLAUDE.md / `docs/specs` 를 먼저 갱신한 뒤 진행한다.
4. 새 기능은 **TDD 우선**: `backend/tests/` 에 계약 테스트 먼저, 역할은 `ansible-lint` + `--check`(dry-run) 우선.
5. 모든 구현은 §7 규약(디렉토리/네이밍/config/폐쇄망 가드)을 따른다.
6. **폐쇄망 가드**: 어떤 에이전트도 외부 인터넷에서 패키지를 받지 않는다. 의심되면 즉시 중단·보고.

---

## 5. 대시보드 요구사항 (필수 기능)
1. **실행 제어판**: OS 선택(CentOS7/RHEL8), 프로파일 선택(package set), 대상 호스트/그룹 선택,
   옵션(재부팅 허용, dry-run, fail-fast), **실행/중지**.
2. **Stage 진행도**: preflight→…→report 의 단계별 진행 바(대기/진행/완료/실패), 단계별 소요시간.
3. **호스트 상태 테이블**: 호스트별 현재 stage, ok/changed/failed/unreachable 카운트, 최종 상태.
4. **실시간 로그 콘솔**: WebSocket 스트림. stage/host/severity 필터, 자동 스크롤, 색상(info/warn/error).
5. **태스크 클릭 → 로그 드릴다운**: 우측 패널에 **원문 stdout/stderr + ansible result(json) + diff** 표시
   (`GET /api/runs/{run_id}/events/{event_id}/logs`).
6. **설치 완료 보고서**: 완료 시 보고서 미리보기 + **다운로드(HTML/MD/PDF)**.
7. (확장) 과거 실행 이력(run history)과 비교.

---

## 6. 프로파일 & OS 매트릭스 (요약, 상세는 docs/specs)
> 프로파일은 `config/profiles/*.yaml` 로 선언되고, backend 가 extravars 로 ansible 에 주입한다.

| 항목 | CentOS 7 | RHEL 8 |
|---|---|---|
| 패키지 매니저 | `yum` | `dnf` |
| 커널 계열 | 3.10.x | 4.18.x |
| 서비스 관리 | `systemd` | `systemd` |
| repo 파일 | `/etc/yum.repos.d/*.repo` | `/etc/yum.repos.d/*.repo` |
| 모듈스트림 | 해당없음 | `dnf module` (appstream) |
| 오프라인 미러 | `createrepo` 기반 | `createrepo_c` 기반 |

- 분기는 `ansible_distribution`/`ansible_distribution_major_version` fact 또는 사용자가 고른 `os_target` 으로.
- 프로파일 예시: `base`(최소), `web`(nginx/httpd), `db`(mariadb/postgres), `custom`(목록 지정).
  실제 패키지 목록은 **폐쇄망 미러에 존재하는 것만** 허용(없으면 preflight 에서 실패 보고).

---

## 7. 개발 규약 (모든 에이전트 공통)

### 7.1 디렉토리 구조 (`pkg-installer/`)
```
pkg-installer/
├── CLAUDE.md                       # (이 파일) 오케스트레이션 마스터
├── README.md
├── docs/specs/*.md                 # 상세 설계 스펙 (embed)
├── config/
│   ├── installer.yaml              # 전역 설정(host/port/경로/미러/정책)
│   └── profiles/*.yaml             # 설치 프로파일(패키지 세트)
├── ansible/
│   ├── ansible.cfg
│   ├── inventory/                  # 대상 호스트 인벤토리
│   ├── group_vars/                 # OS별/그룹별 변수
│   ├── playbooks/site.yml          # 진입 플레이북
│   └── roles/{common,offline_repo,kernel,packages,config,validate}/
├── backend/
│   ├── pyproject.toml
│   ├── installer/                  # pkg-platform + report/validate 로직
│   ├── api/                        # pkg-installer-backend (FastAPI)
│   └── tests/                      # pytest
├── frontend/                       # pkg-dashboard-frontend (React+TS, Vite)
└── reports/                        # 생성된 설치 완료 보고서
```
> ⚠️ 서브 에이전트 정의(`.md`)는 Claude Code 인식을 위해 **저장소 루트 `.claude/agents/pkg-*.md`** 에 둔다.

### 7.2 기술/도구
- Python ≥ 3.11, `asyncio`. 패키지: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`,
  `ansible-runner`, `pyyaml`, `jinja2`(보고서), `pytest`, `pytest-asyncio`.
- Ansible ≥ 2.14(ansible-core). `ansible-lint`, `yamllint`. 모듈은 `ansible.builtin` 우선.
- Frontend: React + TypeScript + Vite, WebSocket, 로그 콘솔/진행도 시각화.
- Lint/format: `ruff` + `black`(py), `ansible-lint`/`yamllint`(ansible), `eslint` + `prettier`(ts).

### 7.3 설정 원칙
- **하드코딩 금지**: 모든 host/port/경로/미러 URL 은 `config/installer.yaml` + `inventory`.
- **폐쇄망 가드**: repo/번들 외 외부 URL 금지. role 은 `assert` 로 인터넷 미사용을 강제 가능하게.
- **멱등성**: 모든 task 는 재실행 안전(`creates`/`state=present`/체크). `command`/`shell` 최소화.
- **비밀정보**: SSH 키/패스워드/구독정보는 `ansible-vault` 또는 env. 평문 커밋 금지.

### 7.4 빌드/실행/테스트 (확정 후 README 동기화)
```bash
# backend
cd pkg-installer/backend && pip install -e . && pytest
uvicorn api.main:app --reload          # 대시보드 백엔드

# ansible (dry-run, 폐쇄망 대상)
cd pkg-installer/ansible && ansible-lint && ansible-playbook -i inventory playbooks/site.yml --check

# frontend
cd pkg-installer/frontend && npm install && npm run dev
```

### 7.5 Git
- 개발 브랜치: `claude/inspiring-cray-jz5ifw`. 명시 요청 없이는 PR 생성 금지.
- 커밋은 작고 의미 단위로. 공유 계약 변경은 `docs/specs` + 이 CLAUDE.md 동시 갱신.

---

## 8. 진행 상태 보드 (오케스트레이터가 갱신)
- [ ] pkg-platform: config/logging/eventbus/models(TaskEvent,RunState)/ansible-runner 래퍼
- [ ] pkg-ansible: site.yml + roles(common/offline_repo/kernel/packages/config/validate), OS 분기, inventory/group_vars
- [ ] pkg-offline-repo: 로컬 미러/번들 스펙, .repo 템플릿, GPG, 번들 빌드 도구
- [ ] pkg-installer-backend: FastAPI REST(실행/조회/보고서) + /ws/runs WebSocket + 드릴다운 API
- [ ] pkg-validator: 설치 후 검증 체크(버전/서비스/설정), validate role 산출 판정
- [ ] pkg-report: 완료 보고서 생성기(HTML/MD/PDF), 스키마/섹션
- [ ] pkg-dashboard-frontend: OS선택/제어/진행도/호스트상태/실시간로그/드릴다운/보고서

> 스캐폴드(디렉토리/스펙/에이전트/시드 설정)는 구성 완료. 각 항목은 담당 에이전트가 TDD 로 채운다.
