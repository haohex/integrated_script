import io
import logging
import sys

import pytest

import integrated_script.main as entrypoint
from integrated_script.core.logging_config import LogManager
from integrated_script.core.windows_compat import setup_console_encoding


@pytest.mark.parametrize("missing", ["stdout", "stderr", "both"])
def test_windows_encoding_handles_individually_missing_streams(monkeypatch, missing):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")
    with monkeypatch.context() as patch:
        patch.setattr(sys, "platform", "win32")
        patch.setattr(sys, "stdout", stream if missing == "stderr" else None)
        patch.setattr(sys, "stderr", stream if missing == "stdout" else None)
        assert setup_console_encoding()
        if missing != "both":
            stream.write("图像 数据")
            stream.flush()
            assert buffer.getvalue() == "图像 数据".encode("utf-8")
    stream.close()


@pytest.mark.parametrize("stderr_available", [True, False])
def test_gui_initializes_encoding_before_real_startup_logging(
    monkeypatch, tmp_path, stderr_available
):
    buffer = io.BytesIO()
    stderr = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    log_dir = tmp_path / "logs"

    def configure_logging(**kwargs):
        if stderr_available:
            assert sys.stderr.encoding == "utf-8"
        LogManager(log_dir=kwargs["log_dir"], log_level=kwargs["log_level"])

    try:
        with monkeypatch.context() as patch:
            patch.setattr(sys, "platform", "win32")
            patch.setattr(sys, "stdout", None)
            patch.setattr(sys, "stderr", stderr if stderr_available else None)
            patch.setattr(entrypoint, "default_log_dir", lambda: str(log_dir))
            patch.setattr(entrypoint, "setup_logging", configure_logging)
            patch.setattr(entrypoint, "get_logger", logging.getLogger)
            patch.setattr(entrypoint, "run_gui_mode", lambda config, cwd: 0)
            assert entrypoint.gui_main([]) == 0
            for handler in root.handlers:
                handler.flush()
            if stderr_available:
                assert "启动桌面界面" in buffer.getvalue().decode("utf-8")
            else:
                assert all(isinstance(h, logging.FileHandler) for h in root.handlers)
            assert any(
                "启动桌面界面" in path.read_text("utf-8")
                for path in log_dir.glob("*.log")
            )
    finally:
        for handler in list(root.handlers):
            if handler not in previous_handlers:
                root.removeHandler(handler)
                handler.close()
        root.handlers = previous_handlers
        root.setLevel(previous_level)
        stderr.close()
