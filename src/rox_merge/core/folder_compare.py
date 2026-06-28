"""재귀 폴더 비교 엔진 (PLAN §2 M2, §6.4). 순수 Python, Qt 무의존.

두 디렉터리를 재귀 비교해 각 항목을 분류한다:
``same / left_only / right_only / different``.

"내용 다름" 판정 (PLAN 결정 Q3):
- 크기가 다르면 즉시 different.
- 크기가 같으면:
  - EXACT 모드: 내용 해시로 확정.
  - FAST 모드: mtime이 같으면 same, 다르면 해시로 확인(하이브리드).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

# 항목 상태
SAME = "same"
LEFT_ONLY = "left_only"
RIGHT_ONLY = "right_only"
DIFFERENT = "different"

# 비교 정밀도
MODE_FAST = "fast"     # 크기 + mtime (mtime 다르면 해시로 확인)
MODE_EXACT = "exact"   # 항상 내용 해시

_HASH_CHUNK = 65536


@dataclass
class CompareNode:
    """폴더 비교 트리의 한 항목."""

    name: str                       # 항목 이름
    relpath: str                    # 루트 기준 상대 경로
    is_dir: bool
    status: str                     # SAME | LEFT_ONLY | RIGHT_ONLY | DIFFERENT
    children: list["CompareNode"] = field(default_factory=list)
    left_exists: bool = False
    right_exists: bool = False

    @property
    def has_difference(self) -> bool:
        """이 항목(또는 하위)에 차이가 있는지 — 필터/초기 확장 판정용."""
        return self.status != SAME


def compare_dirs(left: str | Path, right: str | Path, mode: str = MODE_FAST) -> CompareNode:
    """두 디렉터리를 재귀 비교해 루트 :class:`CompareNode` 를 반환한다."""
    left, right = Path(left), Path(right)
    children = _compare_children(left, right, "", mode)
    return CompareNode(
        name=left.name or str(left),
        relpath="",
        is_dir=True,
        status=_dir_status(children),
        children=children,
        left_exists=True,
        right_exists=True,
    )


def _entries(path: Path) -> set[str]:
    try:
        return {p.name for p in path.iterdir()}
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return set()


def _compare_children(lp: Path, rp: Path, relpath: str, mode: str) -> list[CompareNode]:
    left_names = _entries(lp)
    right_names = _entries(rp)
    nodes: list[CompareNode] = []
    for name in sorted(left_names | right_names):
        child_rel = f"{relpath}/{name}" if relpath else name
        cl, cr = lp / name, rp / name
        in_l, in_r = name in left_names, name in right_names
        l_dir = in_l and cl.is_dir()
        r_dir = in_r and cr.is_dir()

        if in_l and in_r:
            if l_dir and r_dir:
                kids = _compare_children(cl, cr, child_rel, mode)
                nodes.append(CompareNode(name, child_rel, True, _dir_status(kids),
                                         kids, True, True))
            elif not l_dir and not r_dir:
                status = compare_files(cl, cr, mode)
                nodes.append(CompareNode(name, child_rel, False, status, [], True, True))
            else:
                # 한쪽은 파일, 한쪽은 폴더 — 타입 불일치 → different
                nodes.append(CompareNode(name, child_rel, l_dir or r_dir, DIFFERENT,
                                         [], True, True))
        elif in_l:
            nodes.append(_only_node(cl, child_rel, name, LEFT_ONLY, "left"))
        else:
            nodes.append(_only_node(cr, child_rel, name, RIGHT_ONLY, "right"))
    return nodes


def _only_node(path: Path, relpath: str, name: str, status: str, side: str) -> CompareNode:
    is_dir = path.is_dir()
    children: list[CompareNode] = []
    if is_dir:
        for child in sorted(_entries(path)):
            children.append(
                _only_node(path / child, f"{relpath}/{child}", child, status, side)
            )
    return CompareNode(
        name=name,
        relpath=relpath,
        is_dir=is_dir,
        status=status,
        children=children,
        left_exists=(side == "left"),
        right_exists=(side == "right"),
    )


def _dir_status(children: list[CompareNode]) -> str:
    """하위가 모두 same이면 same, 아니면 different (양쪽 존재 폴더 기준)."""
    return SAME if all(c.status == SAME for c in children) else DIFFERENT


def compare_files(left: Path, right: Path, mode: str = MODE_FAST) -> str:
    """두 파일을 비교해 SAME 또는 DIFFERENT 를 반환한다."""
    try:
        ls, rs = left.stat(), right.stat()
    except OSError:
        return DIFFERENT

    if ls.st_size != rs.st_size:
        return DIFFERENT

    if mode == MODE_EXACT:
        return SAME if _file_hash(left) == _file_hash(right) else DIFFERENT

    # FAST: 크기 같음 → mtime 같으면 same, 아니면 해시로 확인
    if ls.st_mtime_ns == rs.st_mtime_ns:
        return SAME
    return SAME if _file_hash(left) == _file_hash(right) else DIFFERENT


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()
