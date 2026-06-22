# Spec: 공통 이벤트 모델 (TaskEvent) — pkg-platform

> 권위 출처. `CLAUDE.md §3.1` 과 동기화. 변경 시 양쪽 모두 갱신.

## TaskEvent (backend/installer/models.py)
| 필드 | 타입 | 의미 |
|---|---|---|
| `event_id` | str | 고유 ID(로그 드릴다운 키). uuid4 권장 |
| `ts` | float | epoch(ms 정밀도) |
| `run_id` | str | 설치 실행 ID |
| `host` | str | 대상 호스트(또는 `localhost`/`controller`) |
| `os_target` | str | `centos7` \| `rhel8` |
| `stage` | str | `preflight`\|`offline-repo`\|`kernel`\|`packages`\|`config`\|`validate`\|`report` |
| `role` | str | ansible role 이름 |
| `task` | str | ansible task 이름 |
| `action` | str | module/action(예: `yum`,`dnf`,`copy`,`command`,`reboot`) |
| `status` | str | `running`\|`ok`\|`changed`\|`failed`\|`skipped`\|`unreachable` |
| `summary` | str | 한 줄 요약 |
| `payload` | dict | ansible result/facts/diff(구조화) |
| `log_ref` | str | 원문 로그 위치(event_id 로 조회) |
| `severity` | str | `info`\|`warn`\|`error` |

## ansible-runner 이벤트 → TaskEvent 매핑 (runner.py)
| ansible event | status | severity | 비고 |
|---|---|---|---|
| `playbook_on_task_start` | `running` | info | task 시작 |
| `runner_on_ok` (changed=false) | `ok` | info | |
| `runner_on_ok` (changed=true) | `changed` | info | payload.diff 포함 |
| `runner_on_skipped` | `skipped` | info | |
| `runner_on_failed` (ignore_errors) | `failed` | warn | best-effort 시 |
| `runner_on_failed` | `failed` | error | fail-fast 중단 트리거 |
| `runner_on_unreachable` | `unreachable` | error | SSH 도달 불가 |

- `stage` 결정: task/role 의 `tags`(`stage_preflight`…) 우선, 없으면 role 이름→stage 매핑 표(install-stages.md) 사용.
- `payload` 는 ansible result 의 핵심 필드(rc, stdout/stderr 길이, item, diff, msg)만 구조화. 원문 전체는 `log_ref` 로.

## RunState (집계)
| 필드 | 의미 |
|---|---|
| `run_id`, `os_target`, `profile`, `options` | 실행 메타 |
| `stages[stage] = {state, started, ended, ok, changed, failed}` | stage별 진행/통계 |
| `hosts[host] = {current_stage, ok, changed, failed, unreachable, final}` | 호스트별 상태 |
| `started`, `ended`, `overall` (`running`\|`success`\|`failed`) | 전체 상태 |

## EventBus 계약
- `publish(TaskEvent)` / `subscribe(run_id=None) -> async iterator`.
- 링버퍼(run_id별)로 late-join 백필. `get_event(event_id)` 로 드릴다운 원문 조회.
