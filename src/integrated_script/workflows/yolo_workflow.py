from typing import Any, Dict, List, Optional, Set

from ..contracts.errors import NormalizedError, normalize_exception
from ..contracts.results import OperationResult


class YoloWorkflow:
    """YOLO 相关 workflow 适配层。

    Phase 1 目标：
    - 对内可使用统一 contracts
    - 对外继续返回 legacy dict（不破坏现有 UI）
    """

    def __init__(self, processor: Any):
        self.processor = processor

    def process_ctds_dataset(
        self,
        input_path: str,
        output_name: Optional[str] = None,
        keep_empty_labels: bool = False,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.process_ctds_dataset(
                input_path,
                output_name=output_name,
                keep_empty_labels=keep_empty_labels,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def continue_ctds_processing(
        self,
        pre_result: Dict[str, Any],
        confirmed_type: str,
        keep_empty_labels: Optional[bool] = None,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.continue_ctds_processing(
                pre_result,
                confirmed_type,
                keep_empty_labels=keep_empty_labels,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def convert_yolo_to_ctds_dataset(
        self,
        dataset_path: str,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.convert_yolo_to_ctds_dataset(
                dataset_path,
                output_path=output_path,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def detect_yolo_dataset_type(self, dataset_path: str) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.detect_yolo_dataset_type(dataset_path)
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def convert_yolo_to_xlabel(
        self,
        dataset_path: str,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.convert_yolo_to_xlabel(
                dataset_path,
                output_dir=output_dir,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def convert_yolo_to_xlabel_segmentation(
        self,
        dataset_path: str,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.convert_yolo_to_xlabel_segmentation(
                dataset_path,
                output_dir=output_dir,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def detect_xlabel_dataset_type(self, source_dir: str) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.detect_xlabel_dataset_type(source_dir)
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def detect_xlabel_classes(self, source_dir: str) -> Set[str]:
        return self.processor.detect_xlabel_classes(source_dir)

    def detect_xlabel_segmentation_classes(self, source_dir: str) -> Set[str]:
        return self.processor.detect_xlabel_segmentation_classes(source_dir)

    def convert_xlabel_to_yolo(
        self,
        source_dir: str,
        output_dir: Optional[str] = None,
        class_order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.convert_xlabel_to_yolo(
                source_dir,
                output_dir=output_dir,
                class_order=class_order,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def convert_xlabel_to_yolo_segmentation(
        self,
        source_dir: str,
        output_dir: Optional[str] = None,
        class_order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.convert_xlabel_to_yolo_segmentation(
                source_dir,
                output_dir=output_dir,
                class_order=class_order,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def get_dataset_statistics(self, dataset_path: str) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.get_dataset_statistics(dataset_path)
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def clean_unmatched_files(
        self,
        dataset_path: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.clean_unmatched_files(
                dataset_path,
                dry_run=dry_run,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def detect_name_conflicts(self, dataset_paths: List[Any]) -> Dict[str, Any]:
        try:
            return self.processor.detect_name_conflicts(dataset_paths)
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def validate_classes_consistency(self, dataset_paths: List[Any]) -> Dict[str, Any]:
        try:
            legacy_result = self.processor._validate_classes_consistency(dataset_paths)
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def generate_output_name(
        self,
        classes: List[str],
        dataset_paths: List[Any],
    ) -> str:
        return self.processor._generate_output_name(
            classes=classes,
            dataset_paths=dataset_paths,
        )

    def merge_datasets(
        self,
        dataset_paths: List[Any],
        output_path: str,
        output_name: Optional[str] = None,
        image_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.merge_datasets(
                dataset_paths=dataset_paths,
                output_path=output_path,
                output_name=output_name,
                image_prefix=image_prefix,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def collect_all_classes_info(
        self, dataset_paths: List[Any]
    ) -> List[Dict[str, Any]]:
        return self.processor._collect_all_classes_info(dataset_paths)

    def create_unified_class_mapping(
        self,
        all_classes_info: List[Dict[str, Any]],
    ) -> Any:
        return self.processor._create_unified_class_mapping(all_classes_info)

    def generate_different_output_name(
        self,
        unified_classes: List[str],
        dataset_paths: List[Any],
    ) -> str:
        return self.processor._generate_different_output_name(
            unified_classes=unified_classes,
            dataset_paths=dataset_paths,
        )

    def merge_different_type_datasets(
        self,
        dataset_paths: List[str],
        output_path: str,
        output_name: Optional[str] = None,
        image_prefix: Optional[str] = None,
        dataset_order: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        try:
            legacy_result = self.processor.merge_different_type_datasets(
                dataset_paths=dataset_paths,
                output_path=output_path,
                output_name=output_name,
                image_prefix=image_prefix,
                dataset_order=dataset_order,
            )
            return OperationResult.from_legacy(legacy_result).to_legacy()
        except Exception as error:  # noqa: BLE001
            normalized = self._normalize_error(error)
            return self._legacy_failure(normalized)

    def _normalize_error(self, error: Exception) -> NormalizedError:
        return normalize_exception(error)

    def _legacy_failure(self, normalized: NormalizedError) -> Dict[str, Any]:
        return OperationResult.failure(
            message=normalized.message,
            error_code=normalized.code,
            payload={"error_details": normalized.details},
        ).to_legacy()
