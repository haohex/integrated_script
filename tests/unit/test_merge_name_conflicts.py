"""合并文件名策略的回归测试。"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from integrated_script.config.exceptions import DatasetError
from integrated_script.processors.yolo_processor import YOLOProcessor
from integrated_script.ui.interactive import InteractiveInterface
from integrated_script.workflows.yolo_workflow import YoloWorkflow


def make_dataset(root, name, image, classes="cat", class_id=0):
    path = root / name
    (path / "images").mkdir(parents=True)
    (path / "labels").mkdir()
    (path / "classes.txt").write_text(classes + "\n")
    (path / "images" / image).write_bytes(b"image")
    (path / "labels" / (Path(image).stem + ".txt")).write_text(
        f"{class_id} 0.5 0.5 0.2 0.2\n"
    )
    return path


@pytest.mark.parametrize(
    "second,conflict",
    [("other.jpg", False), ("one.jpg", True), ("ONE.jpg", True), ("one.png", True)],
)
def test_detect_conflicts(tmp_path, second, conflict):
    first = make_dataset(tmp_path, "a", "one.jpg")
    other = make_dataset(tmp_path, "b", second)
    result = YoloWorkflow(YOLOProcessor()).detect_name_conflicts([first, other])
    assert result == {
        "has_conflict": conflict,
        "conflict_count": int(conflict),
        "examples": ["one"] if conflict else [],
    }


def test_internal_directory_conflict(tmp_path):
    path = make_dataset(tmp_path, "a", "one.jpg")
    (path / "nested").mkdir()
    (path / "nested" / "one.png").write_bytes(b"image")
    assert YOLOProcessor().detect_name_conflicts([path])["conflict_count"] == 1


@pytest.mark.parametrize("different", [False, True])
@pytest.mark.parametrize("prefix", [None, "sample"])
def test_merge_names_and_labels(tmp_path, different, prefix):
    first = make_dataset(tmp_path, "a", "one.jpg")
    second = make_dataset(tmp_path, "b", "two.png", "dog" if different else "cat")
    processor = YOLOProcessor()
    method = (
        processor.merge_different_type_datasets
        if different
        else processor.merge_datasets
    )
    result = method([str(first), str(second)], str(tmp_path), "out", prefix)
    assert result["success"]
    output = tmp_path / "out"
    expected = (
        ["one.jpg", "two.png"]
        if prefix is None
        else ["sample_00001.jpg", "sample_00002.png"]
    )
    assert sorted(p.name for p in (output / "images").iterdir()) == expected
    for index, name in enumerate(expected):
        label = output / "labels" / (Path(name).stem + ".txt")
        assert label.read_text().startswith(f"{int(different and index == 1)} ")


@pytest.mark.parametrize("different", [False, True])
def test_conflict_refuses_before_output(tmp_path, different):
    first = make_dataset(tmp_path, "a", "one.jpg")
    second = make_dataset(tmp_path, "b", "ONE.png")
    processor = YOLOProcessor()
    method = (
        processor.merge_different_type_datasets
        if different
        else processor.merge_datasets
    )
    with pytest.raises(DatasetError, match="文件名冲突"):
        method([str(first), str(second)], str(tmp_path), "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("different", [False, True])
@pytest.mark.parametrize("mode", ["none", "cancel", "prefix"])
def test_interactive_merge_prefix_flow(tmp_path, monkeypatch, capsys, different, mode):
    paths = [
        make_dataset(tmp_path, "a", "one.jpg"),
        make_dataset(tmp_path, "b", "two.jpg"),
    ]
    processor = YOLOProcessor()
    workflow = YoloWorkflow(processor)
    workflow.detect_name_conflicts = Mock(
        return_value={
            "has_conflict": mode != "none",
            "conflict_count": int(mode != "none"),
            "examples": ["one"],
        }
    )
    merge = Mock(return_value={"success": False, "error": "test"})
    workflow.merge_datasets = merge
    workflow.merge_different_type_datasets = merge
    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", lambda _: workflow
    )
    interface = InteractiveInterface.__new__(InteractiveInterface)
    monkeypatch.setattr(interface, "_get_processor", lambda _: processor)
    monkeypatch.setattr(interface, "_pause", Mock())
    monkeypatch.setattr(
        interface, "_get_yes_no_input", lambda prompt, default: "确认" in prompt
    )
    answers = [str(p) for p in paths] + [""]
    if mode == "cancel":
        answers += [""]
    else:
        if mode == "prefix":
            answers += ["bad/name", "chosen"]
        answers += ["", "out"]
    inputs = iter(answers)
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return next(inputs)

    monkeypatch.setattr("builtins.input", answer)
    method = (
        interface._yolo_merge_different_datasets
        if different
        else interface._yolo_merge_datasets
    )
    method()
    output = capsys.readouterr().out
    if mode == "cancel":
        merge.assert_not_called()
        assert "操作已取消" in output
        assert not any("输出路径" in p for p in prompts)
    else:
        assert merge.call_args.kwargs["image_prefix"] == (
            "chosen" if mode == "prefix" else None
        )
        if mode == "none":
            assert not any("图片前缀" in p for p in prompts)
            assert "保留原文件名" in output
        else:
            assert "非法文件名字符" in output


@pytest.mark.parametrize("different", [False, True])
def test_merge_preserves_uppercase_label_filename(tmp_path, different):
    first = make_dataset(tmp_path, "a", "one.jpg")
    second = make_dataset(tmp_path, "b", "two.png")
    expected = {}
    for path, stem in [(first, "one"), (second, "two")]:
        source = path / "labels" / f"{stem}.txt"
        label = source.with_suffix(".TXT")
        source.rename(label)
        expected[label.name] = label.read_bytes()
    processor = YOLOProcessor()
    method = (
        processor.merge_different_type_datasets
        if different
        else processor.merge_datasets
    )
    result = method([str(first), str(second)], str(tmp_path), "out")
    assert result["success"]
    labels = tmp_path / "out" / "labels"
    assert {p.name: p.read_bytes() for p in labels.iterdir()} == expected


def test_workflow_normalizes_conflict_scan_error():
    processor = Mock()
    processor.detect_name_conflicts.side_effect = DatasetError("扫描失败")
    result = YoloWorkflow(processor).detect_name_conflicts([Path("dataset")])
    assert result["success"] is False
    assert "扫描失败" in result["error"]
    assert result["error_code"]


@pytest.mark.parametrize("different", [False, True])
def test_interactive_conflict_scan_failure(tmp_path, monkeypatch, capsys, different):
    paths = [
        make_dataset(tmp_path, "a", "one.jpg"),
        make_dataset(tmp_path, "b", "two.jpg"),
    ]
    processor = YOLOProcessor()
    monkeypatch.setattr(
        processor, "detect_name_conflicts", Mock(side_effect=DatasetError("扫描失败"))
    )
    merge = Mock()
    monkeypatch.setattr(processor, "merge_datasets", merge)
    monkeypatch.setattr(processor, "merge_different_type_datasets", merge)
    interface = InteractiveInterface.__new__(InteractiveInterface)
    monkeypatch.setattr(interface, "_get_processor", lambda _: processor)
    pause = Mock()
    monkeypatch.setattr(interface, "_pause", pause)
    monkeypatch.setattr(interface, "_get_yes_no_input", lambda *args, **kwargs: False)
    inputs = iter([str(p) for p in paths] + [""])
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return next(inputs)

    monkeypatch.setattr("builtins.input", answer)
    method = (
        interface._yolo_merge_different_datasets
        if different
        else interface._yolo_merge_datasets
    )
    method()
    output = capsys.readouterr().out
    assert "文件名冲突检测失败" in output
    assert "扫描失败" in output
    assert "has_conflict" not in output
    assert not any("输出路径" in prompt for prompt in prompts)
    merge.assert_not_called()
    pause.assert_called_once_with()
