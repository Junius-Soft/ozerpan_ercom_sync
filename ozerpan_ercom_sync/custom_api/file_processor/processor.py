import os
import logging
from typing import Any, Dict, List, Type

import frappe
from frappe import _

# Configure logging for database connection issues
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from .base import ExcelProcessorInterface
from .constants import ExcelFileType
from .handlers.glass_list_processor import GlassListProcessor
from .handlers.mly_list_processor import MLYListProcessor
from .models.excel_file_info import ExcelFileInfo


class ExcelProcessingManager:
    def __init__(self):
        self._processors: Dict[ExcelFileType, ExcelProcessorInterface] = {}
        # Ensure fresh database connection
        try:
            frappe.db.commit()
        except Exception as e:
            logging.warning(f"Database commit warning in ExcelProcessingManager init: {str(e)}")
        self._register_processors()

    def _register_processors(self) -> None:
        processors: List[Type[ExcelProcessorInterface]] = [
            MLYListProcessor,
            GlassListProcessor,
        ]

        for processor_class in processors:
            # Create processor for each file type
            processor = processor_class()
            self._processors[processor.get_supported_file_type()] = processor
            
        # Make sure to commit any transactions after registration
        try:
            frappe.db.commit()
        except Exception as e:
            logging.warning(f"Database commit warning after processor registration: {str(e)}")

    def process_file(self, file_url: str, filename: str = None) -> Dict[str, Any]:
        try:
            # Ensure database connection is fresh before processing
            frappe.db.commit()
            
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

            # Process the file
            result = processor.process(file_info, file_content)
            
            # Commit database changes after successful processing
            frappe.db.commit()

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
                frappe.db.commit()  # Commit any pending transactions
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
            
            # Final commit before returning
            frappe.db.commit()
            return result_with_metadata

        except ValueError as e:
            # Make sure to commit any pending transactions
            try:
                frappe.db.commit()
            except:
                pass
                
            return {
                "status": "error",
                "message": str(e),
                "error_type": "validation",
                "filename": filename,
            }
        except Exception as e:
            # On error, try to rollback first
            try:
                frappe.db.rollback()
            except:
                pass
                
            frappe.log_error(
                f"Error processing file {filename}: {str(e)}", "Excel Processing Error"
            )
            
            # Then commit to release connection
            try:
                frappe.db.commit()
            except:
                pass
                
            return {
                "status": "error",
                "message": str(e),
                "error_type": "system",
                "filename": filename,
            }
