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
from .glass_processor.glass_processor import GlassOperationProcessor


class GlassOperationRequest(TypedDict):
    operation: str
    employee: str
    name: str


@frappe.whitelist()
def process_glass_operation() -> Dict[str, Any]:
    try:
        operation_data = frappe.form_dict

        if operation_data.get("operation") != "Cam":
            return {
                "status": "error",
                "message": _("Invalid operation type"),
                "error_type": "validation",
            }

        glass_item = find_glasses(operation_data)
        if not glass_item:
            return {
                "status": "error",
                "message": _("No matching glass item found"),
                "error_type": "validation",
            }

        glass_processor = GlassOperationProcessor()
        result = glass_processor.process(glass_item, operation_data["employee"])
        # frappe.throw("-- Process Glass Operation --")

        return {
            "status": "success",
            "message": _("Operation processed successfully"),
            "data": result,
        }

    except Exception as e:
        frappe.log_error(
            f"Error processing glass operation: {str(e)}", "Glass Operation Error"
        )
        return {"status": "error", "message": str(e), "error_type": "system"}


def find_glasses(data: GlassOperationRequest) -> Optional[Dict]:
    print("\n\n\n---Find Glasses---\n\n\n")
    current_glass = frappe.get_doc("CamListe Item", data["name"])
    if not current_glass:
        frappe.throw(_("Glass not found"))

    filters = {
        "parent": current_glass.parent,
        "poz_no": current_glass.poz_no,
    }

    related_glasses = frappe.get_all("CamListe Item", filters=filters, fields=["*"])

    return {"current_glass": current_glass, "related_glasses": related_glasses}


###########################


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
