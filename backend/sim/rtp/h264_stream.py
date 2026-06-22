"""H.264 NAL → RTP 패킷 스트림 (영상 트래픽 송출).

packetization_mode 에 따라 Single/FU-A(대형 NAL 분할)로 패킷화하고 90kHz timestamp 를
프레임 단위로 증가시킨다. 송출 payload 순서가 곧 decoding order(비-interleaved)이므로
검증기는 `reconstruct_annexb(payloads)` 로 동일 골든을 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .h264 import packetize_fu_a, packetize_single, packetize_stap_a
from .rtp import RtpPacket


@dataclass
class H264Stream:
    ssrc: int
    payload_type: int = 96
    clock: int = 90000
    fps: int = 25
    start_seq: int = 0
    start_ts: int = 0
    mtu: int = 1200
    mode: int = 1                    # 0=single only, 1=Non-interleaved(FU-A 허용)

    def build(self, nals: list[bytes], *, nals_per_frame: int = 1
              ) -> tuple[list[RtpPacket], list[bytes]]:
        """NAL 리스트 → (RTP 패킷, payload 리스트). payload 순서 = decoding order."""
        packets: list[RtpPacket] = []
        payloads: list[bytes] = []
        seq = self.start_seq
        ts = self.start_ts
        ts_inc = self.clock // max(1, self.fps)
        frames = [nals[i:i + nals_per_frame]
                  for i in range(0, len(nals), nals_per_frame)] or [[]]
        for frame in frames:
            frame_payloads: list[bytes] = []
            for n in frame:
                if self.mode != 0 and len(n) > self.mtu:
                    frame_payloads.extend(packetize_fu_a(n, self.mtu))
                else:
                    frame_payloads.append(packetize_single(n))
            for pi, pl in enumerate(frame_payloads):
                last = pi == len(frame_payloads) - 1
                packets.append(RtpPacket(
                    payload_type=self.payload_type, sequence=seq & 0xFFFF,
                    timestamp=ts & 0xFFFFFFFF, ssrc=self.ssrc, payload=pl, marker=last))
                payloads.append(pl)
                seq += 1
            ts += ts_inc
        return packets, payloads

    def build_stap_a(self, nals: list[bytes]) -> tuple[list[RtpPacket], list[bytes]]:
        """작은 NAL 들을 STAP-A 1패킷으로 묶는 변형(테스트/효율)."""
        payload = packetize_stap_a(nals)
        pkt = RtpPacket(payload_type=self.payload_type, sequence=self.start_seq & 0xFFFF,
                        timestamp=self.start_ts & 0xFFFFFFFF, ssrc=self.ssrc,
                        payload=payload, marker=True)
        return [pkt], [payload]
