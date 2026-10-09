#!/usr/bin/env python3
"""Package, extract and verify the same archives distributed on GitHub Releases."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import struct
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

if __package__:
    from .package_artifacts import PROJECT_ROOT, artifact_name, package
else:
    from package_artifacts import PROJECT_ROOT, artifact_name, package

RELEASE_TARGETS = {
    "windows-x64": ("windows", "x64", ("tui", "gui")),
    "linux-x64": ("linux", "x64", ("tui", "gui")),
    "linux-arm64": ("linux", "arm64", ("tui",)),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pe_subsystem(path: Path) -> int:
    """Read IMAGE_OPTIONAL_HEADER.Subsystem (2=GUI, 3=console)."""
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError(f"Not a Windows executable: {path}")
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset)
        if stream.read(4) != b"PE\0\0":
            raise ValueError(f"Invalid PE signature: {path}")
        stream.seek(offset + 4 + 20 + 68)
        return struct.unpack("<H", stream.read(2))[0]


def prepare(plat: str, arch: str, tag: str, output: Path) -> None:
    target = f"{plat}-{arch}"
    if target not in RELEASE_TARGETS:
        raise ValueError(f"Unsupported release target: {target}")
    version = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))[
        "project"
    ]["version"]
    if tag.startswith("v") and tag != f"v{version}":
        raise ValueError(f"Tag {tag} does not match product version {version}")
    modes = RELEASE_TARGETS[target][2]
    files = [package(mode, plat, tag, arch, output) for mode in modes]
    info = {
        "version": version,
        "tag": tag,
        "target": target,
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip(),
        "python": platform.python_version(),
        "build_system": platform.platform(),
        "machine": platform.machine(),
        "packages": {},
        "artifacts": {path.name: sha256(path) for path in files},
    }
    for name in ("pyinstaller", "textual", "PySide6", "Pillow", "platformdirs"):
        try:
            info["packages"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    if plat == "windows":
        for mode in modes:
            directory = "integrated_script" + ("_gui" if mode == "gui" else "")
            subsystem = pe_subsystem(
                PROJECT_ROOT / "dist" / directory / f"{directory}.exe"
            )
            expected = 2 if mode == "gui" else 3
            if subsystem != expected:
                raise ValueError(
                    f"{mode} PE subsystem {subsystem}, expected {expected}"
                )
            info[f"{mode}_subsystem"] = subsystem
    metadata_file = output / f"BUILDINFO-{target}.json"
    metadata_file.write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    files.append(metadata_file)
    (output / f"SHA256SUMS-{target}.txt").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="utf-8"
    )
    print(json.dumps(info, ensure_ascii=False, indent=2))


def verify_checksums(directory: Path) -> None:
    manifests = sorted(directory.glob("SHA256SUMS-*.txt"))
    if not manifests:
        raise ValueError("Missing SHA256SUMS manifests")
    for manifest in manifests:
        for line in manifest.read_text("utf-8").splitlines():
            digest, name = line.split("  ", 1)
            if Path(name).name != name:
                raise ValueError(f"Invalid checksum filename: {name}")
            path = directory / name
            if not path.is_file() or sha256(path) != digest:
                raise ValueError(f"Missing or corrupted artifact: {name}")
            print(f"Verified {name}")


def extract(directory: Path, destination: Path) -> None:
    verify_checksums(directory)
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(directory.iterdir()):
        if path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                archive.extractall(destination, filter="data")
        elif path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                archive.extractall(destination)


def verify_release(directory: Path, tag: str) -> None:
    verify_checksums(directory)
    commits = set()
    expected_archives = set()
    for target, (plat, arch, modes) in RELEASE_TARGETS.items():
        info = json.loads((directory / f"BUILDINFO-{target}.json").read_text("utf-8"))
        if info["tag"] != tag or f"v{info['version']}" != tag:
            raise ValueError(f"Version mismatch in {target}")
        commits.add(info["commit"])
        for mode in modes:
            name = artifact_name(tag, plat, arch, mode)
            expected_archives.add(name)
            path = directory / name
            if not path.is_file() or info["artifacts"].get(name) != sha256(path):
                raise ValueError(f"Missing or incorrect {name}")
    actual_archives = {
        path.name
        for path in directory.iterdir()
        if path.name.endswith((".zip", ".tar.gz"))
    }
    if actual_archives != expected_archives or len(commits) != 1:
        raise ValueError("Unexpected archives or inconsistent build commits")
    (directory / "SHA256SUMS.txt").write_text(
        "".join(
            f"{sha256(directory / name)}  {name}\n"
            for name in sorted(expected_archives)
        ),
        encoding="utf-8",
    )
    print(f"Verified all {len(expected_archives)} release archives at {commits.pop()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--platform", required=True, choices=("windows", "linux"))
    prep.add_argument("--arch", required=True, choices=("x64", "arm64"))
    prep.add_argument("--tag", required=True)
    prep.add_argument("--output", type=Path, default=PROJECT_ROOT / "dist/artifacts")
    unpack = commands.add_parser("extract")
    unpack.add_argument("--directory", type=Path, required=True)
    unpack.add_argument("--destination", type=Path, required=True)
    release = commands.add_parser("release")
    release.add_argument("--directory", type=Path, required=True)
    release.add_argument("--tag", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.platform, args.arch, args.tag, args.output)
    elif args.command == "extract":
        extract(args.directory, args.destination)
    else:
        verify_release(args.directory, args.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
