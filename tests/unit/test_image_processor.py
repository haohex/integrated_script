from pathlib import Path

import pytest

from integrated_script.config.exceptions import PathError, ProcessingError
from integrated_script.config.settings import ConfigManager
from integrated_script.processors.image_processor import ImageProcessor


def _build_processor(tmp_path: Path, monkeypatch) -> ImageProcessor:
    monkeypatch.setattr(ImageProcessor, "_check_dependencies", lambda self: None)

    config = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    config.set("paths.log_dir", str(tmp_path / "logs"))
    return ImageProcessor(config=config)


def test_init_raises_when_no_image_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        "integrated_script.processors.image_processor.CV2_AVAILABLE", False
    )
    monkeypatch.setattr(
        "integrated_script.processors.image_processor.PIL_AVAILABLE", False
    )

    with pytest.raises(ProcessingError):
        ImageProcessor()


def test_normalize_extensions_formats_values(tmp_path: Path, monkeypatch) -> None:
    processor = _build_processor(tmp_path, monkeypatch)

    normalized = processor._normalize_extensions(["JPG", " .png ", "", 123])

    assert normalized == [".jpg", ".png"]


def test_convert_format_single_file_returns_stats(tmp_path: Path, monkeypatch) -> None:
    input_file = tmp_path / "input.jpg"
    output_file = tmp_path / "output.png"
    input_file.write_bytes(b"source")

    processor = _build_processor(tmp_path, monkeypatch)

    def fake_convert(_input: Path, output: Path, _target: str, _quality: int) -> None:
        output.write_bytes(b"converted")

    monkeypatch.setattr(processor, "_convert_single_image", fake_convert)

    result = processor.convert_format(
        input_path=str(input_file),
        target_format="png",
        output_path=str(output_file),
        quality=90,
    )

    assert result["success"] is True
    assert result["statistics"]["converted_count"] == 1
    assert output_file.exists()


def test_resize_images_single_file_returns_size_change(
    tmp_path: Path, monkeypatch
) -> None:
    input_file = tmp_path / "input.jpg"
    output_file = tmp_path / "resized.jpg"
    input_file.write_bytes(b"source")

    processor = _build_processor(tmp_path, monkeypatch)

    sizes = iter([(200, 100), (100, 50)])

    def fake_get_image_size(_path: Path) -> tuple[int, int]:
        return next(sizes)

    def fake_resize(
        _input: Path, output: Path, _target: tuple[int, int], _keep: bool
    ) -> None:
        output.write_bytes(b"resized")

    monkeypatch.setattr(processor, "_get_image_size", fake_get_image_size)
    monkeypatch.setattr(processor, "_resize_single_image", fake_resize)

    result = processor.resize_images(
        input_dir=str(input_file),
        output_dir=str(output_file),
        target_size=(100, 50),
        maintain_aspect_ratio=True,
    )

    assert result["success"] is True
    assert result["original_size"] == (200, 100)
    assert result["new_size"] == (100, 50)
    assert output_file.exists()


def test_compress_images_raises_path_error_when_input_path_invalid(
    tmp_path: Path, monkeypatch
) -> None:
    processor = _build_processor(tmp_path, monkeypatch)

    with pytest.raises(PathError):
        processor.compress_images(str(tmp_path / "missing.jpg"), quality=80)
