from typing import Any, Dict, Optional, TypedDict

import frappe
from frappe import _

from .barcode_reader.exceptions import (
    BarcodeError,
    InvalidBarcodeError,
    QualityControlError,
)
from .barcode_reader.reader import BarcodeReader
from .file_processor.processor import ExcelProcessingManager


@frappe.whitelist()
def process_excel_file(file_url: str) -> Dict[str, Any]:
    print("\n\n\n")
    print("--- File Processor ---")

    try:
        if not file_url:
            return {
                "status": "error",
                "message": _("No file URL provided"),
                "error_type": "Validation",
            }

        manager = ExcelProcessingManager()
        result = manager.process_file(file_url)

        print("\n\n\n")
        return result

    except Exception as e:
        frappe.log_error(
            f"Error in file processing: {str(e)}", "File Processing API Error"
        )
        return {
            "status": "error",
            "message": _("Unexpected error occured"),
            "error_type": "system",
        }


class BarcodeRequest(TypedDict):
    barcode: str
    employee: str
    operation: str
    quality_data: Optional[Dict[str, Any]]


@frappe.whitelist()
def read_barcode(
    barcode: str, employee: str, operation: str, quality_data: Optional[Dict] = None
) -> Dict[str, Any]:
    try:
        print("\n\n\n")
        print("--- Read Barcode ---")
        reader = BarcodeReader()
        result = reader.read_barcode(
            barcode=barcode,
            employee=employee,
            operation=operation,
            quality_data=quality_data,
        )
        print("\n\n\n")
        return result
    except QualityControlError as e:
        return {
            "status": "error",
            "message": str(e.message),
            "error_type": e.error_type,
            **(e.data or {}),
        }
    except InvalidBarcodeError as e:
        return {"status": "error", "message": str(e), "error_type": "invalid_barcode"}
    except BarcodeError as e:
        return {"status": "error", "message": str(e), "error_type": "barcode_operation"}
    except Exception as e:
        frappe.log_error(f"Error reading barcode: {str(e)}", "Barcode Reader Error")
        return {
            "status": "error",
            "message": str(e),
            "error_type": "system",
        }
