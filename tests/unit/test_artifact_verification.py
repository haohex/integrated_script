"""Prevent incomplete or mixed builds from reaching the download page."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from scripts.verify_artifacts import (
    RELEASE_TARGETS,
    pe_subsystem,
    sha256,
    verify_checksums,
    verify_release,
)


def release_fixture(directory: Path) -> None:
    for target, (plat, arch, modes) in RELEASE_TARGETS.items():
        info = {
            "tag": "v3.0.1",
            "version": "3.0.1",
            "commit": "same-commit",
            "artifacts": {},
        }
        suffix = "zip" if plat == "windows" else "tar.gz"
        files = []
        for mode in modes:
            path = directory / f"integrated-script-v3.0.1-{plat}-{arch}-{mode}.{suffix}"
            path.write_bytes(f"fixture-{target}-{mode}".encode())
            files.append(path)
            info["artifacts"][path.name] = sha256(path)
        metadata = directory / f"BUILDINFO-{target}.json"
        metadata.write_text(json.dumps(info), "utf-8")
        files.append(metadata)
        (directory / f"SHA256SUMS-{target}.txt").write_text(
            "".join(f"{sha256(path)}  {path.name}\n" for path in files), "utf-8"
        )


def test_release_requires_all_five_archives_and_emits_global_checksums(tmp_path):
    release_fixture(tmp_path)
    verify_release(tmp_path, "v3.0.1")
    assert len((tmp_path / "SHA256SUMS.txt").read_text().splitlines()) == 5


def test_modified_archive_cannot_pass_checksums(tmp_path):
    release_fixture(tmp_path)
    next(tmp_path.glob("*.zip")).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="corrupted artifact"):
        verify_release(tmp_path, "v3.0.1")


def test_missing_gui_archive_cannot_release(tmp_path):
    release_fixture(tmp_path)
    next(tmp_path.glob("*windows*gui.zip")).unlink()
    with pytest.raises(ValueError, match="corrupted artifact"):
        verify_release(tmp_path, "v3.0.1")


def test_different_commits_cannot_release_even_with_correct_checksums(tmp_path):
    release_fixture(tmp_path)
    metadata = tmp_path / "BUILDINFO-windows-x64.json"
    info = json.loads(metadata.read_text())
    info["commit"] = "other-commit"
    metadata.write_text(json.dumps(info))
    manifest = tmp_path / "SHA256SUMS-windows-x64.txt"
    lines = manifest.read_text().splitlines()
    lines[-1] = f"{sha256(metadata)}  {metadata.name}"
    manifest.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="inconsistent build commits"):
        verify_release(tmp_path, "v3.0.1")


def test_additional_macos_archive_cannot_accidentally_publish(tmp_path):
    release_fixture(tmp_path)
    (tmp_path / "unexpected-macos.app.zip").write_bytes(b"not in scope")
    with pytest.raises(ValueError, match="Unexpected archives"):
        verify_release(tmp_path, "v3.0.1")


def test_checksum_filename_cannot_escape_artifact_directory(tmp_path):
    (tmp_path / "SHA256SUMS-linux-x64.txt").write_text("abc  ../outside\n")
    with pytest.raises(ValueError, match="Invalid checksum filename"):
        verify_checksums(tmp_path)


@pytest.mark.parametrize("subsystem", [2, 3])
def test_read_actual_pe_header_subsystem(tmp_path, subsystem):
    blob = bytearray(256)
    blob[:2] = b"MZ"
    struct.pack_into("<I", blob, 0x3C, 64)
    blob[64:68] = b"PE\0\0"
    struct.pack_into("<H", blob, 64 + 4 + 20 + 68, subsystem)
    path = tmp_path / "program.exe"
    path.write_bytes(blob)
    assert pe_subsystem(path) == subsystem
