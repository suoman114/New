# As-Built 관찰 결과 (실 운영 로그 분석)

> 출처: 실 운영 로그 4종(`vctp0_2`, `vcsm_2`, `vcmm0`, `vcmc`, 2026-06-20, LTE-R 철도 MCPTT — 부산 Humetro).
> **이 문서가 설계서(v1.0.0)보다 우선한다.** 시뮬레이터는 여기 기술된 **실제 동작**에 맞춰 구현/검증한다.
> 설계서와 충돌 시 본 문서 기준. (설계서는 초기 IMS 가정, 실제는 MCPTT 중심으로 진화)

## 0. 가장 중요한 발견 (설계서 대비 델타)
| 항목 | 설계서 v1.0.0 | 실제(로그) |
|---|---|---|
| 주 트래픽 | IMS 중심 | **MCPTT 중심** (로그상 IMS:0, MCPTT:28~30 동시호) |
| 프로세스 | VCTP/VCSM/VCMM | **+ VCMC** (MCPTT 시그널링/DB 브레인) 추가 |
| transactionId | Integer | **UUID 문자열** |
| 성공 reasonCode | `0` | **`2000`** (`0`은 요청/미결 상태) |
| 에러코드 | -1~-4 | **3001**(Callee SDP is null), **4001**(Session is not exist) |
| heartbeat | `heartbeat_req`, `vcmm_id`, total 2000 | **`heartbeat_indi`**, `vcmmId`, **total 16000** |
| start_req body | 단일 `save_file_name`, 단일 `sdp` | **caller/callee 분리**: `caller_save_file_name`/`callee_save_file_name`, `caller_sdp`/`callee_sdp`, `record_time` 추가 |
| 추가 메시지 | 없음 | **`recording_update`**(ReINVITE 중 SDP 변경), **`recording_change`**(MCPTT floor TAKEN/IDLE) |
| DB 테이블 | `call_session`, `record_file` | 실제 **`TBL_RECORD_INFO`** (MariaDB/Hibernate, 컬럼 다수 추가) |
| 파일명 | `{I/M}_{CALLID}_{MDN}_{HHMMSSsss}` | `{I/M}_{CALLID}_{MDN}_{GROUPID}_{YYYYMMDDHHMMSS}_{FILE_INDEX}` |
| 저장 경로 | `~/REC/...` | **`/home/vcs/ramdisk/...`** (램디스크) → NAS 이관, 진행중 **`.awb.ing`** |
| 주입(VCTP) | UDP 포워딩 | 실제는 **NIC 미러링/libpcap 캡처**(ens*) + fragment 재조립 |

## 1. 프로세스 역할 (as-built)
- **VCTP** (`NetworkPacketListener`, `DumpPacketTask`): NIC(ens1f0 등) **libpcap 캡처** → IP fragment 재조립 →
  `send SIP message to VCSM`(소스 IP:port, length, mapSize, 첫 줄). SIP 전 메서드 포워딩.
  포트: IMS SIP `5060`, MCPTT SIP `5080`. `mapSize` = fragment 재조립 맵 크기.
- **VCSM** (`SessionManager`, `RecordHandler`, Netty `nioEventLoopGroup`, C3P0/Hibernate):
  **IMS 시그널링 브레인**. 초당 `callSession count` 로그. `[domain] or [MSRP] is contains` 필터.
  IMS 호의 `recording_start/stop/update_req` 를 VCMM 으로 송신, `TBL_RECORD_INFO` 직접 기록.
- **VCMM** (`VCMM_0`, `McpttApplicationHandler`, `VcsRecordFile`): **미디어 캡처/파일 저장**.
  RTP 수신→`.awb` 저장(램디스크). MCPTT **floor 처리**(Taken→큐 clear). `heartbeat_indi` 송신.
  MCPTT 시 floor 변화를 `recording_change_req` 로 **VCMC** 에 통지.
