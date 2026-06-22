# RTP & AMR-WB Payload / File 변환 규격

> 출처: "녹취(uVCS) 설계서 부록 2~7".
> 담당 에이전트: `rtp-media`(송출=정방향), `validator`(검증=역방향 재구성).
> 핵심: 시뮬레이터는 원본 음원을 **AMR-WB RTP 로 패킷화하여 송출**하고,
> 검증기는 서버가 저장한 `.awb/.amr` 파일을 부록 5 의사코드대로 **재구성하여 비교**한다.

## 1. RTP Header (RFC3550, 부록 2) — 검증 포인트
- `V=2` 이어야 한다.
- `P` bit 설정 시 마지막 octet 값 = padding bytes 수(무시).
- `X` bit 설정 시 header extension 1개 포함 → payload 해석 시 고려.
- `PT` = SDP nego payload type 과 동일.
- `SSRC` = 이전 packet 과 동일.
- `sequence number` 확인 → decoding 순서로 buffering.
- `timestamp` 증가분 확인 → **packet 유실 및 녹취 시 추가해야 할 packet 수 산출** (묵음 채움 핵심).

## 2. AMR / AMR-WB RTP Payload (부록 3)
구조: **payload header → table of contents(ToC) → speech data**.

### 2.1 payload header
- BE(Bandwidth-Efficient) / OA(Octet-Aligned) 모드에 따라 구성 상이.
- 이 field 는 실제 AMR File Storage 변환 시 **무시**되는 bit.
- OA 모드에서 **interleaving 미지원**.

> 구현: `backend/sim/rtp/amrwb.py` 에 **OA + BE 양쪽** 패킷화/파싱 구현.
> OA: `[CMR byte][ToC byte…][speech bytes…]`. BE: `CMR(4) + ToC(6×n) + speech bits` 연속 bitstream(끝 0 padding).
> `packetize(frames, octet_align=...)` / `parse(payload, octet_align=...)` 로 SDP nego(octet-align 유무) 반영.
> **파일 storage 포맷은 모드 무관 동일**하므로 BE/OA 골든 재구성 결과가 일치한다.

### 2.2 ToC (table of contents)
- 하나의 RTP packet 은 1개 이상 speech frame → n개 연속 ToC bits.
- 각 ToC: `F`(1bit) `FT`(4bit) `Q`(1bit) [BE], OA 모드는 byte 정렬.
  - `F`: 마지막 frame 이면 `0`.
  - `FT`: Frame Type index (speech coding mode / SID / NO_DATA).
  - `Q`: `0`이면 심각한 frame 손상(단 drop 보다 그대로 사용이 품질에 유리).

### 2.3 speech data
- ToC 순서대로 연속적 speech frame data.
- `FT=14 or 15` 인 경우 speech frame 없음.

## 3. File Storage (부록 4)
- 확장자: AMR=`.amr`, AMR-WB=`awb`(설계서 표기; 파일명 규칙은 `.awb`).
- 구조: Header + n speech frames.
- **Magic number** (`\n` 필수 포함):
  - Single-channel: `#!AMR\n` (`0x2321414d520a`), `#!AMR-WB\n` (`0x2321414d522d57420a`).
  - Multi-channel: `#!AMR_MC1.0\n`, `#!AMR-WB_MC1.0\n` + 32-bit channel description(CHAN=채널수, reserved=0).
- Speech frame: Frame header(ToC 의 FT,Q 유지, 나머지 0) + speech bits(부록 6 길이, 필요시 0 padding).
- non-speech 구간의 SID update 사이 frame 및 NO_DATA/SPEECH_LOST packet → **묵음 packet 으로 변환**(부록 7, `silence-packets.md`).

## 4. Speech frame 길이 (부록 6)
```
SPEECHBITS (bits, FT 순):
  AMR    : (95, 103, 118, 134, 148, 159, 204, 244, 39)        # FT 0..7 + SID(8)=39
  AMR-WB : (132, 177, 253, 285, 317, 365, 397, 461, 477, 40)  # FT 0..8 + SID(9)=40
MAX_MODES = { AMR: 8, AMR-WB: 9 }   # speech frame(SID 포함) range index
NODATA    = { AMR: 15, AMR-WB: 14 } # SPEECH_LOST, NO_DATA frame range
SAMPLES   = { AMR: 160, AMR-WB: 320 } # 20ms frame 당 sample 수 (8k/16k)
```

## 5. 부록 5 의사코드 (검증기 = 역방향 재구성의 기준)

