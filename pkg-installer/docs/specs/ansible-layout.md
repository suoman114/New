# Spec: Ansible 레이아웃 (playbook/roles/inventory)

> pkg-ansible 권위 출처. role 인터페이스/태그/변수 계약.

## 디렉토리
```
ansible/
├── ansible.cfg
├── inventory/
│   ├── hosts.ini                # [centos7] / [rhel8] 그룹
│   └── host_vars/*.yml          # 호스트별(ssh, ip)
├── group_vars/
│   ├── all.yml                  # 공통(offline repo, 정책)
│   ├── centos7.yml              # os-matrix
│   └── rhel8.yml
├── playbooks/site.yml
└── roles/{common,offline_repo,kernel,packages,config,validate}/
        ├── tasks/main.yml
        ├── defaults/main.yml
        ├── templates/
        ├── handlers/main.yml
        └── meta/main.yml
```

## site.yml 골격
```yaml
- hosts: "{{ target_hosts | default('all') }}"
  become: true
  gather_facts: true
  vars:
    os_target: "{{ os_target }}"       # extravars (backend 주입)
    profile: "{{ profile }}"
    fail_fast: "{{ fail_fast | default(true) }}"
    reboot_allowed: "{{ reboot_allowed | default(false) }}"
  roles:
    - { role: common,       tags: [stage_preflight] }
    - { role: offline_repo, tags: [stage_offline_repo] }
    - { role: kernel,       tags: [stage_kernel] }
    - { role: packages,     tags: [stage_packages] }
    - { role: config,       tags: [stage_config] }
    - { role: validate,     tags: [stage_validate] }
```

## role 인터페이스(입력 변수)
| role | 주요 입력 |
|---|---|
| `common` | `min_disk_gb`, `min_mem_mb`, `require_offline_only`(인터넷 차단 assert) |
| `offline_repo` | `offline.repo_name`, `offline.baseurl`, `offline.gpgkey`, `offline.bundle_path` |
| `kernel` | `kernel_min_version`, `reboot_allowed` |
| `packages` | `profile_packages`(프로파일에서 산출), `pkg_mgr`, `use_module_streams` |
| `config` | `sysctl`, `limits`, `services`, `config_templates` |
| `validate` | (입력 없음) 사실 수집 후 `validate_result` JSON 산출 |

## 산출(backend 연동)
- validate role 은 호스트별 `validate_result`(validation-spec.md 스키마) 를 `set_fact`/`copy` 로 노출.
- backend `runner.py` 가 ansible 이벤트의 `res` 에서 이를 수거 → pkg-validator 판정.

## 규약
- `become: true`. 멱등성 필수. `command/shell` 사용 시 `changed_when`/`creates`/`failed_when` 명시.
- 모든 외부 URL 금지(offline.baseurl 은 `file://` 또는 내부 http 미러). `common` 에서 assert.
- `ansible-lint`/`yamllint` 통과. `--syntax-check`/`--check` 우선 검증.