- **VCMC** (`OwnRegisterManager`, `HealthRegiManager`, `RmqRecordChangeReq`, `HibernateRecordManager`,
  `MariaDBSender`, `RecordCompleteHandler`): **MCPTT 시그널링/DB 브레인**.
  MCPTT 녹취 클라이언트로 SIP **REGISTER**(OWN/HEALTH), `recording_change` 처리,
  `TBL_RECORD_INFO` INSERT/UPDATE, 완료 처리.

### 메시지 경로 요약
- **IMS**: VCTP→VCSM(SIP). VCSM ⇄ VCMM (`recording_start/update/stop`). VCSM→DB.
- **MCPTT**: VCMC(REGISTER로 망 가입) + VCTP→(VCSM/VCMM). VCMM ⇄ VCMC (`recording_change` floor).
  VCMC→DB. 즉 MCPTT 는 **floor 단위(talk spurt)로 파일 1개**씩 생성.

## 2. RMQ 메시지 (as-built, JSON)
공통 헤더: `type`, `callId`, `transactionId`(UUID), `msgFrom`(`VCSM`/`VCMM_0`/`VCMC`),
`trxType`(`0`=indi/notify, `1`=req/res), `reasonCode`, `reason`.

reasonCode: `0`(요청/미결) · **`2000`=Success** · `3001`="Callee SDP is null" · `4001`="Session is not exist."

### 2.1 `heartbeat_indi` (VCMM_0 → , trxType 0)
```json
{ "header": { "type":"heartbeat_indi", "callId":"<uuid>", "transactionId":"<uuid>",
              "msgFrom":"VCMM_0", "trxType":0, "reasonCode":2000, "reason":"Success" },
  "body": { "vcmmId":0, "session_total":16000, "session_idle":15972 } }
```

### 2.2 `recording_start_req` (IMS: VCSM→VCMM / MCPTT: VCMC→VCMM, trxType 1)
```json
{ "header": { "type":"recording_start_req", "callId":"1339172425_809000108@104.240.17.77",
              "transactionId":"<uuid>", "msgFrom":"VCSM", "trxType":1, "reasonCode":0 },
  "body": {
    "from_no":"+821358512668", "to_no":"01358512046", "outbound":0, "service_type":"IMS",
    "record_time":"2026/06/20/01",
    "caller_save_file_name":"I_1339172425_809000108@104.240.17.77_01358512668_01358512046_20260620015023",
    "callee_save_file_name":"I_1339172425_809000108@104.240.17.77_01358512046_01358512668_20260620015023",
    "caller_sdp":"v=0...m=audio 50020 RTP/AVP 98 97 101 100 99 102...a=rtpmap:98 AMR-WB/16000/1...",
    "callee_sdp":"v=0...m=audio 50042 RTP/AVP 97 99...a=rtpmap:97 AMR-WB/16000/1..."
  } }
```
- IMS 는 **caller/callee 양 레그를 각각 파일**로 녹취 → save_file_name/sdp 2개.
- `record_time` = `YYYY/MM/DD/HH` (디렉토리 산출용).

### 2.3 `recording_start_res` (VCMM → , trxType 1)
- IMS: `{ "audio_extension":"awb" }`
- MCPTT: `{ "audio_extension":"awb", "sdp":"v=0...m=audio 30822 RTP/AVP 98...a=rtpmap:98 AMR-WB/16000/1\r\na=fmtp:98 mode-set=8; octet-align=1\r\na=recvonly\r\nm=application 30826 UDP MCPTT\r\n" }`
  - res SDP 가 **VCMM 의 RTP 수신 포트(recvonly)** 와 **MCPTT floor application 포트**를 알려줌.

### 2.4 `recording_update_req` / `_res` (ReINVITE 중 SDP 변경, VCSM→VCMM)
```json
req.body : { "file_index":2, "caller_sdp":"...sendonly...", "callee_sdp":"...recvonly..." }
res.body : { "audio_extension":"awb", "file_index":1, "record_result":2000, "record_reason":"Success", "fps":"0,0" }
```

### 2.5 `recording_stop_req` / `_res` (VCSM→VCMM)
```json
req.body : { "from_no":"+821358512668", "to_no":"01358512046" }   // trxType 0
res.body : {}                                                     // reasonCode 2000
```

