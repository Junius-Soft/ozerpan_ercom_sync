from typing import Any

import frappe

from ..constants import BarcodeStatus
from ..exceptions import InvalidBarcodeError


def get_tesdetay(barcode: str) -> Any:
    tesdetay = frappe.get_doc("TesDetay", {"barkod": barcode})
    if not tesdetay:
        raise InvalidBarcodeError(f"No TesDetay found for barcode: {barcode}")
    return tesdetay


def update_operation_status(
    tesdetay_ref: str,
    job_card_name: str,
    status: BarcodeStatus,
) -> None:
    tesdetay = frappe.get_doc("TesDetay", tesdetay_ref)
    for op_state in tesdetay.operation_states:
        if op_state.job_card_ref == job_card_name:
            op_state.status = status.value
            tesdetay.save()
            break
