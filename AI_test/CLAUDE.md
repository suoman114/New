# Infra Automation Web Server

## 프로젝트 개요
폐쇄망(Air-gapped) 환경에서 OS 셋업, 패키지 배포/설치 및 설치 후 검증 작업을 자동화하는 웹 서버.
완성된 애플리케이션은 RPM 패키지로 빌드하여 배포한다.

## 기술 스택
- **Language**: Java 1.8
- **Framework**: Spring Boot
- **Build**: Maven (RPM 패키지 배포 포함)
- **Database**: MariaDB
- **API**: REST API
- **자동화**: Ansible (OS / PKG 셋업)
- **대상 OS**: CentOS, Ubuntu

## 패키지 구조
```
com.lter.infra
├── controller    # REST API 엔드포인트
├── service       # 비즈니스 로직
├── repository    # DB 접근 (MariaDB)
├── domain        # Entity / DTO
├── config        # Spring 설정
└── util          # 공통 유틸 (스크립트 실행 등)
```

## RPM 패키지 네이밍
- 형식: `LTER-infra-R{버전}.rpm`
- 버전 형식: `R1.0.0` (R{Major}.{Minor}.{Patch})
- 예시: `LTER-infra-R1.0.0.rpm`

## 빌드 & 실행
```bash
# 애플리케이션 빌드
mvn clean package

# RPM 패키지 빌드
mvn clean package -Prpm

# 로컬 실행
mvn spring-boot:run
```

## API 설계 원칙
- RESTful 설계 준수
- 기본 URL prefix: `/api/v1`
- 응답 포맷: JSON
- HTTP 상태 코드 적절히 사용 (200, 201, 400, 404, 500)

## Ansible Playbook 구성

### Inventory
- 대상 호스트 그룹: `vcs`
- 소스 파일 경로 (Ansible 서버): `/root/lter_vcs_busan/`
- RPM 임시 경로: `/root/rpm/`

### OS 셋업 순서 (번호 순 실행)
| 순서 | 파일 | 설명 |
|------|------|------|
| 0 | `0_auto_pass.yml` | SSH 키 교환, SELinux 비활성화 |
| 1 | `1_PAM_limits.yml` | PAM limits 설정 (nofile, stack, nproc, core) |
| 2 | `2_systemctl_stop.yml` | 불필요 서비스 중지, rsyslog 설정 |
| 3 | `3_sysctl.yml` | 커널 파라미터 튜닝 |
| 4 | `4_ntp.yml` | NTP 설치 및 설정 |
| 5 | `5_visudo_vcs.yml` | vcs 그룹 sudo 권한 부여 |
| 12 | `12_Cron_root.yml` | 헬스체크 Cron 등록 |
| 14 | `14_ramdisk.yml` | Ramdisk 마운트 설정 |
| 15 | `15_ldconf.yml` | ld.so 설정 |
| 15 | `15_rclocal.yml` | rc.local ring buffer, iptables 설정 |
| 16 | `16_watermark.yml` | Watermark 파일 복사 |

### PKG 셋업 순서
| 순서 | 파일 | 설명 |
|------|------|------|
| 6 | `6_RMQ_vcs.yml` | RabbitMQ 설치 및 설정 |
| 7 | `7_openjdk.yml` | OpenJDK 1.8 설치 |
| 8-1 | `8-1_mariaDB.yml` | MariaDB 설치, DB/계정 생성 |
| 8-2 | `8-2_mariaDB_chown.yml` | MariaDB 디렉토리 권한 설정 |
| 9-1 | `9-1_group_vcs.yml` | vcs 계정/그룹 생성 (uid:802, gid:801) |
| 9-2 | `9-2_chmod_vcs.yml` | vcs 디렉토리 권한 설정 |
| 10-1 | `10-1_group_vcweb.yml` | vcweb 계정/그룹 생성 (uid:1003, gid:1002) |
| 10-2 | `10-2_chmod_vcweb.yml` | vcweb 디렉토리 권한 설정 |
| 11 | `11_vcs_dic.yml` | VCS 패키지 배포 및 RPM 설치 |
| 13 | `13_service_start.yml` | 서비스 init.d 등록 및 활성화 |

