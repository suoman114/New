# Spec: 폐쇄망 오프라인 미러/번들 (Offline Repo)

> pkg-offline-repo 권위 출처. 인터넷 없는 환경의 패키지 소스 규격.

## 모델
- **빌드 노드(인터넷 有, 1회)**: 패키지+의존성 수집 → `createrepo(_c)` → **번들 tar** + 매니페스트.
- **폐쇄망(인터넷 無)**: 번들을 미러 서버(내부 http) 또는 대상 호스트에 배치 → `.repo` 등록 → 설치.

## 번들 레이아웃
```
offline-bundle-{os_target}-{date}.tar.gz
└── offline-bundle/
    ├── repo/                     # rpm 들 + repodata/ (createrepo 산출)
    ├── gpg/RPM-GPG-KEY-...       # 서명 키
    └── manifest.json
```

## manifest.json 스키마
```json
{
  "os_target": "centos7|rhel8",
  "created": "2026-06-22T00:00:00Z",
  "createrepo": "createrepo|createrepo_c",
  "packages": [
    {"name": "nginx", "version": "1.20.1", "release": "1.el8", "arch": "x86_64",
     "file": "nginx-1.20.1-1.el8.x86_64.rpm", "sha256": "..."}
  ],
  "module_streams": [ {"name":"nodejs","stream":"18"} ]   // rhel8 옵션
}
```

## .repo 템플릿 (offline_repo role)
```ini
[offline]
name=Offline Mirror ({{ os_target }})
baseurl={{ offline.baseurl }}      # file:///opt/offline-bundle/repo  또는 http://mirror.internal/offline
enabled=1
gpgcheck={{ 1 if offline.gpgkey else 0 }}
gpgkey={{ offline.gpgkey | default('') }}
module_hotfixes=1                  # rhel8 모듈 충돌 회피(필요 시)
```

## 등록 절차(멱등)
1. 번들 복사/마운트(`unarchive`, `creates=`).
2. GPG 키 import(`rpm_key`, 멱등).
3. `.repo` 작성(template). 4. **다른 외부 repo 비활성**(`*.repo` enabled=0 또는 백업/이동).
5. `yum/dnf clean all && makecache`(로컬 한정). 6. 가용성 검증(`repoquery --repoid offline`).

## 검증
- manifest 의 각 패키지가 repo 에 존재 + sha256 일치 + (서명 검증).
- 누락/불일치 시 명확한 실패(어떤 패키지가 왜 없는지). 이 검증은 순수 함수로 분리해 단위테스트.

## 가드
- 설치 경로에서 **인터넷 0**. baseurl 외부(http(s)://*공인*) 금지. build 도구만 외부 가정(분리 실행).
