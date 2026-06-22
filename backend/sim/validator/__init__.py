"""validator: 파일/DB/오디오 무결성 검증 (핵심 검증 두뇌).

권위 스펙: docs/specs/observed-from-logs.md(DB/파일/통계), amr-wb-rtp.md(부록5),
silence-packets.md, file-storage.md, db-schema.md.
"""

from .silence_tables import SILENCE_AMRWB, SILENCE_AMR, write_mute
from .reconstruct import reconstruct_awb, storage_record, MAGIC_AMRWB, MAGIC_AMR
from .audio_check import compare_awb
from .file_check import check_files, check_spurt_file, find_file
from .db_check import check_db
from .video_check import compare_h264, reconstruct_annexb, reconstruct_annexb_interleaved
from .report import Validator, aggregate

__all__ = [
    "SILENCE_AMRWB", "SILENCE_AMR", "write_mute",
    "reconstruct_awb", "storage_record", "MAGIC_AMRWB", "MAGIC_AMR",
    "compare_awb", "check_files", "check_spurt_file", "find_file", "check_db",
    "compare_h264", "reconstruct_annexb", "reconstruct_annexb_interleaved",
    "Validator", "aggregate",
]
