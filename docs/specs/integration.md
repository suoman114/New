# 실 서버 통합시험 가이드

> 지금까지 모든 모듈은 오프라인(인메모리/tmp)으로 검증되었다. 이 문서는 실제 uVCS
> (MariaDB `TBL_RECORD_INFO` / RabbitMQ / 램디스크·NAS)에 붙여 통합시험하는 절차다.
> 모든 연동은 **graceful degrade** — 미연결 시 해당 검증만 건너뛰고 시뮬레이터는 계속 동작한다.

## 1. 접속정보 (환경변수 override)
비밀정보는 `config/sim.yaml` 에 두지 않고 환경변수로 주입한다(없으면 yaml 기본값).

| 환경변수 | 의미 | 기본 |
|---|---|---|
| `UVCS_DB_HOST` / `UVCS_DB_PORT` | MariaDB host/port | 127.0.0.1 / 3306 |
| `UVCS_DB_USER` / `UVCS_DB_PASSWORD` | DB 계정(read-only 권장) | readonly / "" |
| `UVCS_DB_NAME` | DB 이름 | uvcs |
| `UVCS_RMQ_ENABLED` | RMQ 모니터 on/off | true |
| `UVCS_RMQ_HOST` / `UVCS_RMQ_PORT` | RabbitMQ host/port | 127.0.0.1 / 5672 |
| `UVCS_RMQ_USER` / `UVCS_RMQ_PASSWORD` | RMQ 계정 | guest / guest |
| `UVCS_RMQ_EXCHANGE` | tap 대상 exchange | "" |
| `UVCS_REC_RAMDISK` / `UVCS_REC_NAS` | 녹취 파일 루트 | /home/vcs/ramdisk · /home/vcs/nas |
| `UVCS_INJECT_MODE` | tapper_udp / pcap_mirror | tapper_udp |

> DB 계정은 **읽기 전용**을 사용한다(검증기는 SELECT 만; `DbConfig.readonly=True` 안전장치).

## 2. 연동 상태 점검
```
GET /api/integration/health
→ { "db": {"reachable": true/false, ...},
    "rmq": {"enabled": ..., "tracked_calls": N},
    "fs": {"active_root": "/home/vcs/ramdisk"|null, "ramdisk": bool, "nas": bool},
    "inject_mode": "tapper_udp" }
```
대시보드 상단 칩(DB/RMQ/FS)으로도 표시된다.

## 3. 통합 검증 흐름
1. `POST /api/run {scenario_id}` — Tapper UDP 로 SIP+RTP 주입(실 VCTP 하류 = VCSM:10000/VCMM:10001+).
2. (선택) RMQ shadow monitor 가 VCSM/VCMC↔VCMM 메시지를 관찰해 호별 트래커에 누적.
3. 호 종료 후 `POST /api/validate?session_id=...`:
   - **파일**: `UVCS_REC_*` 하위에서 기대 파일명 정규식 매칭 + magic + 골든 byte 비교.
   - **DB**: `TBL_RECORD_INFO` 조회 → FILE_STATUS/AUDIO_EXTENSION/그룹ID/파일명 정합.
   - **오디오**: 송출 패킷 → (손실 timestamp-gap 채움) 골든 재구성 vs 서버 저장 파일.
   - **RMQ**: 모니터가 해당 호를 관찰했으면 floor 시퀀스/txn 페어링/에러코드 검증 합류.
   - 결과는 `ValidationResult` 로 저장되고 `FlowEvent(channel=VALIDATION)` 발행 → 대시보드 리포트.

## 4. 미연결 시 동작(스모크)
- DB 연결 실패 → DB 검증 스킵(`reachable=false`), 나머지 진행.
- RMQ 비활성/연결 실패 → RMQ 검증 스킵(모니터 disabled).
- 파일 루트 부재 → 파일/오디오 검증 스킵(기대 파일 미발견).
- 즉, **부분 연동만으로도** 가능한 검증을 수행하고 리포트한다.

## 5. 주의
- 시뮬레이터는 SUT 와 동일 host 또는 원격 모두 지원. 원격이면 램디스크/NAS 를 마운트하거나
  파일 접근 경로를 `UVCS_REC_*` 로 지정한다.
- `pcap_mirror` 모드(실 VCTP 까지 시험)는 2차 — 현재 기본은 `tapper_udp`(VCTP 우회 직접 주입).
