import json
from typing import Any, Optional

import frappe

from ozerpan_ercom_sync.custom_api.barcode_reader.exceptions import InvalidBarcodeError

from ..constants import BarcodeStatus
from ..models.quality_data import QualityData


def get_tesdetay(barcode: str, operation: str) -> Any:
    filters = {"barkod": barcode}
    results = frappe.db.sql(
        """
        SELECT
            td.*,
            os.job_card_ref,
            os.status,
            os.operation,
            os.is_corrective,
            os.idx
        FROM `tabTesDetay` td
        LEFT JOIN `tabTesDetay Operation Status` os ON td.name = os.parent
        WHERE td.barkod = %(barkod)s
        ORDER BY td.name, os.idx
        """,
        filters,
        as_dict=1,
    )

    current_doc = None
    organized_data = []

    for row in results:
        if current_doc is None or current_doc["name"] != row.name:
            current_doc = {
                "name": row.name,
                "siparis_no": row.siparis_no,
                "poz_no": row.poz_no,
                "sanal_adet": row.sanal_adet,
                "barkod": row.barkod,
                "model": row.model,
                "stok_kodu": row.stok_kodu,
                "quality_data": row.quality_data,
                "operation_states": [],
            }
            organized_data.append(current_doc)

        if row.job_card_ref:
            current_doc["operation_states"].append(
                {
                    "job_card_ref": row.job_card_ref,
                    "status": row.status,
                    "operation": row.operation,
                    "is_corrective": row.is_corrective,
                    "idx": row.idx,
                }
            )

    filtered_data = [
        od
        for od in organized_data
        if od.get("operation_states")
        and any(
            os["operation"] == operation and os["status"] != "Completed"
            for os in od.get("operation_states")
        )
    ]
    if filtered_data:
        min_poz_tesdetay = min(filtered_data, key=lambda x: x.get("poz_no", float("inf")))
        filtered_data = [min_poz_tesdetay]
    if not filtered_data:
        raise InvalidBarcodeError(f"No TesDetay found for barcode: {barcode}")
    return min_poz_tesdetay


def update_operation_status(
    tesdetay_ref: str,
    job_card_name: str,
    status: BarcodeStatus,
    quality_data: Optional[QualityData] = None,
) -> None:
    tesdetay = frappe.get_doc("TesDetay", tesdetay_ref)
    if quality_data:
        tesdetay.quality_data = json.dumps(quality_data.__dict__)
    for op_state in tesdetay.operation_states:
        if op_state.job_card_ref == job_card_name:
            op_state.status = status.value
            tesdetay.save(ignore_permissions=True)
            break