### 주요 설정 변수 (사용자 입력 필요)
| 변수 | 설명 | 예시 |
|------|------|------|
| `ansible_host` | 대상 서버 IP | `192.168.1.10` |
| `ntp_server` | NTP 서버 IP (동적 입력, `4_ntp.yml`에 `-e` 옵션으로 전달) | `192.168.7.23` |
| `new_password` | MariaDB root 비밀번호 | `root.123` |
| `database_name` | 초기 DB 이름 | `VCSM` |

### Ansible 동적 변수 전달 방식
- `ansible-playbook` 실행 시 `-e` (extra-vars) 옵션으로 동적 변수 전달
- 예시: `ansible-playbook 4_ntp.yml -e "ntp_server=192.168.7.23"`
- `4_ntp.yml`의 하드코딩된 NTP IP는 `{{ ntp_server }}` 변수로 교체
- API 요청 시 `ntpServer` 필드를 받아 playbook 실행 시 주입

### Java에서 Ansible 실행 방식
- `ProcessBuilder`를 사용하여 `ansible-playbook` 명령어 실행
- 실행 결과(stdout, stderr, exit code)를 DB(`job_history`)에 저장
- 비동기 실행 후 jobId로 상태 조회

## 주요 API 엔드포인트

### 1. 서버 등록 (`/api/v1/servers`)
| Method | URL | 설명 |
|--------|-----|------|
| GET | `/api/v1/servers` | 서버 목록 조회 |
| POST | `/api/v1/servers` | 서버 등록 |
| GET | `/api/v1/servers/{id}` | 서버 상세 조회 |
| PUT | `/api/v1/servers/{id}` | 서버 정보 수정 |
| DELETE | `/api/v1/servers/{id}` | 서버 삭제 |

### 2. OS / PKG 셋업 (`/api/v1/setup`)
| Method | URL | 설명 |
|--------|-----|------|
| POST | `/api/v1/setup/os` | OS 셋업 실행 (Ansible playbook 0~5, 12~16) |
| POST | `/api/v1/setup/package` | PKG 설치 실행 (Ansible playbook 6~13) |
| GET | `/api/v1/setup/status/{jobId}` | 셋업 작업 상태 조회 |

### 3. Validation 스크립트 실행 (`/api/v1/validation`)
| Method | URL | 설명 |
|--------|-----|------|
| POST | `/api/v1/validation/run` | 검증 스크립트 실행 |
| GET | `/api/v1/validation/result/{jobId}` | 실행 결과 조회 |
| GET | `/api/v1/validation/history` | 실행 이력 조회 |

## 전체 작업 흐름
```
[Git 저장소]
    │
    ├── RPM 파일들
    └── Validation 스크립트
         │
         ▼
[LTER 웹 서버] ── Git pull ──▶ 로컬 스토리지 (RPM, 스크립트 보관)
         │
         ├── 1. OS 셋업    ──▶ Ansible playbook 실행 (대상 서버)
         ├── 2. PKG 설치   ──▶ Git에서 가져온 RPM으로 Ansible 실행
         └── 3. Validation ──▶ Git에서 가져온 스크립트 실행 → 결과 저장
```

## 주요 도메인
- **OS Setup**: 대상 서버 OS 초기 설정 자동화
- **Package**: PKG 배포 및 설치 관리
- **Script**: 설치 후 검증 스크립트 실행 및 결과 관리
- **Target**: 대상 서버 관리 (CentOS / Ubuntu)

## DB 테이블 구성
| 테이블 | 설명 |
|--------|------|
| `target_server` | 대상 서버 목록 (IP, OS 종류, 상태 등) |
| `job_history` | 작업 실행 이력 (실행자, 시작/종료 시간, 성공/실패, 로그) |
| `script` | Validation 스크립트 관리 (이름, Git 경로, 버전) |
| `git_repo` | Git 연동 정보 (repo URL, branch, 인증 정보, 로컬 저장 경로) |
| `package` | RPM 패키지 관리 (이름, 버전, Git 경로, 로컬 경로, 대상 OS) |

## Git 연동 구성

### 용도
- **RPM 파일**: PKG 설치에 사용할 RPM들을 Git에서 관리
- **Validation 스크립트**: 설치 후 검증 스크립트를 Git에서 관리

### 동작 방식
1. 웹 서버가 Git repo에서 `git pull` (또는 `git clone`)
2. 가져온 파일을 웹 서버 로컬 스토리지에 저장
3. Ansible playbook 실행 시 로컬 경로의 RPM 파일 사용
4. Validation 실행 시 로컬 경로의 스크립트 실행

