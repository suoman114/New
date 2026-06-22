# SIP / SDP 규격

> 출처: "녹취(uVCS) 설계서 2.1 (Signal 처리) + 부록 1 (SDP)".
> 담당 에이전트: `sip-engine`(생성/파싱), `scenario`(기대값).

## 1. SIP 인터페이스 개요
- VCSM(Signal 모듈)은 Tapper 와 연동하여 수신한 **SIP 메시지 기반**으로 Recording 시작/종료.
- 지원: **IMS 녹취 호 처리**, **MCPTT 녹취 호 처리**.
- 시뮬레이터는 **Tapper 가 미러링한 SIP** 를 VCTP(UDP 10000)로 주입한다 (UA 양측 + 코어 시그널링 미러).

## 2. INVITE 샘플 (IMS, 설계서 2.1.3)
```
INVITE tel:01020950212;phone-context=sktims.net SIP/2.0
Call-ID: cdbd539377ca3bd91123ac90e99e7b59@113.217.242.196
CSeq: 1 INVITE
From: <sip:01020069012@sktims.net>;tag=ad6fc658
To: <tel:01020950212;phone-context=sktims.net>
Via: SIP/2.0/UDP 113.217.242.196:5060;branch=z9hG4bK-393530-9238f7f8095945b892fb62c7016703fe
Max-Forwards: 70
Contact: <sip:01020069012@113.217.242.196:5060>
Route: <sip:SCSM3-orig-tu021530753092-74@172.1.183.15:5067;lr>
P-Asserted-Identity: <sip:01020069012@sktims.net>
Session-Expires: 180;refresher=uac
Allow: INVITE,ACK,OPTIONS,CANCEL,BYE,UPDATE,INFO,REFER,NOTIFY,MESSAGE,PRACK
Supported: timer,100rel
User-Agent: TTA-VoLTE/2.0 SM-G955N/QL3 Device_Type/Android_Phone SKT
Accept-Contact: *;+g.3gpp.icsi-ref="urn%3Aurn-7%3A3gpp-service.ims.icsi.mmtel";require;explicit
P-Early-Media: supported
P-Access-Network-Info: 3GPP-E-UTRAN-FDD; utran-cell-id-3gpp=45005080a074a98b
P-Served-User: <sip:01020069012@sktims.net>;regstate=reg;sescase=orig
P-Charging-Vector: icid-value="abc9.sktims.net-s-222a650000000db7"
P-Asserted-Service: urn:urn-7:3gpp-service.ims.icsi.mmtel
Content-Type: application/sdp
Content-Length: 248

v=0
o=- 0 0 IN IP4 113.217.242.196
s=-
t=0 0
m=audio 20060 RTP/AVP 100 103 98
c=IN IP4 113.217.242.196
a=rtpmap:100 AMR-WB/16000
a=rtpmap:98 AMR /8000
a=ptime:20
a=rtpmap:103 telephone-event/16000
a=fmtp:100 mode-set=8; octet-align=1
a=fmtp:103 0-15
a=sendrecv
```

- `sip-engine` 은 위 샘플을 **템플릿**으로 from/to/Call-ID/Via/branch/tag/SDP 를 시나리오별 치환.
- 호 흐름(권장 기본): `INVITE → 100 Trying → 180 Ringing → 200 OK → ACK → (media) → BYE → 200 OK`.
  (Tapper 미러링이므로 양방향 메시지를 모두 주입 가능해야 함. 최소셋은 INVITE/200/ACK/BYE.)
- MCPTT 는 호 셋업 메시지/헤더가 다를 수 있으므로 `service_type=MCPTT` 분기 템플릿을 둔다.

## 3. SDP 파싱 규칙 (부록 1)

### 3.1 공통 (모든 코덱)
- `v=0` 이어야 한다.
- `c=` line 3번째 필드로 caller/callee IP 획득. (예: `c=IN IP4 10.160.254.57`)
  - IP4 는 `10.160.254.57/127` 처럼 **TTL** 이 붙을 수 있음. IP6 는 TTL 없음.
  - **Multicast 미고려**.
- `m=<media> <port> <proto> <fmt> ...`:
  - `port` 로 caller/callee port 획득.
  - `proto` 는 `RTP/AVP` 또는 `RTP/SAVP`.
  - `fmt` 는 payload type 목록.
- `a=rtpmap:{pt} <name>/<clock>` 으로 코덱 구분. 지원: **AMR-WB, AMR, H264**.

### 3.2 AMR / AMR-WB specific
- `a=rtpmap:<pt> <name>/<clock>[/<channels>]`
  - name: `AMR` 또는 `AMR-WB`.
  - clock: AMR=`8000`, AMR-WB=`16000` (고정).
  - channels: optional, range `{1..6}`, 없으면 default `1`.
- `a=fmtp:<pt> <params>` (예: `a=fmtp:100 octet-align=1;mode-set=8`)
  - **Interleaving 미지원**.
  - `mode-set` : 지원 mode 목록(콤마 구분). 예 `mode-set=2,3,7`.
  - `octet-align` : OA 모드 여부 판단(1=OA, 없으면 BE).

### 3.3 H264 specific (2차)
- `a=rtpmap:<pt> H264/90000`.
- `a=fmtp:<pt> profile-level-id=...; packetization-mode=...; sprop-parameter-sets=...`
  - packetization-mode: `0/none`=single NAL, `1`=Non-interleaved, `2`=Interleaved.
  - 상세는 `docs/specs/h264.md`.

## 4. 세션 관리 (설계서 2.5, 시뮬레이터 측 모델)
- 시뮬레이터는 **Call-ID 를 key** 로 한 세션맵을 유지(SUT 의 SIP Session Map 과 대응 검증).
- Caller 호 발생 시 세션 생성, 호 종료(BYE) 시 세션 삭제.
- 세션에는 from/to MDN, SDP(코덱/IP/port), 송출 RTP 통계, 기대 파일명을 보관.
