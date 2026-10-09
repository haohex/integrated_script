# -*- coding: utf-8 -*-
"""应用层文件操作处理器的交互与语义回归。

覆盖本轮审查发现的实际缺陷：

* ``file.rename_single_dir`` 在后缀字段留空时必须沿用旧交互的自动检测，
  否则重命名会丢失文件扩展名；
* ``file.rename_images_labels`` / ``file.rename_images_labels_legacy`` 在旧
  交互中执行前会请求确认，应用层必须保留同一语义：拒绝时不得改动任何文件。

测试使用真实 workflow/processor 与临时目录，仅用最小 TaskContext 收集确认
与日志。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from integrated_script.application.contracts import ParameterSpec
from integrated_script.application.handlers.file import (
    handle_rename_images_labels,
    handle_rename_images_labels_legacy,
    handle_rename_single_dir,
)
from integrated_script.application.operations import TaskContext
from integrated_script.config.settings import ConfigManager


class RecordingContext(TaskContext):
    """记录确认/提问调用并通过 ``confirm_result`` / ``ask_result`` 应答。"""

    def __init__(
        self,
        config: ConfigManager,
        working_directory: Path,
        *,
        confirm_result: bool = True,
        ask_result: Any = False,
    ) -> None:
        super().__init__(config, working_directory)
        self.confirm_result = confirm_result
        self.ask_result = ask_result
        self.confirmations: List[tuple] = []
        self.asks: List[tuple] = []
        self.logs: List[str] = []

    def confirm(
        self,
        title: str,
        message: str,
        *,
        details: Sequence[str] = (),
        default: bool = False,
    ) -> bool:
        self.confirmations.append((title, message, tuple(details), default))
        return self.confirm_result

    def ask(
        self,
        title: str,
        message: str,
        fields: Sequence[ParameterSpec],
        *,
        kind: str = "input",
    ) -> Optional[Dict[str, Any]]:
        self.asks.append((title, message, tuple(fields), kind))
        if callable(self.ask_result):
            return self.ask_result(fields)
        if self.ask_result is False:
            return None
        return dict(self.ask_result or {})

    def log(self, message: str) -> None:
        self.logs.append(message)

    def progress(self, current: int, total: Optional[int], message: str = "") -> None:
        return None


def _config(tmp_path: Path) -> ConfigManager:
    config = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    config.set("paths.temp_dir", str(tmp_path / "temp"))
    config.set("paths.log_dir", str(tmp_path / "logs"))
    return config


def test_rename_single_dir_auto_detects_suffix_when_blank(tmp_path: Path) -> None:
    """后缀留空时沿用旧交互行为：自动检测目录后缀，不丢扩展名。"""
    work = tmp_path / "data"
    work.mkdir()
    for name in ("a.jpg", "b.jpg"):
        (work / name).write_text("x", encoding="utf-8")

    context = RecordingContext(_config(tmp_path), work)
    result = handle_rename_single_dir(
        context,
        {
            "source_dir": str(work),
            "prefix": "",
            "digits": 5,
            "suffix": "",
            "shuffle_order": False,
        },
    )

    assert result["success"] is True, result
    renamed = sorted(path.name for path in work.iterdir() if path.is_file())
    assert renamed == ["00001.jpg", "00002.jpg"], renamed
    assert context.asks == [], "自动检测到后缀时不应提问"


def test_rename_single_dir_mixed_suffixes_use_lexicographic_default(
    tmp_path: Path,
) -> None:
    """多个已存在后缀时保持旧语义：取字典序首个后缀且不提问。"""
    work = tmp_path / "data"
    work.mkdir()
    for name in ("a.png", "b.jpg", "c.bmp"):
        (work / name).write_text("x", encoding="utf-8")

    context = RecordingContext(_config(tmp_path), work)
    result = handle_rename_single_dir(
        context,
        {
            "source_dir": str(work),
            "prefix": "",
            "digits": 2,
            "suffix": "",
            "shuffle_order": False,
        },
    )

    assert result["success"] is True, result
    assert context.asks == []
    renamed = sorted(path.name for path in work.iterdir())
    assert renamed == ["01.bmp", "02.bmp", "03.bmp"], renamed


def test_rename_single_dir_asks_suffix_when_none_detected(tmp_path: Path) -> None:
    """目录中所有文件都无后缀时必须提问并采用用户输入的后缀。"""
    work = tmp_path / "data"
    work.mkdir()
    for name in ("alpha", "beta"):
        (work / name).write_text("x", encoding="utf-8")

    context = RecordingContext(_config(tmp_path), work, ask_result={"suffix": ".dat"})
    result = handle_rename_single_dir(
        context,
        {
            "source_dir": str(work),
            "prefix": "",
            "digits": 2,
            "suffix": "",
            "shuffle_order": False,
        },
    )

    assert result["success"] is True, result
    assert len(context.asks) == 1
    _, _, fields, _ = context.asks[0]
    assert fields[0].name == "suffix"
    renamed = sorted(path.name for path in work.iterdir())
    assert renamed == ["01.dat", "02.dat"], renamed


def test_rename_single_dir_cancelled_when_suffix_dialog_dismissed(
    tmp_path: Path,
) -> None:
    """用户关闭/拒绝后缀输入时不写文件、不进入确认步骤。"""
    work = tmp_path / "data"
    work.mkdir()
    for name in ("alpha", "beta"):
        (work / name).write_text("x", encoding="utf-8")

    context = RecordingContext(_config(tmp_path), work, ask_result=False)
    result = handle_rename_single_dir(
        context,
        {
            "source_dir": str(work),
            "prefix": "",
            "digits": 2,
            "suffix": "",
            "shuffle_order": False,
        },
    )

    assert result["success"] is True
    assert result["cancelled"] is True
    assert context.asks, "必须请求后缀"
    assert context.confirmations == [], "取消后不应再请求确认"
    assert sorted(path.name for path in work.iterdir()) == ["alpha", "beta"]


def test_rename_single_dir_blank_suffix_answer_cancels(tmp_path: Path) -> None:
    """输入空后缀同样视为取消，不重命名。"""
    work = tmp_path / "data"
    work.mkdir()
    (work / "alpha").write_text("x", encoding="utf-8")

    context = RecordingContext(_config(tmp_path), work, ask_result={"suffix": ""})
    result = handle_rename_single_dir(
        context,
        {
            "source_dir": str(work),
            "prefix": "",
            "digits": 2,
            "suffix": "",
            "shuffle_order": False,
        },
    )

    assert result["success"] is True
    assert result["cancelled"] is True
    assert [path.name for path in work.iterdir()] == ["alpha"]


def test_rename_single_dir_respects_explicit_suffix(tmp_path: Path) -> None:
    """显式后缀优先于自动检测。"""
    work = tmp_path / "data"
    work.mkdir()
    (work / "a.jpg").write_text("x", encoding="utf-8")

    context = RecordingContext(_config(tmp_path), work)
    result = handle_rename_single_dir(
        context,
        {
            "source_dir": str(work),
            "prefix": "img",
            "digits": 3,
            "suffix": ".png",
            "shuffle_order": False,
        },
    )

    assert result["success"] is True, result
    assert (work / "img_001.png").exists()
    assert not (work / "a.jpg").exists()


def test_rename_images_labels_requires_confirmation(tmp_path: Path) -> None:
    """拒绝确认时不得重命名任何 images/labels 文件。"""
    dataset = tmp_path / "ds"
    (dataset / "images").mkdir(parents=True)
    (dataset / "labels").mkdir(parents=True)
    for name in ("a.jpg", "b.jpg"):
        (dataset / "images" / name).write_text("x", encoding="utf-8")
        (dataset / "labels" / f"{Path(name).stem}.txt").write_text(
            "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
        )

    context = RecordingContext(_config(tmp_path), dataset, confirm_result=False)
    result = handle_rename_images_labels(
        context,
        {
            "source_dir": str(dataset),
            "prefix": "x",
            "digits": 5,
            "shuffle_order": False,
        },
    )

    assert result["success"] is True
    assert result["cancelled"] is True
    assert context.confirmations, "必须请求确认"
    assert sorted(path.name for path in (dataset / "images").iterdir()) == [
        "a.jpg",
        "b.jpg",
    ]


def test_rename_images_labels_renames_after_confirmation(tmp_path: Path) -> None:
    dataset = tmp_path / "ds"
    (dataset / "images").mkdir(parents=True)
    (dataset / "labels").mkdir(parents=True)
    for name in ("a.jpg", "b.jpg"):
        (dataset / "images" / name).write_text("x", encoding="utf-8")
        (dataset / "labels" / f"{Path(name).stem}.txt").write_text(
            "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
        )

    context = RecordingContext(_config(tmp_path), dataset, confirm_result=True)
    result = handle_rename_images_labels(
        context,
        {
            "source_dir": str(dataset),
            "prefix": "x",
            "digits": 5,
            "shuffle_order": False,
        },
    )

    assert result["success"] is True, result
    assert sorted(path.name for path in (dataset / "images").iterdir()) == [
        "x_00001.jpg",
        "x_00002.jpg",
    ]


def test_rename_images_labels_legacy_requires_confirmation(tmp_path: Path) -> None:
    """传统模式同样保留确认语义。"""
    dataset = tmp_path / "ds"
    (dataset / "images").mkdir(parents=True)
    (dataset / "labels").mkdir(parents=True)
    (dataset / "images" / "a.jpg").write_text("x", encoding="utf-8")
    (dataset / "labels" / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    context = RecordingContext(_config(tmp_path), dataset, confirm_result=False)
    result = handle_rename_images_labels_legacy(
        context,
        {
            "source_dir": str(dataset),
            "prefix": "",
            "shuffle_order": False,
        },
    )

    assert result["success"] is True
    assert result["cancelled"] is True
    assert context.confirmations
    assert [path.name for path in (dataset / "images").iterdir()] == ["a.jpg"]
