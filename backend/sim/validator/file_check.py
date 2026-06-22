"""녹취 파일 존재/명명/경로/magic 검증 (docs/specs/file-storage.md, observed-from-logs.md §3)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..platform.models import ValidationItem
from ..scenario.expectations import ScenarioExpectations, TalkSpurtExpectation
from .reconstruct import MAGIC_AMR, MAGIC_AMRWB


def find_file(root: str | Path, name_regex: str) -> Optional[Path]:
    """root 하위(.awb/.awb.ing 포함)에서 정규식에 맞는 파일 1개 탐색."""
    pat = re.compile(name_regex)
    for p in Path(root).rglob("*"):
        if p.is_file() and (pat.match(p.name) or pat.match(p.name.removesuffix(".ing"))):
            return p
    return None


def check_magic(path: Path, wb: bool = True) -> bool:
    magic = MAGIC_AMRWB if wb else MAGIC_AMR
    with open(path, "rb") as f:
        return f.read(len(magic)) == magic


def check_spurt_file(spurt: TalkSpurtExpectation, root: str | Path) -> ValidationItem:
    """한 talk-spurt 의 파일 존재/패턴/magic/크기 검증."""
    name = f"file[{spurt.index}] {spurt.talker_digits}"
    found = find_file(root, spurt.name_regex)
    if spurt.expect_empty:
        # 빈 발언: 파일이 없거나 0바이트일 수 있음(서버 "No packets recorded")
        if found is None:
            return ValidationItem(category="FILE", name=name, status="PASS",
                                  detail="빈 발언 → 파일 없음(정상)")
        size = found.stat().st_size
        return ValidationItem(category="FILE", name=name, status="PASS",
                              actual=str(found.name),
                              detail=f"빈 발언 파일 존재(size={size})")
    if found is None:
        return ValidationItem(category="FILE", name=name, status="FAIL",
                              expected=spurt.name_regex, actual=None,
                              detail="기대 파일을 찾지 못함")
    size = found.stat().st_size
    if size <= 0:
        return ValidationItem(category="FILE", name=name, status="FAIL",
                              actual=str(found.name), detail="파일 크기 0")
    if not check_magic(found):
        return ValidationItem(category="FILE", name=name, status="FAIL",
                              actual=str(found.name), detail="magic number 불일치")
    return ValidationItem(category="FILE", name=name, status="PASS",
                          actual=str(found.name), detail=f"존재/패턴/magic OK (size={size})")


def check_files(exp: ScenarioExpectations, root: str | Path) -> list[ValidationItem]:
    return [check_spurt_file(s, root) for s in exp.talk_spurts]
