# RMQ 연동 규격 (VCSM ↔ VCMM)

> 출처: "녹취(uVCS) RMQ 연동 규격서 v1.0.0" + "녹취(uVCS) 설계서 2.3~2.5".
> 담당 에이전트: `rmq-monitor`(검증), `scenario`(기대값), `validator`(정합성).
> 시뮬레이터는 실 서버만 시험하므로 RMQ 는 **패시브 모니터**(shadow consumer)로 관찰/검증한다.

## 1. 전송/구조
- **Protocol**: AMQP (RabbitMQ). VCSM 에 설치된 RabbitMQ Server 가 각 Process 로 라우팅.
- **Direction**: VCSM ↔ VCMM.
- **포맷**: JSON. 최상위 `header`(필수) + `body`(선택, 단순 결과 메시지는 생략 가능).

## 2. 헤더 (`header`)
| 순번 | Key | Type | 필수 | 설명 |
|---|---|---|---|---|
| 1 | `type` | String | M | 메시지 타입 |
| 2 | `callId` | String | O | 호 처리 메시지가 아닌 경우 생략 가능 |
| 3 | `transactionId` | String/Integer | M | Transaction ID |
| 4 | `msgFrom` | String | M | 응답 수신 큐 이름 (예: `VCMM_0`, `VCSM_VCMM`) |
| 5 | `trxType` | Bool/Int | O | `0`=Notification(Indi), `1`=Req/Res |
| 6 | `reasonCode` | Integer | M(설계서 N) | 결과 코드 |
| 7 | `reason` | String | M(설계서 N) | 결과 메시지 |

예시:
```json
{
  "header": {
    "type": "recording_start_res",
    "callId": "call_eiwjf333",
    "transactionId": 1899868767744,
    "msgFrom": "VCMM_0",
    "trxType": 1,
    "reasonCode": 4000,
    "reason": "CREATE CALLPACKET FAIL"
  },
  "body": { "audio_extension": "amr" }
}
```

## 3. 에러 코드
| Reason Code | Reason | 설명 |
|---|---|---|
| `0` | 성공 | |
| `-1` | 실패 | |
| `-2` | Timeout | |
| `-3` | Wrong Param | 필수 파라미터가 없거나 값이 잘못된 경우 |
| `-4` | Already Exist | 이미 등록되어 중복 불가 / 동일 operation 구동 중 |

> 주의: 설계서 예시에는 `reasonCode: 4000`(CREATE CALLPACKET FAIL) 같은 확장 코드도 등장.
> 검증기는 `0`=성공 기준으로 판정하되, **음수/4xxx 확장 코드는 로그/리포트에 원문 보존**한다.

## 4. 메시지별 Body

### 4.1 VCMM Login — `login_req` (VCMM→VCSM)
VCMM 프로세스 기동 시 VCSM 으로 Login 전송.
| 순번 | Key | Type | 필수 | 설명 |
|---|---|---|---|---|
| 1 | `vcmm_id` | Integer | M | VCMM id : `0 ~ 5` |
```json
{ "body": { "vcmm_id": 1 } }
```

### 4.2 `login_res` (VCSM→VCMM)
Body 없음. `{ "body": {} }`

### 4.3 Heartbeat — `heartbeat_req` (VCMM→VCSM)
VCMM 이 자신의 상태(채널 수 등)를 주기적으로 전송. 기동 시 현재 상태 전송.
| 순번 | Key | Type | 필수 | 설명 |
|---|---|---|---|---|
| 1 | `vcmm_id` | Integer | M | VCMM id : `0 ~ 5` |
| 2 | `session_total` | Integer | M | 채널 총 수 |
| 3 | `session_idle` | Integer | M | IDLE 채널 수 |
```json
{ "body": { "vcmm_id": 0, "session_total": 2000, "session_idle": 1268 } }
```

### 4.4 Recording Start — `recording_start_req` (VCSM→VCMM)
SDP 의 RTP 정보를 기반으로 녹취 시작.
| 순번 | Key | Type | 필수 | 설명 |
|---|---|---|---|---|
| 1 | `from_no` | String | M | 발신번호 |
| 2 | `to_no` | String | M | 착신번호 |
| 3 | `outbound` | Integer | M | `INBOUND=0`, `OUTBOUND=1`, `INBOUND_ONLY=2` |
| 4 | `save_file_name` | String | M | 저장 file 명 (확장자 제외) |
| 5 | `service_type` | String | M | `IMS` / `MCPTT` |
| 6 | `conference_id` | Integer | O | 회의 통화 ID (아니면 NULL) |
| 7 | `sdp` | String | O | INVITE 수신 SDP. NO SDP 인 경우 NULL → Error 전송 |
```json
{
  "body": {
    "from_no": "01011113333",
    "to_no": "01012341234",
    "outbound": 0,
    "service_type": "IMS",
    "sdp": "v=0\r\no=01011113333 1163 1617 IN IP4 192.168.5.72\r\ns=Talk\r\nc=IN IP4 192.168.5.72\r\nt=0 0\r\nm=audio 7078 RTP/AVP 96 101\r\na=rtpmap:96 AMR-WB/16000\r\na=fmtp:96 octet-align=1\r\na=rtpmap:101 telephone-event/16000\r\n",
    "save_file_name": "I-J92r1BSxGD@INBOUND_01011113333_2020-02-03 17:09:50"
  }
}
```

### 4.5 `recording_start_res` (VCMM→VCSM)
| 순번 | Key | Type | 필수 | 설명 |
|---|---|---|---|---|
| 1 | `audio_extension` | String | O | `amr`, `awb` |
| 2 | `video_extension` | String | O | `h264` |
| 3 | `sdp` | String | O | `service_type=MCPTT` 인 경우 **필수** 전달 |
```json
{ "body": { "audio_extension": "amr", "video_extension": "h264" } }
```

### 4.6 Recording Stop — `recording_stop_req` (VCSM→VCMM)
| 순번 | Key | Type | 필수 | 설명 |
|---|---|---|---|---|
| 1 | `from_no` | String | M | 발신번호 |
| 2 | `to_no` | String | M | 착신번호 |
```json
{ "body": { "from_no": "01012341234", "to_no": "01022223333" } }
```

### 4.7 `recording_stop_res` (VCMM→VCSM)
Body 없음. `{ "body": {} }`

## 5. 검증기(validator/rmq-monitor) 체크리스트
- header 필수 필드 존재 및 타입.
- `recording_start_req.save_file_name` 이 실제 생성 파일명(확장자 제외)과 일치.
- `outbound`/`service_type`/`from_no`/`to_no` 가 시나리오 주입값과 일치.
- start→res→(media)→stop→res 순서/타이밍, `transactionId` 매칭.
- `reasonCode` 가 시나리오 기대값과 일치 (정상=0, NO-SDP=error).