### Git 실행 방식
- Java `ProcessBuilder`로 `git clone` / `git pull` 명령어 실행
- 인증: SSH Key 또는 username/password 방식 지원
- 폐쇄망이므로 내부 Git 서버(GitLab, Gitea 등) 사용 전제

## Validation 스크립트 구성

### 스크립트 종류
| 파일 | 용도 |
|------|------|
| `os_audit.sh` | OS 감사 - 70+ 항목 수집 (계정, 네트워크, 커널, 서비스 등) |
| `verify_vcs_install.sh` | VCS 설치 검증 - RPM 버전, 계정, 디렉토리, 설정파일, 프로세스 확인 |

### os_audit.sh
- 인수: `./os_audit.sh [서버명]`
- 출력 형식: `===SECTION:섹션명===` / `===CONFIG:항목===` 구조로 파싱 가능
- 섹션 목록: `User`, `Network`, `Sudo`, `ulimit`, `Kernel`, `rootlock`, `config_full_audit`, `Disk`, `SW_Backup_list`, `META`
- 환경변수로 동적 설정 가능:
  - `OS_AUDIT_REQUIRED_USERS` — 필수 계정 패턴 (기본: `vcs|vcsdn`)
  - `OS_AUDIT_BACKUP_PATHS` — 백업 경로 (기본: `/backup`)
  - `OS_AUDIT_SYSCTL_FILE` — sysctl 설정 파일 경로

### verify_vcs_install.sh
- 인수 없음, 환경변수 `APP_AUDIT`으로 작업 디렉토리 지정
- 보고서 파일 자동 생성: `VCS_INSTALL_VERIFY_YYYYMMDD_HHMMSS.txt`
- 검증 항목:
  1. 3rd Party RPM 버전 점검 (Java 1.8, RabbitMQ 3.7.13, Erlang 21.3.7, MariaDB 10.4.12)
  2. OS 계정 점검 (vcs, vcweb)
  3. 디렉토리 및 Web 패키지 점검
  4. 설정 파일 및 YAML 점검
  5. IP 및 프로세스 설정 점검

### 결과 파싱 기준
| 태그 | 의미 |
|------|------|
| `[OK]` | 정상 |
| `[WARN]` | 경고 (설치됐으나 버전 상이 등) |
| `[FAIL]` | 실패 (미설치, 미존재 등) |

### Java에서 스크립트 실행 방식
- `ProcessBuilder`로 대상 서버에 SSH 접속 후 스크립트 실행
- 실행 결과(stdout) 파싱 → `[OK]` / `[WARN]` / `[FAIL]` 집계 후 DB 저장
- 보고서 파일은 대상 서버에 저장되며, 경로를 `job_history`에 기록

## 주의사항
- 폐쇄망 환경이므로 외부 네트워크 의존성 없이 동작해야 함
- 스크립트 실행 시 실행 결과(성공/실패/로그)를 반드시 DB에 저장
- 코딩 진행 중 규칙 추가 예정

---

## 오케스트레이션 (Claude Code 서브 에이전트)

이 프로젝트는 **오케스트레이터(이 문서) + 서브 에이전트** 방식으로 확장한다.
에이전트 정의는 저장소 루트 `.claude/agents/pkg-*.md` 에 있으며, Claude Code 가 작업을 위임받아 개발한다.

> ⚠️ **스코프 보강**: 본 문서 상단의 "대상 OS: CentOS, Ubuntu" 는 서버 등록 대분류
> (`TargetServer.OsType = CENTOS|UBUNTU`)다. **설치 자동화 OS 타깃 스코프는 CentOS 7 + RHEL 8** 로 확정했고,
> 버전·패키지매니저(yum/dnf)·커널기준선·모듈스트림 분기는 `com.lter.infra.common.OsTarget`(CENTOS7/RHEL8)을 단일 출처로 쓴다.

