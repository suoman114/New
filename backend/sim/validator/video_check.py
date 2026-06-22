"""H.264 영상 검증 (2차) — RTP payload → Annex B(.h264) 재구성 + NAL 단위 diff.

서버는 수신 RTP 를 de-packetize(FU-A 재조립/STAP-A 분해) → (interleaved 면 DON 정렬) →
NRI=0 drop → Annex B 저장한다. 검증기는 동일 규칙으로 골든을 만들어 byte/ NAL 비교한다.
규격: docs/specs/h264.md (부록8·9).
"""

from __future__ import annotations

from ..platform.models import ValidationItem
from ..rtp.h264 import (
    ANNEXB_START,
    NalWithDon,
    deinterleave,
    depacketize,
    drop_nri_zero,
    nal_type,
    to_annexb,
)


def reconstruct_annexb(payloads: list[bytes], *, drop_nri0: bool = True) -> bytes:
    """비-interleaved(single/STAP-A/FU-A) RTP payload → Annex B."""
    nals = depacketize(payloads)
    if drop_nri0:
        nals = drop_nri_zero(nals)
    return to_annexb(nals)


def reconstruct_annexb_interleaved(units: list[NalWithDon], *,
                                   drop_nri0: bool = True) -> bytes:
    """interleaved 모드: (NAL,DON) 수신 → DON/AbsDON 정렬 → Annex B."""
    nals = deinterleave(units)
    if drop_nri0:
        nals = drop_nri_zero(nals)
    return to_annexb(nals)


def split_annexb(data: bytes) -> list[bytes]:
    """Annex B byte stream → NAL unit 리스트(start code 제거). 3/4 byte start code 허용."""
    nals: list[bytes] = []
    i = 0
    n = len(data)
    starts: list[int] = []
    while i < n - 3:
        if data[i] == 0 and data[i + 1] == 0:
            if data[i + 2] == 1:
                starts.append(i + 3)
                i += 3
                continue
            if i < n - 4 and data[i + 2] == 0 and data[i + 3] == 1:
                starts.append(i + 4)
                i += 4
                continue
        i += 1
    for k, s in enumerate(starts):
        e = starts[k + 1] - 4 if k + 1 < len(starts) else n
        # 다음 start code 직전까지(직전 start code 길이 보정은 단순화: 4 가정 후 트림)
        nal = data[s:e]
        # 끝의 00 00 00 / 00 00 잔여 제거
        nals.append(nal.rstrip(b"\x00") if k + 1 < len(starts) else nal)
    return [x for x in nals if x]


def compare_h264(golden: bytes, actual: bytes, *, name: str = "video") -> ValidationItem:
    if golden == actual:
        return ValidationItem(category="AUDIO", name=name, status="PASS",
                              detail=f"{len(actual)}B 일치 (h264)")
    g = split_annexb(golden)
    a = split_annexb(actual)
    if len(g) != len(a):
        return ValidationItem(category="AUDIO", name=name, status="FAIL",
                              expected=len(g), actual=len(a),
                              detail=f"NAL 수 불일치 (golden={len(g)}, actual={len(a)})")
    for i, (x, y) in enumerate(zip(g, a)):
        if x != y:
            return ValidationItem(category="AUDIO", name=name, status="FAIL",
                                  detail=f"NAL[{i}] 불일치 (type golden={nal_type(x)}, "
                                         f"actual={nal_type(y)})")
    return ValidationItem(category="AUDIO", name=name, status="FAIL",
                          detail="start code/길이 차이")


__all__ = [
    "reconstruct_annexb", "reconstruct_annexb_interleaved", "split_annexb",
    "compare_h264", "ANNEXB_START",
]
