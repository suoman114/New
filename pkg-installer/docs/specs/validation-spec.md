# Spec: 설치 후 검증 (Validation)

> pkg-validator + ansible validate role 공용. 검증 항목/산출 JSON/판정 규칙의 단일 출처.

## validate role 산출 JSON (호스트별)
```json
{
  "host": "node01",
  "os_target": "rhel8",
  "facts": {
    "running_kernel": "4.18.0-348.el8.x86_64",
    "installed_kernels": ["4.18.0-348.el8.x86_64"],
    "packages": {"nginx": "1.20.1-1.el8", "chrony": "4.1-1.el8"},
    "services": {"nginx": {"enabled": true, "active": true}},
    "sysctl": {"net.ipv4.ip_forward": "1"},
    "files": {"/etc/nginx/nginx.conf": {"exists": true, "sha256": "..."}},
    "repos": {"offline": {"enabled": true}, "base": {"enabled": false}}
  }
}
```

## 판정기 입력/출력 (validate.py — 순수 함수)
- 입력: 위 facts JSON + 기대값(profile + manifest + os-matrix defaults).
- 출력: `ValidationResult` 항목 리스트.

```json
{
  "host": "node01",
  "checks": [
    {"id":"kernel.min_version","status":"PASS","expected":">=4.18.0-348","actual":"4.18.0-348.el8"},
    {"id":"pkg.nginx.version","status":"PASS","expected":"1.20.1-1.el8","actual":"1.20.1-1.el8"},
    {"id":"svc.nginx.active","status":"PASS","expected":true,"actual":true},
    {"id":"repo.external_disabled","status":"PASS","expected":"base=disabled","actual":"disabled"}
  ],
  "summary": {"pass": 4, "fail": 0, "warn": 0, "overall": "PASS"}
}
```

## 검증 항목(기본 체크리스트)
| id | 내용 | 판정 |
|---|---|---|
| `kernel.min_version` | 부팅 커널 ≥ `kernel_min_version` | actual ≥ expected → PASS |
| `kernel.running_matches_installed` | 부팅 커널이 설치 최신과 일치 | 불일치 → WARN(재부팅 필요) |
| `pkg.<name>.installed` | 프로파일 패키지 설치됨 | 미설치 → FAIL |
| `pkg.<name>.version` | 매니페스트 버전 일치 | 불일치 → FAIL(정책상 WARN 가능) |
| `svc.<name>.enabled/active` | 서비스 상태 | 불일치 → FAIL |
| `sysctl.<key>` | 커널 파라미터 적용 | 불일치 → FAIL |
| `file.<path>` | 설정 파일 존재/내용 | 불일치 → FAIL |
| `repo.external_disabled` | 외부 repo 비활성(폐쇄망) | 활성 → FAIL |

## 규칙
- 판정은 결정적·순수. 동일 입력 → 동일 결과.
- `overall = FAIL if any check FAIL`, else `WARN if any WARN`, else `PASS`.
- FAIL/WARN 은 보고서에서 강조되도록 expected/actual/host/stage 근거 포함.
