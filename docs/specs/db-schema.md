# DB 규격 (uVCS Database)

> 출처: "녹취(uVCS) Database 규격서 v1.0.0".
> 담당 에이전트: `validator`(DB 정합성 검증), `platform`(DB client).
> 시뮬레이터는 SUT 의 DB 를 **읽기 전용**으로 조회하여 검증한다 (쓰기 금지).

## 1. 호 정보 — `call_session` table
| 이름 | 타입 | PK | AI | FK | NOT NULL | 설명 |
|---|---|---|---|---|---|---|
| `SIP_CALLID` | varchar(n) | o | | | o | sip call ID |
| `CALLER_MDN` | varchar(n) | | | | O | caller mdn |
| `CALLEE_MDN` | varchar(n) | | | | O | callee mdn |
| `CREATE_TIME` | datetime | | | | O | 호 생성시간 |
| `END_TIME` | datetime | | | | | 호 종료시간 |
| `DURATION_TIME` | time | | | | | 호 유지시간 |
| `SERVICE_TYPE` | varchar(n) | | | | | `IMS` / `MCPTT` |
| `RECORD_TYPE` | varchar(n) | | | | | RECORD 유형: 음성 / 영상 |
| `CALL_TYPE` | varchar(n) | | | | | 호 유형: 개별 / 그룹 |

## 2. 녹취 파일 — `record_file` table
| 이름 | 타입 | PK | AI | FK | NOT NULL | 설명 |
|---|---|---|---|---|---|---|
| `ID` | int(n) | o | o | | o | id |
| `SIP_CALLID` | varchar(n) | | | o | o | sip call ID |
| `FTEL` | varchar(n) | | | | | 국번 |
| `ETEL` | varchar(n) | | | | | 전화번호 |
| `CALL_TYPE` | varchar(n) | | | | | `IMS` / `MCPTT` |
| `RECORD_TYPE` | varchar(n) | | | | | `AUDIO` / `VIDEO` / `AUDIO_VIDEO` |
| `AUDIO_EXTENSION` | varchar(n) | | | | | `amr` / `awb` |
| `VIDEO_EXTENSION` | varchar(n) | | | | | `h264` |
| `CREATE_TIME` | datetime | | | | o | 시작시간 |
| `END_TIME` | datetime | | | | o | 종료시간 |
| `DURATION_TIME` | time | | | | o | 재생시간 |
| `FILE_NAME` | varchar(n) | | | | o | 파일 이름 |
| `REASON_CODE` | int(n) | | | | | 파일 저장 시도 시 전달받은 ReasonCode |
| `REASON_STR` | varchar(n) | | | | | 파일 저장 시도 시 전달받은 Reason |
| `FILE_STATUS` | int(n) | | | | | 파일 처리 상태 |

### `FILE_STATUS` 값
| 값 | 의미 |
|---|---|
| `0` | 파일 저장 중 |
| `1` | 파일 부분 저장 |
| `2` | 파일 저장 완료 |
| `-1` | 파일 저장 실패 |

## 3. 검증기 체크리스트
- 호 발생 시 `call_session` 1행 생성, `SIP_CALLID` = 주입 Call-ID.
- `CALLER_MDN/CALLEE_MDN` = 주입 from/to. `SERVICE_TYPE` = 시나리오(IMS/MCPTT).
- 종료 시 `END_TIME`/`DURATION_TIME` 채워짐. `DURATION = END - CREATE` 근사 일치.
- `record_file.FILE_NAME` 이 실제 파일시스템 파일명과 일치, 확장자/`AUDIO_EXTENSION` 정합.
- 정상 종료 시 `FILE_STATUS=2`(완료). 손실/에러 시나리오는 기대 status 와 비교.
- `record_file.SIP_CALLID` → `call_session.SIP_CALLID` FK 관계 일치.

## 4. 즉석재생 연계 (참고)
편리한 검색/재생을 위한 웹 기반 즉석재생기는 `call_session.sipCallId` ↔ `record_file.call_id`(SIP_CALLID)
조인으로 호↔파일을 연결한다. (시뮬레이터 검증 시 동일 조인 로직 사용)
