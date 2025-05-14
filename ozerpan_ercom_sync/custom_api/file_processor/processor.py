import os
from typing import Any, Dict, List, Type

import frappe
from frappe import _

from .base import ExcelProcessorInterface
from .constants import ExcelFileType
from .handlers.glass_list_processor import GlassListProcessor
from .handlers.mly_list_processor import MLYListProcessor
from .models.excel_file_info import ExcelFileInfo


class ExcelProcessingManager:
    def __init__(self):
        self._processors: Dict[ExcelFileType, ExcelProcessorInterface] = {}
        self._register_processors()

    def _register_processors(self) -> None:
        processors: List[Type[ExcelProcessorInterface]] = [
            MLYListProcessor,
            GlassListProcessor,
        ]

        for processor_class in processors:
            processor = processor_class()
            self._processors[processor.get_supported_file_type()] = processor

    def process_file(self, file_url: str, filename: str = None) -> Dict[str, Any]:
        try:
            print(f"\n\n-- Processing File: {filename} -- (START)")
            file_info = ExcelFileInfo.from_filename(filename, file_url)

            processor = self._processors.get(file_info.file_type)
            print(f"Using processor: {processor.__class__.__name__}")

            if not processor:
                raise ValueError(
                    _(f"No processor found for file type: {file_info.file_type}")
                )

            processor.validate(file_info)

            if not os.path.exists(file_url):
                raise ValueError(_("File not found on server"))

            with open(file_url, "rb") as f:
                file_content = f.read()

            result = processor.process(file_info, file_content)

            missing_items = result.get("missing_items", {})

            if missing_items:
                result_with_metadata = {
                    "status": "error",
                    "message": _("Processing failed due to missing required items"),
                    "error_type": "missing_items",
                    "order_no": file_info.order_no,
                    "filename": filename,
                    "missing_items": missing_items,
                }
                print(f"-- Processing File: {filename} -- Failed (Missing Items) --\n\n")
                return result_with_metadata

            result_with_metadata = {
                "status": "success",
                "message": _("File processed successfully"),
                "file_type": file_info.file_type.value,
                "order_no": file_info.order_no,
                "filename": filename,
            }

            for key, value in result.items():
                if key not in result_with_metadata:
                    result_with_metadata[key] = value
            print(f"-- Processing File: {filename} -- (END)\n\n")
            return result_with_metadata

        except ValueError as e:
            return {
                "status": "error",
                "message": str(e),
                "error_type": "validation",
                "filename": filename,
            }
        except Exception as e:
            frappe.log_error(
                f"Error processing file {filename}: {str(e)}", "Excel Processing Error"
            )
            return {
                "status": "error",
                "message": str(e),
                "error_type": "system",
                "filename": filename,
            }
