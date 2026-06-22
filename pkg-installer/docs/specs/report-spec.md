# Spec: 설치 완료 보고서 (Completion Report)

> pkg-report 권위 출처. 보고서 스키마/섹션/렌더링 규격.

## 산출물
- 경로: `pkg-installer/reports/{run_id}/report.{html,md,pdf}`
- 포맷: HTML(기본), Markdown(항상), PDF(옵션·폐쇄망 가용 시).

## 입력 모델 (ReportModel = pkg-platform.models)
- `RunState`(stage 진행/호스트별 status/통계, 시작·종료·소요)
- `ValidationResult[]`(호스트별, validation-spec.md)
- `facts`(OS/커널/패키지 버전, changed 항목)
- 실행 메타(run_id, os_target, profile, options, offline manifest 참조)

## 섹션 (순서 고정)
1. **표지 / 요약**
   - run_id, 생성일시, os_target, profile, 대상 호스트 수
   - **전체 판정**: `SUCCESS`/`FAILED` (= validate FAIL 또는 stage failed 하나라도 있으면 FAILED)
   - 총 소요시간, ok/changed/failed 합계
2. **단계별 결과(stage summary)**: stage별 state/ok/changed/failed/소요시간(표).
3. **호스트별 상세**(호스트마다):
   - 설치/부팅 커널 버전, 설치 패키지 버전 목록, 변경 항목(changed)
   - 검증 결과 표(check id / status / expected / actual)
4. **폐쇄망 & 안전**: 사용한 offline 미러/번들(manifest), 외부 repo 비활성 여부, 재부팅 수행 여부.
5. **실패/경고 모음**: FAIL/WARN 항목 + 드릴다운 참조(`event_id` → `/api/runs/{run_id}/events/{event_id}/logs`).
6. **부록**: 실행 옵션 전문, 프로파일 패키지 목록.

## 표지 JSON(메타, `GET /api/runs/{run_id}/report`)
```json
{
  "run_id": "r-20260622-001",
  "generated": "2026-06-22T01:23:45Z",
  "os_target": "rhel8",
  "profile": "web",
  "hosts": 3,
  "overall": "SUCCESS",
  "duration_sec": 412,
  "totals": {"ok": 120, "changed": 28, "failed": 0},
  "formats": ["html", "md"]
}
```

## 렌더링/규칙
- jinja2 템플릿(`templates/report.html.j2`, `report.md.j2`).
- 보고서는 **재생성 가능**(동일 데이터 → 동일 출력), 외부 네트워크 의존 금지.
- 색상/뱃지: SUCCESS=green, FAILED=red, WARN=amber. FAIL 항목은 상단 요약에도 노출.
