"""재귀 폴더 비교 엔진 테스트."""

import os

from rox_merge.core.folder_compare import (
    DIFFERENT,
    LEFT_ONLY,
    MODE_EXACT,
    MODE_FAST,
    RIGHT_ONLY,
    SAME,
    compare_dirs,
    compare_files,
)


def _write(path, content: bytes = b"x", mtime_ns: int | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))


def _by_name(node):
    return {c.name: c for c in node.children}


# ------------------------------------------------------------- 단일 파일 비교


def test_compare_files_size_differs(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    _write(a, b"abc"); _write(b, b"abcd")
    assert compare_files(a, b) == DIFFERENT


def test_compare_files_exact_detects_content(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    # 같은 크기, 같은 mtime, 다른 내용
    _write(a, b"abc", mtime_ns=1_000_000_000)
    _write(b, b"abd", mtime_ns=1_000_000_000)
    assert compare_files(a, b, MODE_FAST) == SAME      # fast는 못 잡음(크기·mtime 동일)
    assert compare_files(a, b, MODE_EXACT) == DIFFERENT  # exact는 해시로 잡음


def test_compare_files_fast_mtime_differs_uses_hash(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    # 같은 크기·내용, 다른 mtime → fast도 해시로 same 확정
    _write(a, b"abc", mtime_ns=1_000_000_000)
    _write(b, b"abc", mtime_ns=2_000_000_000)
    assert compare_files(a, b, MODE_FAST) == SAME
    # 같은 크기·다른 내용, 다른 mtime → different
    _write(b, b"abd", mtime_ns=2_000_000_000)
    assert compare_files(a, b, MODE_FAST) == DIFFERENT


# ------------------------------------------------------------- 디렉터리 비교


def test_identical_dirs(tmp_path):
    left = tmp_path / "L"; right = tmp_path / "R"
    _write(left / "a.txt", b"hello", mtime_ns=1_000)
    _write(right / "a.txt", b"hello", mtime_ns=1_000)
    root = compare_dirs(left, right)
    assert root.status == SAME
    assert _by_name(root)["a.txt"].status == SAME


def test_left_only_and_right_only(tmp_path):
    left = tmp_path / "L"; right = tmp_path / "R"
    _write(left / "only_left.txt")
    _write(right / "only_right.txt")
    root = compare_dirs(left, right)
    by = _by_name(root)
    assert by["only_left.txt"].status == LEFT_ONLY
    assert by["only_right.txt"].status == RIGHT_ONLY
    assert root.status == DIFFERENT


def test_different_file(tmp_path):
    left = tmp_path / "L"; right = tmp_path / "R"
    _write(left / "a.txt", b"aaa")
    _write(right / "a.txt", b"bbbb")  # 크기 다름
    root = compare_dirs(left, right)
    assert _by_name(root)["a.txt"].status == DIFFERENT
    assert root.status == DIFFERENT


def test_nested_dir_status_propagates(tmp_path):
    left = tmp_path / "L"; right = tmp_path / "R"
    _write(left / "sub" / "same.txt", b"x", mtime_ns=5)
    _write(right / "sub" / "same.txt", b"x", mtime_ns=5)
    _write(left / "sub" / "diff.txt", b"aa")
    _write(right / "sub" / "diff.txt", b"bbb")
    root = compare_dirs(left, right)
    sub = _by_name(root)["sub"]
    assert sub.is_dir
    assert sub.status == DIFFERENT  # 하위에 차이 있음
    sub_by = _by_name(sub)
    assert sub_by["same.txt"].status == SAME
    assert sub_by["diff.txt"].status == DIFFERENT


def test_left_only_dir_is_recursive(tmp_path):
    left = tmp_path / "L"; right = tmp_path / "R"
    _write(left / "pkg" / "mod.py", b"code")
    right.mkdir()
    root = compare_dirs(left, right)
    pkg = _by_name(root)["pkg"]
    assert pkg.is_dir and pkg.status == LEFT_ONLY
    assert _by_name(pkg)["mod.py"].status == LEFT_ONLY


def test_empty_dirs_are_same(tmp_path):
    left = tmp_path / "L"; right = tmp_path / "R"
    left.mkdir(); right.mkdir()
    assert compare_dirs(left, right).status == SAME
