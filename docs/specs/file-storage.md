# 녹취 파일명 / 디렉토리 구조 규격

> 출처: "녹취(uVCS) 설계서 2.6 (녹취 File 관리)".
> 담당: `validator`(파일 존재/명명/경로 검증), `scenario`(기대 파일명 산출).
>
> ⚠️ **실제 파일명/경로는 `observed-from-logs.md §3` 가 우선**한다:
> IMS `I_{CALLID}_{from}_{to}_{YYYYMMDDHHMMSS}.awb`(caller/callee 2개),
> MCPTT `M_{CALLID}_{talkerMDN}_{GROUPID}_{YYYYMMDDHHMMSS}_{FILE_INDEX}.awb`(talk-spurt별),
> 저장 루트 **`/home/vcs/ramdisk/...`** + 진행중 **`.awb.ing`** → 완료 시 NAS 이관.
> 아래 설계서 규칙은 참고용.

## 1. 원칙
- 녹음 파일은 **Unique** 하게 관리되어야 한다.
- `recording_start_req.save_file_name` 은 **확장자 제외** 이름이며, 서버가 코덱에 맞는 확장자를 붙인다.

## 2. 파일명 규칙
`{접두}_{CALL-ID}_{MDN}_{HHMMSSsss}.{확장자}`
- 접두: `I` = IMS, `M` = MCPTT.
- 확장자(음성): AMR-WB = `.awb`, AMR-NB = `.amr`.
- 확장자(영상): H.264 = `.h264`.

| 망 | 미디어 | 코덱 | 파일명 |
|---|---|---|---|
| IMS | 음성 | AMR-WB | `I_{CALL-ID}_MDN_HHMMSSsss.awb` |
| IMS | 음성 | AMR-NB | `I_{CALL-ID}_MDN_HHMMSSsss.amr` |
| MCPTT | 음성 | AMR-WB | `M_{CALL-ID}_MDN_HHMMSSsss.awb` |
| MCPTT | 음성 | AMR-NB | `M_{CALL-ID}_MDN_HHMMSSsss.amr` |
| IMS | 영상 | H.264 | `I_{CALL-ID}_MDN_HHMMSSsss.h264` |
| MCPTT | 영상 | H.264 | `M_{CALL-ID}_MDN_HHMMSSsss.h264` |

## 3. 디렉토리 구조
```
~/REC/
├── MCPTT/
│   ├── VIDEO/{YYYY}/{MM}/{DD}/{HH}/
│   ├── VOICE/{YYYY}/{MM}/{DD}/{HH}/
│   └── CONV /{YYYY}/{MM}/{DD}/{HH}/
└── IMS/
    ├── VIDEO/{YYYY}/{MM}/{DD}/{HH}/
    ├── VOICE/{YYYY}/{MM}/{DD}/{HH}/
    └── CONV /{YYYY}/{MM}/{DD}/{HH}/
```
- `CONV` = 음성+영상 결합(AUDIO_VIDEO) 등 변환/통합 산출물 영역(설계 추정, 검증 시 존재만 확인).
- `~/REC` 루트는 config(`sim.yaml: sut.rec_root`)로 지정. 시뮬레이터가 원격이면 마운트/접근 경로 설정.

## 4. validator 체크리스트
- 호 종료 후 기대 경로에 파일 존재 (망/미디어/시각 디렉토리 정합).
- 파일명 접두/CALL-ID/MDN/시각/확장자 패턴 일치 (정규식 검증).
- `record_file.FILE_NAME` 과 실제 파일명 일치, `AUDIO_EXTENSION` ↔ 확장자 정합.
- 파일 크기 > 0, magic number(`#!AMR-WB\n` 등) 존재, `amr-wb-rtp.md` 의 골든 비교.
