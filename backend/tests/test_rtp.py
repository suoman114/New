"""rtp-media 테스트 — RTP 헤더, AMR-WB OA 패킷화, 스트림/통계, 손상."""

from sim.rtp import (
    AmrWbStream,
    RtpPacket,
    amrwb_frame_bytes,
    encoder,
    impair,
    packetize_oa,
    parse_oa,
)
from sim.rtp.amrwb import AMRWB_SPEECH_BITS, SID_FT_WB


def test_rtp_header_roundtrip():
    pkt = RtpPacket(payload_type=98, sequence=161, timestamp=480, ssrc=1195870476,
                    payload=b"\xf0\x40\x11", marker=True)
    raw = pkt.pack()
    back = RtpPacket.unpack(raw)
    assert back.payload_type == 98
    assert back.sequence == 161
    assert back.timestamp == 480
    assert back.ssrc == 1195870476
    assert back.marker is True
    assert back.payload == b"\xf0\x40\x11"


def test_amrwb_frame_byte_lengths():
    # 부록6: FT0=132bit→17B, FT8=477bit→60B, SID(9)=40bit→5B
    assert amrwb_frame_bytes(0) == (AMRWB_SPEECH_BITS[0] + 7) // 8 == 17
    assert amrwb_frame_bytes(8) == 60
    assert amrwb_frame_bytes(SID_FT_WB) == 5
    assert amrwb_frame_bytes(15) == 0  # NO_DATA


def test_packetize_parse_oa_roundtrip():
    frames = encoder.speech_frames(3, ft=8, seed=7)
    payload = packetize_oa(frames)
    # [CMR][3×ToC][3×60B]
    assert payload[0] == 0xF0
    back = parse_oa(payload)
    assert [f.ft for f in back] == [8, 8, 8]
    assert all(len(f.data) == 60 for f in back)
    assert back[0].data == frames[0].data


def test_toc_last_flag():
    payload = packetize_oa(encoder.speech_frames(2, ft=8))
    # ToC bytes at index 1,2; first F=1(0x80 set), last F=0
    assert payload[1] & 0x80
    assert not (payload[2] & 0x80)


def test_stream_seq_ts_increment_and_stats():
    frames = encoder.talk_spurt(80, ft=8)  # 80ms → 4 frames
    stream = AmrWbStream(ssrc=12345, payload_type=98, start_seq=100, start_ts=1000)
    packets = stream.build(frames)
    assert [p.sequence for p in packets] == [100, 101, 102, 103]
    assert [p.timestamp for p in packets] == [1000, 1320, 1640, 1960]  # +320
    assert packets[0].marker is True and packets[1].marker is False
    st = stream.stats(packets)
    assert st.total_packets == 4 and st.first_seq == 100 and st.last_seq == 103
    assert st.ssrc == 12345 and st.play_time_ms == 80


def test_loss_creates_gap_but_keeps_seq():
    frames = encoder.speech_frames(10, ft=8)
    packets = AmrWbStream(ssrc=1, start_seq=0).build(frames)
    kept, dropped = impair.drop_random(packets, loss_pct=100.0, seed=1)
    assert len(kept) == 0 and len(dropped) == 10
    kept2 = impair.drop_by_indices(packets, {3, 7})
    seqs = [p.sequence for p in kept2]
    assert 3 not in seqs and 7 not in seqs and len(seqs) == 8


def test_inject_silence_and_sid_count():
    frames = encoder.speech_frames(4, ft=8) + encoder.sid_frames(1)
    stream = AmrWbStream(ssrc=9)
    st = stream.stats(stream.build(frames))
    assert st.sid_count == 1
    with_sil = impair.inject_silence(encoder.speech_frames(4, ft=8), every=2, run=1)
    assert sum(1 for f in with_sil if f.is_no_data) == 2
