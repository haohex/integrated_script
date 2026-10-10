#!/usr/bin/env python3
"""Drive the extracted terminal executable through a real PTY / Windows ConPTY.

The controller needs Pillow, pyte and pexpect (POSIX) / pywinpty (Windows).
These are acceptance tools; they are not dependencies of the distributed app.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import select
import subprocess
import tempfile
import time
import tomllib
import traceback
from pathlib import Path


def isolated_environment(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name, sub in {
        "HOME": "home",
        "USERPROFILE": "home",
        "XDG_CONFIG_HOME": "config",
        "XDG_CACHE_HOME": "cache",
        "XDG_STATE_HOME": "state",
        "XDG_DATA_HOME": "data",
        "APPDATA": "roaming",
        "LOCALAPPDATA": "local",
    }.items():
        directory = root / sub
        directory.mkdir(parents=True, exist_ok=True)
        env[name] = str(directory)
    env.update(TERM="xterm-256color", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PATH"] = (
        str(Path(env.get("SystemRoot", "C:/Windows")) / "System32")
        if os.name == "nt"
        else ""
    )
    return env


class Terminal:
    def __init__(self, executable: Path, root: Path, log: Path):
        import pyte

        self.windows = os.name == "nt"
        env = isolated_environment(root)
        if self.windows:
            from winpty import PtyProcess

            self.child = PtyProcess.spawn(
                [str(executable)], cwd=str(root), env=env, dimensions=(40, 120)
            )
        else:
            import pexpect

            self.child = pexpect.spawn(
                str(executable),
                [],
                cwd=str(root),
                env=env,
                encoding="utf-8",
                timeout=15,
                dimensions=(40, 120),
            )
        self.screen = pyte.Screen(120, 40)
        self.stream = pyte.Stream(self.screen)
        self.log = log.open("w", encoding="utf-8")

    def send(self, value: str) -> None:
        if self.windows:
            self.child.write(value)
        else:
            self.child.send(value)

    def pump(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.windows:
                if not select.select([self.child.fileobj], [], [], 0.05)[0]:
                    continue
                try:
                    data = self.child.read(65536)
                except EOFError:
                    break
            else:
                import pexpect

                try:
                    data = self.child.read_nonblocking(65536, timeout=0.05)
                except pexpect.TIMEOUT:
                    continue
                except pexpect.EOF:
                    break
            self.log.write(data)
            self.log.flush()
            self.stream.feed(data)

    def text(self) -> str:
        return "\n".join(self.screen.display)

    def wait_for(self, text: str, timeout: float = 40) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(0.3)
            if text in self.text():
                return
        raise AssertionError(f"Did not see {text!r}:\n{self.text()}")

    def ready(self) -> None:
        self.wait_for("搜索全部操作")
        self.wait_for("CTDS数据转YOLO格式")
        self.pump(1)

    def focus_search(self) -> None:
        for _ in range(6):
            self.send("\x06")
            self.pump(0.4)
            self.send("\x7f" * 48)
            self.pump(0.3)
            self.send("zzfocusprobe")
            self.pump(0.5)
            if "zzfocusprobe" in self.screen.display[1]:
                self.send("\x7f" * 48)
                self.pump(0.5)
                return
        raise AssertionError(f"Cannot focus search:\n{self.text()}")

    def select_operation(self, operation: str, title: str, label: str) -> None:
        for _ in range(3):
            self.focus_search()
            self.send(operation)
            self.pump(1.2)
            self.send("\t")
            self.pump(0.5)
            self.send("\x1b[B\x1b[B")
            self.pump(0.5)
            self.send("\r")
            self.pump(1)
            if label in self.text() and title in self.screen.display[3]:
                return
        raise AssertionError(f"Cannot select {operation}:\n{self.text()}")

    def fill_first_path(self, path: Path) -> None:
        self.send("\t\t")
        self.pump(0.6)
        for _ in range(14):
            self.send(str(path))
            self.pump(0.6)
            if path.name in self.text():
                return
            self.send("\t")
            self.pump(0.3)
        raise AssertionError(f"Cannot fill path {path}:\n{self.text()}")

    def run(self, timeout: float = 90) -> None:
        self.send("\x12")
        self.wait_for("执行成功", timeout=timeout)

    def quit(self) -> int:
        self.send("\x11")
        deadline = time.monotonic() + 20
        while self.child.isalive() and time.monotonic() < deadline:
            self.pump(0.2)
        if self.child.isalive():
            raise AssertionError("Ctrl+Q did not exit the terminal app")
        if not self.windows:
            self.child.close()
        return self.child.exitstatus

    def close(self) -> None:
        try:
            if self.child.isalive():
                self.child.terminate(force=True)
            self.child.close(force=True)
        finally:
            self.log.close()


def run_cases(
    executable: Path, output: Path, expected_version: str, compression_count: int
) -> dict:
    from PIL import Image

    report = {
        "platform": platform.platform(),
        "executable": str(executable),
        "status": "failed",
        "operations": [],
        "python_on_child_path": False,
        "network_isolation": os.environ.get(
            "ACCEPTANCE_NETWORK_ISOLATION", "not asserted"
        ),
    }
    with tempfile.TemporaryDirectory(prefix="is-") as directory:
        root = Path(directory)
        images = root / "图像 数据"
        images.mkdir()
        Image.new("RGB", (12, 9), "red").save(images / "样本 A.png")
        version = subprocess.run(
            [str(executable), "--version"],
            cwd=root,
            env=isolated_environment(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=40,
        )
        assert version.returncode == 0, version.stderr
        report["version"] = version.stdout.strip()
        assert report["version"].split()[-1] == expected_version, report["version"]
        cases = [
            ("label.create_empty", "创建空标签文件", "标签目录"),
            ("image.convert", "格式转换", "输入路径"),
        ]
        if compression_count:
            cases.append(("image.compress", "图像压缩", "输入路径"))
        for operation, title, label in cases:
            if operation == "image.compress":
                blob = (images / "样本 A.png").read_bytes()
                for number in range(compression_count - 1):
                    (images / f"样本 {number:04}.png").write_bytes(blob)
            terminal = Terminal(executable, root, output / f"{operation}.ansi.log")
            try:
                terminal.ready()
                terminal.select_operation(operation, title, label)
                terminal.fill_first_path(images)
                terminal.run(timeout=360 if operation == "image.compress" else 90)
                (output / f"{operation}.screen.txt").write_text(
                    terminal.text(), "utf-8"
                )
                if operation == "label.create_empty":
                    labels = list((root / "labels").glob("*.txt"))
                    assert len(labels) == 1 and labels[0].name == "样本 A.txt"
                    assert labels[0].read_bytes() == b""
                elif operation == "image.convert":
                    converted = list((root / "图像 数据_converted").glob("*.jpg"))
                    assert len(converted) == 1
                    with Image.open(converted[0]) as image:
                        assert image.format == "JPEG" and image.size == (12, 9)
                else:
                    compressed = list((root / "图像 数据_compressed").glob("*.png"))
                    assert len(compressed) == compression_count
                    for path in compressed:
                        with Image.open(path) as image:
                            assert image.format == "PNG" and image.size == (12, 9)
                exit_code = terminal.quit()
                assert exit_code == 0, exit_code
                report["operations"].append(
                    {
                        "id": operation,
                        "exit_code": exit_code,
                        "output_verified": True,
                        "output_count": (
                            compression_count if operation == "image.compress" else 1
                        ),
                    }
                )
            finally:
                terminal.close()
    report["status"] = "passed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-version", default="auto")
    parser.add_argument("--compression-count", type=int, default=1001)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        expected_version = args.expected_version
        if expected_version == "auto":
            project = Path(__file__).resolve().parents[1] / "pyproject.toml"
            expected_version = tomllib.loads(project.read_text("utf-8"))["project"][
                "version"
            ]
        if args.compression_count < 0:
            raise ValueError("compression count cannot be negative")
        report = run_cases(
            args.executable.resolve(),
            args.output,
            expected_version,
            args.compression_count,
        )
        exit_code = 0
    except Exception:
        report = {
            "status": "failed",
            "platform": platform.platform(),
            "traceback": traceback.format_exc(),
        }
        exit_code = 1
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
