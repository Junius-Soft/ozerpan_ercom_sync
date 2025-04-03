from typing import Any, Dict, List, Optional, TypedDict

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
from .glass_processor.types import GlassOperationRequest
from .services.surme_service import (
    fetch_surme_orders,
    fetch_surme_poz_details,
)


@frappe.whitelist()
def process_glass_operation() -> Dict[str, Any]:
    try:
        operation_data = frappe.form_dict

        if not _is_valid_operation(operation_data):
            return _create_error_response("Invalid operation type", "validation")

        glass_item = find_glasses(operation_data)
        if not glass_item:
            return _create_error_response("No matching glass item found", "validation")

        result = GlassOperationProcessor().process(operation_data)
        return _create_success_response("Operation processed successfully", result)

    except Exception as e:
        return _handle_operation_error(e)


def _is_valid_operation(operation_data: Dict) -> bool:
    return operation_data.get("operation") == "Cam"


def find_glasses(data: GlassOperationRequest) -> Optional[Dict]:
    current_glass = _get_current_glass(data["glass_name"])
    order_no = data["glass_name"].split("-")[0]
    related_glasses = _get_related_glasses(order_no, current_glass.poz_no)

    return {"current_glass": current_glass, "related_glasses": related_glasses}


def _get_current_glass(glass_name: str) -> Any:
    glass = frappe.get_doc("CamListe", glass_name)
    if not glass:
        frappe.throw(_("Glass not found"))
    return glass


def _get_related_glasses(order_no: str, poz_no: str) -> List[Dict]:
    filters = {"order_no": order_no, "poz_no": poz_no}
    return frappe.get_all("CamListe", filters=filters, fields=["*"])


###########################


@frappe.whitelist()
def get_surme_orders():
    print("\n\n\n-- Get Surme Orders --")
    form_data = frappe.form_dict
    order_no = form_data.order_no

    orders = fetch_surme_orders(order_no)

    print("\n\n\n")
    return {"orders": list(orders)}


@frappe.whitelist()
def get_surme_poz_by_order_no():
    print("\n\n\n-- Get Surme Poz By Order No --")
    form_data = frappe.form_dict
    order_no = form_data.order_no

    return fetch_surme_poz_details(order_no)


###########################


@frappe.whitelist()
def process_excel_file(file_url: str) -> Dict[str, Any]:
    try:
        if not file_url:
            _create_error_response("No file URL provided", "Validation")

        manager = ExcelProcessingManager()
        result = manager.process_file(file_url)

        return result

    except Exception as e:
        return _handle_file_processing_error(e)


class BarcodeRequest(TypedDict):
    barcode: str
    employee: str
    operation: str
    quality_data: Optional[Dict[str, Any]]


@frappe.whitelist()
def read_barcode(
    barcode: str,
    employee: str,
    operation: str,
    quality_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    try:
        reader = BarcodeReader()
        result = reader.read_barcode(
            barcode=barcode,
            employee=employee,
            operation=operation,
            quality_data=quality_data,
        )
        return result
    except (QualityControlError, InvalidBarcodeError, BarcodeError) as e:
        return _handle_barcode_error(e)
    except Exception as e:
        return _handle_system_error(e)


def _create_error_response(message: str, error_type: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "message": _(message),
        "error_type": error_type,
    }


def _create_success_response(message: str, data: Any = None) -> Dict[str, Any]:
    response = {
        "status": "success",
        "message": _(message),
    }
    if data:
        response["data"] = data
    return response


def _handle_operation_error(error: Exception) -> Dict[str, Any]:
    """Handle errors from glass operation processing"""
    frappe.log_error(
        f"Error processing glass operation: {str(error)}", "Glass Operation Error"
    )
    return {"status": "error", "message": str(error), "error_type": "system"}


def _handle_file_processing_error(error: Exception) -> Dict[str, Any]:
    """Handle errors from file processing"""
    frappe.log_error(
        f"Error in file processing: {str(error)}", "File Processing API Error"
    )
    return {
        "status": "error",
        "message": _("Unexpected error occurred"),
        "error_type": "system",
    }


def _handle_barcode_error(error: Exception) -> Dict[str, Any]:
    """Handle specific barcode-related errors"""
    if isinstance(error, QualityControlError):
        return {
            "status": "error",
            "message": str(error.message),
            "error_type": error.error_type,
            **(error.data or {}),
        }
    elif isinstance(error, InvalidBarcodeError):
        return {"status": "error", "message": str(error), "error_type": "invalid_barcode"}
    elif isinstance(error, BarcodeError):
        return {
            "status": "error",
            "message": str(error),
            "error_type": "barcode_operation",
        }
    return _handle_system_error(error)


def _handle_system_error(error: Exception) -> Dict[str, Any]:
    """Handle general system errors"""
    frappe.log_error(f"Error reading barcode: {str(error)}", "Barcode Reader Error")
    return {"status": "error", "message": str(error), "error_type": "system"}
