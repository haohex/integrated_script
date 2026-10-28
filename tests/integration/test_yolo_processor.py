import json
from pathlib import Path
from typing import Tuple

import pytest

from integrated_script.config.settings import ConfigManager
from integrated_script.processors import yolo_processor as yolo_processor_module
from integrated_script.processors.yolo import merge as yolo_merge_module
from integrated_script.processors.yolo_processor import YOLOProcessor


def _build_processor(tmp_path: Path) -> YOLOProcessor:
    config = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    config.set("paths.log_dir", str(tmp_path / "logs"))
    return YOLOProcessor(config=config)


def _create_basic_yolo_dataset(dataset: Path) -> Tuple[Path, Path]:
    images = dataset / "images"
    labels = dataset / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    return images, labels


def _create_basic_ctds_dataset(dataset: Path) -> None:
    obj_train_data = dataset / "obj_train_data"
    obj_train_data.mkdir(parents=True)

    (dataset / "obj.names").write_text("car\n", encoding="utf-8")
    (obj_train_data / "sample.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (obj_train_data / "sample.jpg").write_text("img", encoding="utf-8")


def _create_basic_ctds_segmentation_dataset(dataset: Path) -> None:
    obj_train_data = dataset / "obj_train_data"
    obj_train_data.mkdir(parents=True)

    (dataset / "obj.names").write_text("car\n", encoding="utf-8")
    (obj_train_data / "sample.txt").write_text(
        "0 0.1 0.1 0.2 0.2 0.3 0.3\n", encoding="utf-8"
    )
    (obj_train_data / "sample.jpg").write_text("img", encoding="utf-8")


def test_get_dataset_statistics_accepts_labels_subdir_path(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    images, labels = _create_basic_yolo_dataset(dataset)

    (images / "a.jpg").write_text("img", encoding="utf-8")
    (labels / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (dataset / "classes.txt").write_text("cat\n", encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor.get_dataset_statistics(str(labels))

    stats = result["statistics"]
    assert stats["dataset_path"] == str(dataset)
    assert stats["original_path"] == str(labels)
    assert stats["is_valid"] is True
    assert stats["has_classes_file"] is True
    assert stats["num_classes"] == 1
    assert stats["class_names"] == ["cat"]


def test_detect_yolo_dataset_type_returns_detection_for_bbox_labels(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    images, labels = _create_basic_yolo_dataset(dataset)

    (images / "a.jpg").write_text("img", encoding="utf-8")
    (labels / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor.detect_yolo_dataset_type(str(dataset))

    assert result["detected_type"] == "detection"
    assert result["statistics"]["total_files"] == 1
    assert result["statistics"]["detection_files"] == 1
    assert result["statistics"]["segmentation_files"] == 0


def test_detect_yolo_dataset_type_returns_segmentation_for_polygon_labels(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    images, labels = _create_basic_yolo_dataset(dataset)

    (images / "a.jpg").write_text("img", encoding="utf-8")
    (labels / "a.txt").write_text("0 0.1 0.1 0.2 0.2 0.3 0.3\n", encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor.detect_yolo_dataset_type(str(dataset))

    assert result["detected_type"] == "segmentation"
    assert result["statistics"]["detection_files"] == 0
    assert result["statistics"]["segmentation_files"] == 1


def test_detect_xlabel_dataset_type_reports_segmentation_like_shapes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "xlabel"
    source.mkdir(parents=True)

    payload = {
        "shapes": [
            {
                "label": "car",
                "shape_type": "polygon",
                "points": [[1, 1], [2, 1], [2, 2], [1, 2]],
            }
        ]
    }
    (source / "sample.json").write_text(json.dumps(payload), encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor.detect_xlabel_dataset_type(str(source))

    assert result["detected_type"] == "segmentation"
    assert result["statistics"]["segmentation_like"] == 1
    assert result["statistics"]["detection_like"] == 0


def test_process_ctds_dataset_returns_pre_detection_stage_before_confirmation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ctds"
    _create_basic_ctds_dataset(source)

    processor = _build_processor(tmp_path)
    result = processor.process_ctds_dataset(str(source), output_name="demo")

    assert result["success"] is True
    assert result["stage"] == "pre_detection"
    assert result["pre_detection_result"]["success"] is True
    assert result["pre_detection_result"]["dataset_type"] == "detection"
    assert not (tmp_path / "demo").exists()


def test_continue_ctds_processing_produces_output_after_confirmation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ctds"
    _create_basic_ctds_dataset(source)

    processor = _build_processor(tmp_path)
    pre_result = processor.process_ctds_dataset(str(source), output_name="demo")
    result = processor.continue_ctds_processing(pre_result, confirmed_type="detection")

    output_path = Path(result["output_path"])

    assert result["success"] is True
    assert result["detected_dataset_type"] == "detection"
    assert result["statistics"]["final_count"] == 1
    assert output_path.exists()
    assert (output_path / "images").exists()
    assert (output_path / "labels").exists()
    assert len(list((output_path / "images").glob("*.jpg"))) == 1
    assert len(list((output_path / "labels").glob("*.txt"))) == 1
    assert (output_path / "classes.txt").exists()
    assert not (source / "obj_train_data" / "sample.jpg").exists()
    assert not (source / "obj_train_data" / "sample.txt").exists()


def test_continue_ctds_processing_supports_segmentation_confirmation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ctds-seg"
    _create_basic_ctds_segmentation_dataset(source)

    processor = _build_processor(tmp_path)
    pre_result = processor.process_ctds_dataset(str(source), output_name="demo-seg")
    assert pre_result["stage"] == "pre_detection"

    result = processor.continue_ctds_processing(
        pre_result, confirmed_type="segmentation"
    )
    output_path = Path(result["output_path"])

    assert result["success"] is True
    assert result["detected_dataset_type"] == "segmentation"
    assert result["statistics"]["final_count"] == 1
    assert output_path.exists()
    assert len(list((output_path / "images").glob("*.jpg"))) == 1
    assert len(list((output_path / "labels").glob("*.txt"))) == 1


def test_clean_unmatched_files_dry_run_collects_orphans_without_deleting(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    images, labels = _create_basic_yolo_dataset(dataset)

    orphan_image = images / "only_image.jpg"
    matched_image = images / "match.jpg"
    orphan_label = labels / "only_label.txt"
    matched_label = labels / "match.txt"

    orphan_image.write_text("img", encoding="utf-8")
    matched_image.write_text("img", encoding="utf-8")
    orphan_label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    matched_label.write_text("0 0.4 0.4 0.2 0.2\n", encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor.clean_unmatched_files(str(dataset), dry_run=True)

    dry_run_deleted_images = {
        Path(path).name for path in result["deleted_files"]["orphaned_images"]
    }
    dry_run_deleted_labels = {
        Path(path).name for path in result["deleted_files"]["orphaned_labels"]
    }

    assert result["success"] is True
    assert "only_image.jpg" in dry_run_deleted_images
    assert "only_label.txt" in dry_run_deleted_labels
    assert orphan_image.exists()
    assert orphan_label.exists()


def test_clean_unmatched_files_deletes_orphans_when_not_dry_run(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    images, labels = _create_basic_yolo_dataset(dataset)

    orphan_image = images / "only_image.jpg"
    matched_image = images / "match.jpg"
    orphan_label = labels / "only_label.txt"
    matched_label = labels / "match.txt"

    orphan_image.write_text("img", encoding="utf-8")
    matched_image.write_text("img", encoding="utf-8")
    orphan_label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    matched_label.write_text("0 0.4 0.4 0.2 0.2\n", encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor.clean_unmatched_files(str(dataset), dry_run=False)

    assert result["success"] is True
    assert not orphan_image.exists()
    assert not orphan_label.exists()
    assert matched_image.exists()
    assert matched_label.exists()


def test_clean_unmatched_files_handles_empty_labels_in_dry_run(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    images, labels = _create_basic_yolo_dataset(dataset)

    (images / "a.jpg").write_text("img", encoding="utf-8")
    empty_label = labels / "a.txt"
    empty_label.write_text("\n", encoding="utf-8")

    processor = _build_processor(tmp_path)
    result = processor.clean_unmatched_files(str(dataset), dry_run=True)

    dry_run_empty = {
        Path(path).name for path in result["deleted_files"]["empty_labels"]
    }

    assert result["success"] is True
    assert "a.txt" in dry_run_empty
    assert empty_label.exists()


def _create_yolo_dataset_with_classes(
    dataset: Path,
    classes: list[str],
    samples: list[tuple[str, int]],
) -> None:
    images, labels = _create_basic_yolo_dataset(dataset)
    (dataset / "classes.txt").write_text("\n".join(classes) + "\n", encoding="utf-8")

    for stem, class_id in samples:
        (images / f"{stem}.jpg").write_text("img", encoding="utf-8")
        (labels / f"{stem}.txt").write_text(
            f"{class_id} 0.5 0.5 0.2 0.2\n", encoding="utf-8"
        )


def test_merge_datasets_merges_same_classes_and_copies_files(tmp_path: Path) -> None:
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    _create_yolo_dataset_with_classes(d1, ["car", "bus"], [("a", 0)])
    _create_yolo_dataset_with_classes(d2, ["car", "bus"], [("b", 1)])

    processor = _build_processor(tmp_path)
    result = processor.merge_datasets(
        [str(d1), str(d2)],
        str(tmp_path / "out"),
        output_name="merged",
        image_prefix="img",
    )

    assert result["success"] is True
    assert result["merged_datasets"] == 2
    assert result["total_images"] == 2
    assert result["total_labels"] == 2

    output_dir = Path(result["output_path"])
    assert output_dir.exists()
    assert (output_dir / "classes.txt").exists()
    assert len(list((output_dir / "images").glob("*.jpg"))) == 2
    assert len(list((output_dir / "labels").glob("*.txt"))) == 2


def test_merge_datasets_output_name_generation_and_merge_reuse_scanned_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    _create_yolo_dataset_with_classes(d1, ["car", "bus"], [("a", 0)])
    _create_yolo_dataset_with_classes(d2, ["car", "bus"], [("b", 1)])

    scanned_manifest: list[list[Path]] = []

    original_get_file_list = yolo_merge_module.get_file_list

    def recording_get_file_list(*args, **kwargs):
        files = original_get_file_list(*args, **kwargs)
        path_arg = Path(args[0]) if args else Path(kwargs["directory"])
        extensions = args[1] if len(args) > 1 else kwargs.get("extensions")
        recursive = args[2] if len(args) > 2 else kwargs.get("recursive", False)
        normalized_ext = [ext.lower() for ext in extensions] if extensions else []

        if recursive and set(normalized_ext) == {".jpg", ".jpeg", ".png", ".bmp"}:
            if path_arg in {d1, d2}:
                scanned_manifest.append(files)

        return files

    monkeypatch.setattr(yolo_merge_module, "get_file_list", recording_get_file_list)

    processor = _build_processor(tmp_path)

    used_manifest_ids: list[int] = []
    used_manifest_sizes: list[int] = []

    original_generate_output_name_internal = (
        yolo_merge_module.generate_output_name_internal
    )

    def wrapped_generate_output_name_internal(
        _processor,
        classes,
        dataset_paths,
        image_manifest=None,
    ):
        output_name = original_generate_output_name_internal(
            _processor,
            classes,
            dataset_paths,
            image_manifest=image_manifest,
        )
        if image_manifest:
            used_manifest_ids.extend(id(files) for files in image_manifest)
            used_manifest_sizes.extend(len(files) for files in image_manifest)
        return output_name

    monkeypatch.setattr(
        yolo_processor_module,
        "generate_output_name_internal",
        wrapped_generate_output_name_internal,
    )

    result = processor.merge_datasets(
        [str(d1), str(d2)],
        str(tmp_path / "out"),
        output_name=None,
        image_prefix="img",
    )

    assert result["success"] is True
    assert result["merged_datasets"] == 2
    assert result["total_images"] == 2
    assert result["total_labels"] == 2
    assert len(scanned_manifest) == 2
    assert len(used_manifest_sizes) == 2
    assert used_manifest_sizes == [1, 1]
    assert used_manifest_ids
    assert {id(files) for files in scanned_manifest} == set(used_manifest_ids)


def test_continue_ctds_processing_reports_out_of_bounds_and_missing_file_stats(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ctds-invalid"
    obj_train_data = source / "obj_train_data"
    obj_train_data.mkdir(parents=True)

    (source / "obj.names").write_text("car\n", encoding="utf-8")
    (obj_train_data / "valid.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (obj_train_data / "valid.jpg").write_text("img", encoding="utf-8")
    (obj_train_data / "out_of_bounds.txt").write_text(
        "0 1.2 0.5 0.2 0.2\n", encoding="utf-8"
    )
    (obj_train_data / "out_of_bounds.jpg").write_text("img", encoding="utf-8")
    (obj_train_data / "missing_image.txt").write_text(
        "0 0.4 0.4 0.2 0.2\n", encoding="utf-8"
    )
    (obj_train_data / "image_only.jpg").write_text("img", encoding="utf-8")

    processor = _build_processor(tmp_path)
    pre_result = processor.process_ctds_dataset(str(source), output_name="demo")
    result = processor.continue_ctds_processing(pre_result, confirmed_type="detection")

    output_path = Path(result["output_path"])
    stats = result["statistics"]
    invalid_details = result["invalid_details"]

    assert result["success"] is True
    assert stats["total_processed"] == 4
    assert stats["final_count"] == 1
    assert stats["invalid_removed"] == 3
    assert stats["out_of_bounds_labels"] == 1
    assert stats["missing_images"] == 1
    assert stats["missing_labels"] == 1
    assert {Path(path).name for path in invalid_details["out_of_bounds_labels"]} == {
        "out_of_bounds.txt"
    }
    assert {Path(path).name for path in invalid_details["missing_images"]} == {
        "missing_image.txt"
    }
    assert {Path(path).name for path in invalid_details["missing_labels"]} == {
        "image_only.jpg"
    }
    assert output_path.exists()
    assert len(list((output_path / "images").glob("*.jpg"))) == 1
    assert len(list((output_path / "labels").glob("*.txt"))) == 1


def test_continue_ctds_processing_does_not_count_malformed_label_as_out_of_bounds(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ctds-malformed"
    obj_train_data = source / "obj_train_data"
    obj_train_data.mkdir(parents=True)

    (source / "obj.names").write_text("car\n", encoding="utf-8")
    (obj_train_data / "bad_format.txt").write_text("0 0.5 0.5 0.2\n", encoding="utf-8")
    (obj_train_data / "bad_format.jpg").write_text("img", encoding="utf-8")

    processor = _build_processor(tmp_path)
    pre_result = processor.process_ctds_dataset(str(source), output_name="demo")
    result = processor.continue_ctds_processing(pre_result, confirmed_type="detection")

    assert result["success"] is True
    assert result["statistics"]["invalid_removed"] == 1
    assert result["statistics"]["out_of_bounds_labels"] == 0
    assert result["invalid_details"]["out_of_bounds_labels"] == []
    assert {
        Path(path).name for path in result["invalid_details"]["invalid_labels"]
    } == {"bad_format.txt"}


def test_ctds_processing_reads_each_label_file_once_when_dropping_empty_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "ctds"
    _create_basic_ctds_dataset(source)

    processor = _build_processor(tmp_path)

    read_count: dict[Path, int] = {}
    original_validate = processor._validate_ctds_label_file

    def wrapped_validate(label_file: Path, dataset_type: str = "detection"):
        read_count[label_file] = read_count.get(label_file, 0) + 1
        return original_validate(label_file, dataset_type)

    monkeypatch.setattr(processor, "_validate_ctds_label_file", wrapped_validate)

    pre_result = processor.process_ctds_dataset(str(source), output_name="demo")
    result = processor.continue_ctds_processing(
        pre_result,
        confirmed_type="detection",
        keep_empty_labels=False,
    )

    assert result["success"] is True
    assert read_count
    assert all(count == 1 for count in read_count.values())


def test_convert_yolo_to_ctds_builds_images_index_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = tmp_path / "dataset"
    images, labels = _create_basic_yolo_dataset(dataset)

    (dataset / "classes.txt").write_text("car\n", encoding="utf-8")
    for idx in range(3):
        stem = f"item_{idx}"
        (images / f"{stem}.jpg").write_text("img", encoding="utf-8")
        (labels / f"{stem}.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    processor = _build_processor(tmp_path)

    index_build_count = {"count": 0}
    original_build_index = processor._build_images_index

    def wrapped_build_index(directory: Path):
        index_build_count["count"] += 1
        return original_build_index(directory)

    monkeypatch.setattr(processor, "_build_images_index", wrapped_build_index)

    result = processor.convert_yolo_to_ctds_dataset(str(dataset))

    assert result["success"] is True
    assert result["statistics"]["labels_copied"] == 3
    assert result["statistics"]["images_copied"] == 3
    assert index_build_count["count"] == 1