### 2.6 `recording_change_req` / `_res` (MCPTT floor, VCMM→VCMC, trxType 0)
```json
req.body : { "type":"TAKEN", "caller_mdn":"tel:+82585102802", "audio_extension":"awb" }  // TAKEN | IDLE
res.body : { "type":"TAKEN", "file_index":5008,
             "save_file_name":"M_...recorder1_-11401_..._585102802_98152020001_20260620000036_5008" }
```
- `TAKEN` = 누군가 floor 획득(발언 시작) → 새 파일. `IDLE` = floor 반납(발언 종료) → 파일 종료.
- VCMC 가 `file_index`(=파일 시퀀스)와 최종 `save_file_name` 을 확정해 응답.

## 3. 파일명 / 경로 (as-built)
### 파일명
- IMS(레그별): `I_{SIP_CALLID}_{from}_{to}_{YYYYMMDDHHMMSS}.{awb|amr}`
- MCPTT(talk spurt별): `M_{SIP_CALLID}_{talkerMDN}_{MCPTT_GROUP_ID}_{YYYYMMDDHHMMSS}_{FILE_INDEX}.{awb|amr}`
  - 예: `M_tb2bua-tpf_cfua_recorder1_-11401_opf_ob2bua-<hex>_585102802_98152020001_20260620000036_5008.awb`
  - `FILE_INDEX`(5007,5008,…)는 발언 차례마다 증가. talkerMDN/groupId 로 그룹콜 멤버 식별.

### 경로 & 상태
- 진행중: `/home/vcs/ramdisk/{IMS|MCPTT}/{VOICE|VIDEO|CONV}/{YYYY}/{MM}/{DD}/{HH}/<name>.awb.ing`
- 완료 시: `.ing` 제거 + **NAS 이관**. (`NAS monitoring`, `AlarmFile`)
- `record_time`/dir 날짜는 호 시작 기준일 수 있어 현재시각과 다를 수 있음(검증 시 허용범위 고려).

## 4. DB — `TBL_RECORD_INFO` (MariaDB/Hibernate, as-built)
INSERT(저장 시작, `FILE_STATUS=0`) → UPDATE(완료, `FILE_STATUS=2`, END_TIME/DURATION/REASON 채움).
> ✅ **실 서버 `SHOW COLUMNS` 로 확정된 스키마**(192.168.7.64, DB `VCSM`). 로그상 `REASON_CORD`(오타)로
> 보였으나 실제 컬럼명은 **`REASON_CODE`**. 또한 `FTEL`/`ETEL`/`CALL_TYPE` 컬럼이 실재한다.

| 컬럼 | 예시/의미 |
|---|---|
| `SIP_CALLID` | 호 ID (PK 일부) |
| `FILE_INDEX` | 파일 시퀀스 (PK 일부, MCPTT talk spurt 별) |
| `FTEL` | 발신 국번/번호 |
| `ETEL` | 착신 전화번호 |
| `CALL_TYPE` | `IMS` / `MCPTT` (호 종류) |
| `RECORD_TYPE` | `AUDIO` / `VIDEO` / `AUDIO_VIDEO` (초기 null → 확정) |
| `AUDIO_EXTENSION` | `awb`/`amr` |
| `VIDEO_EXTENSION` | `h264` (영상) |
| `CREATE_TIME` / `END_TIME` | 시작/종료 |
| `DURATION_TIME` | `00:00:00.668` (MariaDB `TIME` → 드라이버에서 `timedelta`) |
| `CALLER_FILE_NAME` / `CALLEE_FILE_NAME` | 레그별 파일명(MCPTT 는 caller만) |
| `REASON_CODE` | 처리 결과코드 (0 → 2 완료) — **실 컬럼명** |
| `REASON_STR` | `SUCCESS` |
| `FILE_STATUS` | `0`저장중 / `1`부분 / `2`완료 / `-1`실패 |
| `MCPTT_GROUP_ID` | `98152020001` |
| `GROUP_DISPLAY_NAME` / `USER_NAME` | 그룹/사용자 표시명 (로그는 EUC-KR mojibake) |
| `FPS` | `0,0` (영상 프레임율) |

