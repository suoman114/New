# PKG Init/Install 자동화 (폐쇄망 Provisioning Orchestrator)

폐쇄망(air-gapped)에서 **OS(CentOS 7 / RHEL 8)를 선택**하면 **Ansible** 로
**커널 → 패키지 → 설정(config)** 까지 일괄 프로비저닝하고, **대시보드**에서 제어·실시간 로그를
보며, 완료 시 **설치 완료 보고서**를 생성하는 시스템.

> 개발은 **오케스트레이션 + 서브 에이전트** 방식. 마스터 컨텍스트는 [`CLAUDE.md`](./CLAUDE.md),
> 에이전트 정의는 저장소 루트 `.claude/agents/pkg-*.md`, 상세 스펙은 [`docs/specs/`](./docs/specs).

## 구성
| 영역 | 경로 | 담당 에이전트 |
|---|---|---|
| 공통 기반(config/log/EventBus/models/runner) | `backend/installer/` | `pkg-platform` |
| Ansible(playbook/roles/inventory) | `ansible/` | `pkg-ansible` |
| 폐쇄망 미러/번들 | `ansible/roles/offline_repo`, 빌드도구 | `pkg-offline-repo` |
| 대시보드 백엔드(FastAPI+WS) | `backend/api/` | `pkg-installer-backend` |
| 대시보드 UI(React/TS) | `frontend/` | `pkg-dashboard-frontend` |
| 설치 후 검증 | `backend/installer/validate.py`, `roles/validate` | `pkg-validator` |
| 완료 보고서 | `backend/installer/report.py` | `pkg-report` |

## 핵심 단계
`preflight → offline-repo → kernel → packages → config → validate → report`
(상세: [`docs/specs/install-stages.md`](./docs/specs/install-stages.md))

## 개발 명령 (스캐폴드 — 에이전트가 채움)
```bash
# backend
cd backend && pip install -e . && pytest
uvicorn api.main:app --reload

# ansible (폐쇄망 대상, dry-run)
cd ansible && ansible-lint && ansible-playbook -i inventory playbooks/site.yml --check

# frontend
cd frontend && npm install && npm run dev
```

## 폐쇄망 원칙
- 설치 경로에서 **외부 인터넷 0**. 모든 패키지는 오프라인 미러/번들(`docs/specs/offline-repo.md`).
- 커널 재부팅은 `reboot_allowed: true` 일 때만(기본 false).
- 모든 host/port/경로/미러는 `config/installer.yaml` + `ansible/inventory`. 하드코딩 금지.
