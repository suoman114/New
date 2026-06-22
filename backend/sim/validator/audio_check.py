"""오디오 무결성 비교: 골든 .awb vs 서버 저장 .awb (frame 단위 diff)."""

from __future__ import annotations

from ..platform.models import ValidationItem
from ..rtp.amrwb import amrwb_frame_bytes
from .reconstruct import MAGIC_AMR, MAGIC_AMRWB


def _split_records(data: bytes, wb: bool) -> tuple[bytes, list[bytes]]:
    """(magic, [record...]) 로 분리."""
    magic = MAGIC_AMRWB if wb else MAGIC_AMR
    head = data[:len(magic)]
    body = data[len(magic):]
    records: list[bytes] = []
    idx = 0
    while idx < len(body):
        header = body[idx]
        ft = (header >> 3) & 0x0F
        n = amrwb_frame_bytes(ft) if ft <= 9 else 0
        records.append(body[idx:idx + 1 + n])
        idx += 1 + n
    return head, records


def compare_awb(golden: bytes, actual: bytes, *, name: str = "audio",
                wb: bool = True) -> ValidationItem:
    """골든과 실제 파일을 비교하여 ValidationItem(category=AUDIO) 반환."""
    if golden == actual:
        return ValidationItem(category="AUDIO", name=name, status="PASS",
                              detail=f"{len(actual)}B 일치")
    # magic 비교
    g_magic, g_recs = _split_records(golden, wb)
    a_magic, a_recs = _split_records(actual, wb)
    if g_magic != a_magic:
        return ValidationItem(category="AUDIO", name=name, status="FAIL",
                              expected=g_magic.decode("latin1"),
                              actual=a_magic.decode("latin1", "replace"),
                              detail="magic number 불일치")
    if len(g_recs) != len(a_recs):
        return ValidationItem(category="AUDIO", name=name, status="FAIL",
                              expected=len(g_recs), actual=len(a_recs),
                              detail=f"frame 수 불일치 (golden={len(g_recs)}, actual={len(a_recs)})")
    for i, (g, a) in enumerate(zip(g_recs, a_recs)):
        if g != a:
            return ValidationItem(category="AUDIO", name=name, status="FAIL",
                                  expected=g.hex(), actual=a.hex(),
                                  detail=f"frame[{i}] 불일치 (FT={(g[0] >> 3) & 0xF})")
    return ValidationItem(category="AUDIO", name=name, status="FAIL",
                          detail="길이만 상이(tail 차이)")
