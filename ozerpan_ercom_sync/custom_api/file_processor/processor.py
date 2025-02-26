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

    def process_file(self, file_url: str) -> Dict[str, Any]:
        try:
            try:
                print("\n\n\n")
                print("File URL:", file_url)
                print("\n\n\n")
                file_doc = frappe.get_doc("File", {"file_url": file_url})
            except frappe.DoesNotExistError:
                raise ValueError(_("File not found"))

            file_info = ExcelFileInfo.from_filename(file_doc.file_name, file_url)

            processor = self._processors.get(file_info.file_type)
            if not processor:
                raise ValueError(
                    _(f"No processor found for file type: {file_info.file_type}")
                )

            processor.validate(file_info)

            file_path = frappe.get_site_path() + file_url
            if not os.path.exists(file_path):
                raise ValueError(_("File not found on server"))

            with open(file_path, "rb") as f:
                file_content = f.read()

            result = processor.process(file_info, file_content)

            return {
                "status": "success",
                "message": _("File processed successfully"),
                "file_type": file_info.file_type.value,
                "order_no": file_info.order_no,
                **result,
            }

        except ValueError as e:
            return {"status": "error", "message": str(e), "error_type": "validation"}
        except Exception as e:
            frappe.log_error(f"Error processing file: {str(e)}", "Excel Processing Error")
            return {"status": "error", "message": str(e), "error_type": "system"}
