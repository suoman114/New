# Spec: OS 매트릭스 (CentOS 7 vs RHEL 8)

> pkg-ansible / pkg-offline-repo / pkg-validator 공용. OS별 분기의 단일 출처.

| 항목 | CentOS 7 | RHEL 8 | 분기 변수 |
|---|---|---|---|
| `os_target` | `centos7` | `rhel8` | 사용자 선택 또는 fact |
| `ansible_distribution_major_version` | `7` | `8` | 자동 fact |
| 패키지 매니저 모듈 | `ansible.builtin.yum` | `ansible.builtin.dnf` | `pkg_mgr` |
| 커널 패키지 | `kernel` (3.10.x) | `kernel` (4.18.x) | `kernel_min_version` |
| repo 메타 생성 | `createrepo` | `createrepo_c` | (offline-repo) |
| 모듈 스트림 | 없음 | `dnf module enable/install` (appstream) | `use_module_streams` |
| 서비스 | systemd | systemd | 공통 |
| 부트로더 | grub2 (`grub2-mkconfig -o /boot/grub2/grub.cfg`) | grub2 (BIOS/UEFI 경로 주의) | `grub_cfg_path` |
| repo 디렉토리 | `/etc/yum.repos.d/` | `/etc/yum.repos.d/` | 공통 |

## group_vars 권장 키
```yaml
# group_vars/centos7.yml
os_target: centos7
pkg_mgr: yum
kernel_min_version: "3.10.0-1160"
use_module_streams: false

# group_vars/rhel8.yml
os_target: rhel8
pkg_mgr: dnf
kernel_min_version: "4.18.0-348"
use_module_streams: true
```

## 분기 규칙
- task 는 가능하면 `ansible.builtin.package`(추상) 또는 `pkg_mgr` 변수로 모듈 선택.
- RHEL8 모듈 스트림 필요한 패키지(예: nodejs, php)는 `use_module_streams` 가드 하에 `dnf module`.
- 커널 검증은 `kernel_min_version` 이상 + 부팅 커널(`uname -r`) 일치 여부(validation-spec.md).
- **구독(RHN/Satellite) 불필요**: 폐쇄망이므로 모든 소스는 offline repo. subscription-manager 사용 안 함.