### 5.1 SDP 분석하여 초기화
```text
Read SDP
    // a=rtpmap:100 AMR-WB/16000/1 → codec, channel
    zWB   = exist(AMR-WB) ? 1 : exist(AMR) ? 0 : -1   // -1: not support
    nCHAN = exist(channel field) ? channel field : 1  // range 1..6
    // a=fmtp:100 mode-set=8; octet-align=1 → 주요 parameter
    zOctetAlign = exist(octet-align=1) ? true : false
    nMaxModeset = exist(mode-set) ? max(mode-set list) : (zWB ? 9 : 8)
    // 고정 값
    SPEECHBITS = { AMR:(95,103,118,134,148,159,204,244,39),
                   AMR-WB:(132,177,253,285,317,365,397,461,477,40) }
    MAX_MODES  = { AMR:8, AMR-WB:9 }
    NODATA     = { AMR:15, AMR-WB:14 }
    SAMPLES    = { AMR:160, AMR-WB:320 }
    // octet-align 에 따른 고정 값
    nPAYLOAD_HDR_BIT = zOctetAlign ? 8 : 4
    nTOCBIT          = zOctetAlign ? 8 : 6
    nOLDTIMESTAMP = 0
    bSIDFRAME     = 0
    // File Storage Header 기록
    IF nCHAN == 1
        magick = zWB ? "#!AMR-WB\n" : "#!AMR\n"
    ELSE
        magick = zWB ? "#!AMR-WB_MC1.0\n" : "#!AMR_MC1.0\n"
        magick += nCHAN (32bit integer bit string)
    WRITE magick
```

### 5.2 RTP packet 단위로 speech frame 기록
> RTP Packet 은 sequence number 순으로 정렬되어 있다고 가정.
```text
Read RTP Payload until end packet
    // RTP header 유효성 검사는 완료 가정
    nNOWTIMESTAMP = timestamp of RTP header
    // payload header 는 storage file 과 무관 → skip
    Ignore nPAYLOAD_HDR_BIT
    // n개의 ToC: last entry 까지 ToC list 저장
    WHILE (1)
        // F, R bit 만 사용. ByteAlign: 8bit 배수로 0 padding
        t = ByteAlign( READ(nTOCBIT) )
        toc.append( t & 0x7C )
        IF (t & 0x80) == 0
            Break
    // speech frame: ToC entry 만큼 연속 bit stream
    FOR t in toc
        FT = t >> 3
        IF FT <= MAX_MODES[zWB]
            zSPEECH_DATA = ByteAlign( read( SPEECHBITS[zWB][FT] ) )
            // SID packet → 묵음 패킷 변환
            IF FT == MAX_MODES[zWB]
                IF bSIDFRAME == 0
                    bSIDFRAME = 1
                    nOLDTIMESTAMP = nNOWTIMESTAMP
                    write_mute(count: 1, zWB, nMaxModeset)
                ELSE
                    write_mute( count: (nNOWTIMESTAMP - nOLDTIMESTAMP)/SAMPLES[zWB], zWB, nMaxModeset )
                    nOLDTIMESTAMP = nNOWTIMESTAMP
            // 일반 speech frame
            ELIF FT < MAX_MODES[zWB]
                IF bSIDFRAME == 1
                    WRITE t + zSPEECH_DATA
                    nOLDTIMESTAMP = 0
                    bSIDFRAME = 0
        // SPEECH_LOST / NO_DATA → 1개 묵음 패킷
        ELIF FT >= NODATA[zWB]
            write_mute(count: 1, zWB, nMaxModeset)
```

## 6. rtp-media (정방향 송출) 요구
- 원본 음원(PCM/WAV) → AMR-WB encode(20ms frame) → ToC + speech data 패킷화 → RTP 헤더 부착.
- OA/BE 모드, mode-set, octet-align 을 SDP nego 값과 일치시킨다.
- 옵션: 묵음(DTX/SID) 삽입, 패킷 손실(seq drop), 지터(송신 간격 변동), 잘못된 SSRC/PT(네거티브 테스트).
- telephone-event(101/103) payload 도 선택적으로 송출.

## 7. validator (역방향 검증) 요구
- 송출한 frame 시퀀스로부터 **기대 .awb 파일**을 위 의사코드로 생성(golden).
- 서버 저장 파일과 byte/frame 단위 비교. 묵음 변환·손실 채움까지 동일 규칙으로 판정.
- 불일치 시 frame index/FT/길이 단위 diff 를 리포트.

### 7.1 구현 현황 (`backend/sim/validator/reconstruct.py`)
- `reconstruct_awb(frames)`: timestamp 무관, speech 그대로 + SID/NO_DATA→묵음 1개.
- `reconstruct_from_packets(packets)`: **부록5 완전판** — 수신 RTP 패킷의 timestamp 증가분으로
  손실/DTX 구간을 묵음 패킷으로 채운다. 연속 패킷 간 `gap=(now-old)/SAMPLES`, `gap>1`이면
  `(gap-1)`개 묵음 채움. 검증기는 패킷이 있으면 이 경로를 우선 사용한다.
