"""H.264 RTP de-packetization + DON/AbsDON + Annex B 재구성 검증 (부록8·9)."""

from sim.rtp.h264 import (
    ANNEXB_START,
    NalWithDon,
    absdon_sequence,
    deinterleave,
    depacketize,
    don_diff,
    drop_nri_zero,
    nal_nri,
    nal_type,
    packetize_fu_a,
    packetize_single,
    packetize_stap_a,
    synthetic_nals,
    to_annexb,
)
from sim.validator import compare_h264, reconstruct_annexb, reconstruct_annexb_interleaved
from sim.validator.video_check import split_annexb


def test_single_nal_roundtrip():
    nal = synthetic_nals(1, size=20)[0]
    assert depacketize([packetize_single(nal)]) == [nal]


def test_stap_a_aggregation():
    nals = synthetic_nals(3, size=10)
    payload = packetize_stap_a(nals)
    assert nal_type(payload) == 24
    assert depacketize([payload]) == nals


def test_fu_a_fragmentation_reassembly():
    nal = synthetic_nals(1, size=100)[0]
    packets = packetize_fu_a(nal, mtu=30)
    assert len(packets) > 1
    assert all(nal_type(p) == 28 for p in packets)
    # S/E 플래그
    assert (packets[0][1] >> 7) & 1 == 1            # start
    assert (packets[-1][1] >> 6) & 1 == 1           # end
    assert depacketize(packets) == [nal]


def test_mixed_payloads_depacketize():
    nals = synthetic_nals(4, size=60)
    payloads = [packetize_single(nals[0])]
    payloads += packetize_fu_a(nals[1], mtu=30)
    payloads.append(packetize_stap_a([nals[2], nals[3]]))
    assert depacketize(payloads) == nals


def test_annexb_build_and_split():
    nals = synthetic_nals(3, size=20)
    annexb = to_annexb(nals)
    assert annexb.startswith(ANNEXB_START)
    assert split_annexb(annexb) == nals


def test_drop_nri_zero():
    nals = synthetic_nals(3, size=10, nri=3)
    nals.append(bytes([0x01]) + b"\x00" * 10)       # NRI=0
    kept = drop_nri_zero(nals)
    assert len(kept) == 3 and all(nal_nri(n) != 0 for n in kept)


# ── DON / AbsDON (부록9) ──
def test_don_diff_basic_and_wrap():
    assert don_diff(5, 5) == 0
    assert don_diff(3, 7) == 4
    assert don_diff(7, 3) == -4
    # wrap-around
    assert don_diff(65535, 1) == 2          # 65536 - 65535 + 1
    assert don_diff(1, 65535) == -2


def test_absdon_monotonic_and_wrap():
    assert absdon_sequence([10, 11, 12]) == [10, 11, 12]
    # wrap: 65535 → 0 → 1 은 연속 증가로 해석
    seq = absdon_sequence([65535, 0, 1])
    assert seq[1] - seq[0] == 1 and seq[2] - seq[1] == 1


def test_deinterleave_orders_by_absdon():
    nals = synthetic_nals(4, size=10)
    # 수신 순서가 뒤섞임: DON 3,1,2,0 → decoding order 는 DON 오름차순
    units = [NalWithDon(nals[3], 3), NalWithDon(nals[1], 1),
             NalWithDon(nals[2], 2), NalWithDon(nals[0], 0)]
    ordered = deinterleave(units)
    assert ordered == [nals[0], nals[1], nals[2], nals[3]]


# ── 검증기: RTP → 골든 .h264 vs 서버 파일 ──
def test_reconstruct_and_compare_pass():
    nals = synthetic_nals(5, size=80)
    payloads = [packetize_single(nals[0]), packetize_single(nals[1])]
    payloads += packetize_fu_a(nals[2], mtu=40)
    payloads += packetize_fu_a(nals[3], mtu=40)
    payloads.append(packetize_single(nals[4]))
    golden = reconstruct_annexb(payloads)
    assert compare_h264(golden, golden).status == "PASS"


def test_compare_detects_nal_corruption():
    nals = synthetic_nals(4, size=40)
    golden = to_annexb(nals)
    bad = bytearray(golden)
    bad[-1] ^= 0xFF
    item = compare_h264(golden, bytes(bad))
    assert item.status == "FAIL" and "NAL[3]" in item.detail


def test_interleaved_reconstruction():
    nals = synthetic_nals(3, size=20)
    units = [NalWithDon(nals[2], 2), NalWithDon(nals[0], 0), NalWithDon(nals[1], 1)]
    golden = reconstruct_annexb_interleaved(units)
    assert golden == to_annexb(nals)
