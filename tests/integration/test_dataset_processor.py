from pathlib import Path

from integrated_script.config.settings import ConfigManager
from integrated_script.processors.dataset_processor import DatasetProcessor


def _build_processor(tmp_path: Path) -> DatasetProcessor:
    config = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    config.set("paths.log_dir", str(tmp_path / "logs"))
    return DatasetProcessor(config=config)


def test_detect_dataset_root_returns_parent_for_images_subdir(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    images = dataset / "images"
    labels = dataset / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)

    processor = _build_processor(tmp_path)

    detected = processor._detect_dataset_root(images)

    assert detected == dataset


def test_validate_yolo_dataset_reports_orphaned_files(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    images = dataset / "images"
    labels = dataset / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)

    (images / "a.jpg").write_text("img", encoding="utf-8")
    (images / "b.jpg").write_text("img", encoding="utf-8")
    (labels / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (labels / "c.txt").write_text("0 0.6 0.6 0.2 0.2\n", encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor._validate_yolo_dataset(dataset, check_integrity=False)

    issue_types = {issue["type"] for issue in result["issues"]}
    assert result["success"] is False
    assert result["statistics"]["total_images"] == 2
    assert result["statistics"]["total_labels"] == 2
    assert result["statistics"]["matched_pairs"] == 1
    assert result["statistics"]["orphaned_images"] == 1
    assert result["statistics"]["orphaned_labels"] == 1
    assert "orphaned_images" in issue_types
    assert "orphaned_labels" in issue_types


def test_validate_yolo_dataset_integrity_flags_invalid_and_empty_labels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset = tmp_path / "dataset"
    images = dataset / "images"
    labels = dataset / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)

    (images / "a.jpg").write_text("img", encoding="utf-8")
    (images / "b.jpg").write_text("img", encoding="utf-8")
    (labels / "a.txt").write_text("0 1.2 0.5 0.2 0.2\n", encoding="utf-8")
    (labels / "b.txt").write_text("", encoding="utf-8")

    processor = _build_processor(tmp_path)

    monkeypatch.setattr(
        "integrated_script.processors.dataset_processor.process_with_progress",
        lambda items, func, _desc: [func(item) for item in items],
    )

    result = processor._validate_yolo_dataset(dataset, check_integrity=True)

    issues_by_type = {issue["type"]: issue for issue in result["issues"]}
    invalid_issue = issues_by_type["invalid_labels"]
    empty_issue = issues_by_type["empty_labels"]

    invalid_files = {Path(item["file"]).name for item in invalid_issue["examples"]}
    empty_files = {Path(file_path).name for file_path in empty_issue["files"]}

    assert result["success"] is False
    assert result["statistics"]["invalid_labels"] == 1
    assert result["statistics"]["empty_labels"] == 1
    assert "a.txt" in invalid_files
    assert "b.txt" in empty_files


def test_validate_yolo_dataset_returns_early_when_labels_missing(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    images = dataset / "images"
    images.mkdir(parents=True)
    (images / "a.jpg").write_text("img", encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor._validate_yolo_dataset(dataset, check_integrity=True)

    assert result["success"] is True
    assert result["issues"] == []