### 에이전트 카탈로그
| 에이전트 | 담당 | 주요 코드 |
|---|---|---|
| **pkg-platform** | 공통 기반(프로세스 실행기/설정/SSE 로그/공통 응답·예외·OsTarget/작업이력) | `util/*`, `service/SystemConfigService`, `service/SseLogService`, `common/*`, `entity/InfraConfig`·`JobHistory` |
| **pkg-ansible** | Ansible playbook(0~16), OS/PKG 셋업 순서, extra-vars, CentOS7/RHEL8 분기 | `ansible_yml/*.yml` |
| **pkg-offline-repo** | 폐쇄망 RPM/스크립트 수급(내부 Git→로컬→대상), 패키지 배포 | `service/GitService`·`PackageService`·`PackageDeployService`, `util/GitExecutor`, `entity/GitRepo`·`Package` |
| **pkg-installer-backend** | REST API + SSE + 비동기 실행 + 파이프라인 오케스트레이션 | `controller/*`, `service/SetupService`·`PipelineService` |
| **pkg-dashboard-frontend** | 대시보드 UI(정적 리소스, SSE 로그 콘솔, 보고서 뷰) | `src/main/resources/static/*` |
| **pkg-validator** | 설치 후 검증(os_audit/verify_vcs_install 실행·파싱·집계) | `service/ValidationService`, `os_audit.sh`, `verify_vcs_install.sh` |
| **pkg-report** | 설치 완료 보고서(HTML/Excel: precheck/platform/postsetup/3rdparty) | `service/HtmlReportService`·`ExcelReportService`·`ReportService` |

### 오케스트레이터 규칙
1. 요청을 받으면 담당 에이전트로 매핑·위임한다. 공유 계약(ApiResponse, OsTarget, ProcessResult, SSE jobKey, job_history)
   변경은 이 문서를 먼저 갱신한 뒤 진행한다.
2. 외부 실행은 항상 `pkg-platform` 의 실행기(AnsibleExecutor/ScriptExecutor/GitExecutor)를 경유한다. 직접 ProcessBuilder 금지.
3. 모든 실행은 `job_history`(RUNNING→SUCCESS/FAIL)에 기록하고 실시간 로그는 `SseLogService` 로 흘린다.
4. **폐쇄망 가드**: 어떤 에이전트도 외부 인터넷 의존 금지(설치 경로·UI 자산·보고서 포함).
5. 새 로직은 가능한 한 **순수 함수로 분리 + JUnit 테스트**(`mvn test`).

### 진행 상태 보드 (JUnit 누적 53건 통과, `mvn test` BUILD SUCCESS)
- [x] pkg-platform: 공통 기반 + `OsTarget`(CENTOS7/RHEL8) + `InventoryGenerator` 순수화. (OsTarget/ApiResponse/ProcessResult/InventoryGenerator)
- [x] pkg-ansible: playbook 분류/번호prefix/정렬 규약을 `util/PlaybookCatalog` 로 단일화, SetupService 위임. (PlaybookCatalog 8건)
- [x] pkg-offline-repo: 원격 배포 명령(scp/ssh/extract)+Git 자격증명 URL 을 `util/RemoteCommandBuilder` 로 추출, PackageDeployService/GitExecutor 위임. (7건)
- [x] pkg-installer-backend: 런 순서 해석(SetupService.resolvePlaybooks/resolveResumeFrom)·SSE 로그 가드 테스트. (10건)
- [x] pkg-validator: `ScriptExecutor.parseValidationResult` [OK]/[WARN]/[MISS]/[FAIL] 집계·통과판정 테스트. (5건)
- [x] pkg-dashboard-frontend: 폐쇄망 가드 검증(static 외부 CDN 0건). UI 무리한 변경 없음.
- [x] pkg-report: 보고서 상태환산/HTML 이스케이프를 `util/ReportFormat` 로 추출, HtmlReportService 위임. (6건)

> 공통 패턴: 각 영역의 **순수 로직을 util 로 추출 → JUnit 고정 → 기존 서비스는 위임(동작 보존)**.
> 다음 단계는 통합/E2E(`@WebMvcTest` 컨트롤러 계약, ansible dry-run, 파이프라인 오케스트레이션) 확장.

### 통합/E2E (진행 중)
- [x] `@WebMvcTest(ServerController)` REST 계약: ApiResponse 형태(success/message/data), 검증 실패 400(IP/공백),
      bulk 빈 목록 400, CRUD 라우팅. (7건) — Spring 슬라이스 부팅 확인. **전체 60건 통과.**
- [ ] PipelineService 오케스트레이션(MANUAL 승인 waitForApproval/approve) 테스트 — DB/@Async 의존으로 슬라이스/목 설계 필요.
- [ ] ansible 플레이북 CentOS7/RHEL8 변수 분기(OsTarget) 실제 반영 — 대상 환경/ansible 툴링 필요(현재 미설치).

  