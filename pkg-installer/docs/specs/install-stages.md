# Spec: 설치 단계 상태머신 (Install Stages)

> 권위 출처. stage 정의/순서/태그/정책. `CLAUDE.md §1.1` 과 동기화.

## Stage 순서
```
preflight → offline-repo → kernel → packages → config → validate → report
```
- `report` 는 ansible 이 아니라 backend(`pkg-report`)가 수행(나머지는 ansible role).

## Stage ↔ role ↔ 태그 매핑
| stage | role | tag | 실패 정책 기본 |
|---|---|---|---|
| `preflight` | `common` | `stage_preflight` | fail-fast (전제 미충족이면 중단) |
| `offline-repo` | `offline_repo` | `stage_offline_repo` | fail-fast |
| `kernel` | `kernel` | `stage_kernel` | fail-fast |
| `packages` | `packages` | `stage_packages` | config(`fail_fast`) 따름 |
| `config` | `config` | `stage_config` | config(`fail_fast`) 따름 |
| `validate` | `validate` | `stage_validate` | best-effort(검증은 모두 수집 후 판정) |
| `report` | (backend) | — | always(실패해도 보고서 생성) |

## 정책 (config/installer.yaml)
- `fail_fast: true|false` — packages/config 단계에서 첫 실패 시 중단 여부.
- `reboot_allowed: true|false` — kernel 단계 재부팅 허용. 기본 `false`(폐쇄망 안전).
- `dry_run: true|false` — `ansible-playbook --check` 모드.

## 진행도 산출
- backend `runner.py` 가 `playbook_on_play_start`/task 의 stage 태그로 현재 stage 를 추적,
  RunState.stages 를 갱신 → 대시보드 진행 바의 단일 소스.

## kernel 재부팅 흐름 (reboot_allowed=true)
1. 커널 설치/업그레이드(changed) → 2. `reboot`(timeout 설정) → 3. 부팅 후 `uname -r` 로 새 커널 검증
→ 4. 실패 시 stage failed + 보고서에 기록. `reboot_allowed=false` 면 "재부팅 필요" 경고만 남기고 진행.
