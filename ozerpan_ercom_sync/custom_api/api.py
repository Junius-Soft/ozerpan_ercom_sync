from typing import Any, Dict, List, Optional, TypedDict

import frappe
from frappe import _

from ozerpan_ercom_sync.custom_api.barcode_reader.constants import BarcodeStatus
from ozerpan_ercom_sync.custom_api.barcode_reader.utils.job_card import (
    complete_job,
    get_job_card,
    save_with_retry,
    submit_job_card,
    update_job_card_status,
)
from ozerpan_ercom_sync.custom_api.barcode_reader.utils.tesdetay import get_tesdetay
from ozerpan_ercom_sync.utils import bulk_update_operation_status

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
def revert_latest_barcode_operation(barcode: str, operation: str) -> None:
    print("\n\n-- Revert Barcode Operation -- (Start)")

    tesdetay = get_tesdetay(barcode=barcode, operation=operation)
    if not tesdetay:
        raise InvalidBarcodeError("Invalid Barcode")

    job_card = get_job_card(
        barcode=barcode,
        operation=operation,
        production_item=f"{tesdetay.get('siparis_no')}-{tesdetay.get('poz_no')}",
    )

    current_os = None
    for os in tesdetay.get("operation_states"):
        if os.get("operation") == operation:
            current_os = os

    if not current_os or current_os.get("status") != "In Progress":
        frappe.throw("Only items with the status of 'In Progress' can be reverted.")

    tesdetay_refs = [
        b.tesdetay_ref
        for b in job_card.get("custom_barcodes")
        if b.status == "In Progress"
    ]
    job_card_refs = [job_card.name] * len(tesdetay_refs)

    bulk_update_operation_status(
        tesdetay_refs,
        job_card_refs,
        BarcodeStatus.PENDING.value,
    )

    for time_log in job_card.time_logs:
        if not time_log.to_time:
            frappe.delete_doc("Job Card Time Log", time_log.name)
    job_card.status = "On Hold"

    save_with_retry(job_card)
    print("\n\n-- Revert Barcode Operation -- (End)")
    return {
        "tesdetays": tesdetay_refs,
        "operation": operation,
    }


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
def update_job_cards():
    print("\n\n-- Update Job Cards -- (Start)")
    form_data = frappe.form_dict
    target_status = form_data.status
    employee = form_data.employee
    reason = form_data.reason

    missing_job_cards = []
    messages = []

    for jc_name in form_data.job_cards:
        try:
            jc_doc = frappe.get_doc("Job Card", jc_name)
        except frappe.DoesNotExistError:
            missing_job_cards.append(jc_name)
            continue

        if jc_doc.status == target_status:
            messages.append(f"Job Card is already {jc_doc.status}: {jc_doc.name}")
            continue

        if jc_doc.status == "Completed":
            messages.append(f"Job Card is already completed: {jc_doc.name}")
            continue

        if target_status == "Completed":
            if jc_doc.status != "Work In Progress":
                messages.append(
                    f"Only Work In Progress Job Cards can be completed: {jc_doc.name} - {jc_doc.status}"
                )
                continue
            complete_job(jc_doc, jc_doc.for_quantity)
            submit_job_card(jc_doc)
            messages.append(
                f"Job Card successfully completed: {jc_doc} - {target_status}"
            )

        elif target_status in ["Work In Progress", "On Hold"]:
            update_job_card_status(
                job_card=jc_doc,
                status=target_status,
                employee=employee,
                reason=reason,
            )
            messages.append(
                f"Job Card status changed successfully: {jc_doc} - {target_status}"
            )

    response = {}
    if missing_job_cards:
        response["missing_job_cards"] = missing_job_cards

    if messages:
        response["messages"] = messages

    print("-- Update Job Cards -- (End)\n\n")

    return response


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
            return _create_error_response("No file URL provided", "Validation")

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