> 검증기는 `record_file`(설계서) 대신 **`TBL_RECORD_INFO`** 를 조회한다. `FILE_STATUS` 전이(0→2),
> `REASON_CODE`·`MCPTT_GROUP_ID`·`FTEL`/`ETEL`/`CALL_TYPE` 등 실제 컬럼을 사용. DB 인코딩(EUC-KR) 주의.
> platform.db 는 `SELECT *` + **존재 컬럼만 매핑**(대소문자 무관)으로 스키마 차이에 내성을 갖는다.

## 5. VCMM Record State Machine & 통계 (검증 골든)
- 상태: `RECORD_READY → RECORDING → IDLE` (MCPTT floor TAKEN→RECORDING, IDLE→파일 종료).
- 완료 로그(검증 기준값):
  ```
  Recording statistics completed - file=..., firstPacket[seq=161, timestamp=480, ssrc=1195870476],
    lastPacket[seq=162, timestamp=800, ssrc=...], totalPackets=2, sidCount=0, droppedPackets=0, playTime=40ms
  ```
- "No packets recorded" : floor 잡았으나 RTP 미수신(빈 파일) 케이스 → 검증 시 분기.
- **validator 는 위 통계(seq 범위/ssrc/totalPackets/sidCount/droppedPackets/playTime)를 송출값과 대조**.

## 6. SIP / SDP (as-built)
- VCTP 가 포워딩하는 메서드(빈도순): `200 OK`, `OPTIONS`, `NOTIFY`, `UPDATE`, `SUBSCRIBE`, `REGISTER`,
  `401`, `INVITE`, `ACK`, `BYE`, `481`, `100`, `MESSAGE`, `180`, `408`.
  → sip-engine 은 INVITE/BYE 뿐 아니라 REGISTER/SUBSCRIBE/NOTIFY/UPDATE/OPTIONS/MESSAGE 도 생성·주입 가능해야 함.
- 도메인: IMS `ims.humetro.mnc031.mcc450.3gppnetwork.org`, MCPTT `ptt.humetro...3gppnetwork.org`.
- SDP(실제): 다중 코덱(`AMR-WB/16000/1` 98·97, `AMR/8000/1` 100·101, `telephone-event` 99·102),
  `a=fmtp:.. octet-align=1;mode-change-capability=2;max-red=0`, `b=AS:41/RS:0/RR:2500`,
  `a=maxptime:240`, `a=ptime:20`, 방향 `sendrecv|sendonly|recvonly`.
- MCPTT 녹취용 SDP: `a=recvonly` + `m=application <port> UDP MCPTT`(floor 제어 채널).

## 7. 주입 방식에 대한 결론 (시뮬레이터 설계 반영)
- 실 VCTP 는 NIC 미러링/libpcap. 우리는 선택대로 **Tapper UDP 포워딩 모방**:
  시뮬레이터가 **VCTP 하류 역할**로 SIP→VCSM(:10000), RTP→VCMM(:10001~11000) 직접 주입(실 VCTP 우회).
- (옵션/2차) 실 VCTP 까지 시험하려면 **PCAP/NIC 미러 주입** 모드를 별도 제공.
- 주입 IP/port/transport 전부 config. SUT 가 램디스크/NAS/DB(MariaDB)에 접근하므로
  검증기는 **MariaDB(TBL_RECORD_INFO) + 램디스크/NAS 파일** 모두 접근 경로를 config 로 받는다.

## 8. 시나리오 우선순위 재조정 (실 환경 반영)
1. **MCPTT 그룹콜 + floor(TAKEN/IDLE) talk-spurt 녹취** ← 최우선(실 트래픽 대다수).
2. MCPTT 다중 발언자(파일 시퀀스 FILE_INDEX 증가) 검증.
3. recording_change/ recording_update(ReINVITE) 흐름.
4. IMS 양방향(caller/callee 분리 파일) 녹취.
5. 에러: Callee SDP null(3001), Session not exist(4001), No packets recorded.
6. 성능: heartbeat 기준 채널 총 16000 (확장 목표).
