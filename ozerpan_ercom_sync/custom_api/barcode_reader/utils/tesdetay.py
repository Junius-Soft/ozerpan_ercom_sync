import json
from typing import Any, Optional

import frappe

from ozerpan_ercom_sync.custom_api.barcode_reader.exceptions import InvalidBarcodeError

from ..constants import BarcodeStatus
from ..models.quality_data import QualityData


def get_tesdetay(
    barcode: str,
    operation: str,
    order_no: Optional[str] = None,
    poz_no: Optional[int] = None,
) -> Any:
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

    # Helper function to select TesDetay based on business logic
    def select_tesdetay_from_same_group(candidates):
        """Select TesDetay from candidates with same order_no and poz_no"""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # If multiple with same order_no and poz_no, return minimum sanal_adet
        # Convert sanal_adet to int for proper numeric comparison (not string comparison)
        return min(candidates, key=lambda x: int(x.get("sanal_adet", float("inf"))))

    # If order_no and poz_no are provided, filter by them first
    if order_no and poz_no:
        # Filter by order_no and poz_no, then by operation status
        filtered_data = [
            od
            for od in organized_data
            if od.get("siparis_no") == order_no
            and od.get("poz_no") == poz_no
            and od.get("operation_states")
            and any(
                os["operation"] == operation and os["status"] != "Completed"
                for os in od.get("operation_states")
            )
        ]

        if filtered_data:
            # If multiple TesDetays with same order_no and poz_no, choose minimum sanal_adet
            return select_tesdetay_from_same_group(filtered_data)

        # Check for completed ones with same order_no and poz_no
        completed_data = [
            od
            for od in organized_data
            if od.get("siparis_no") == order_no
            and od.get("poz_no") == poz_no
            and od.get("operation_states")
            and any(
                os["operation"] == operation and os["status"] == "Completed"
                for os in od.get("operation_states")
            )
        ]

        if completed_data:
            min_completed = select_tesdetay_from_same_group(completed_data)
            min_completed["for_information_only"] = True
            return min_completed

        raise InvalidBarcodeError(
            f"No TesDetay found for barcode: {barcode} with order_no: {order_no} and poz_no: {poz_no}"
        )

    # When order_no and poz_no are not provided, get all relevant TesDetays
    # Get both active and completed operations
    active_data = [
        od
        for od in organized_data
        if od.get("operation_states")
        and any(
            os["operation"] == operation and os["status"] != "Completed"
            for os in od.get("operation_states")
        )
    ]

    completed_data = [
        od
        for od in organized_data
        if od.get("operation_states")
        and any(
            os["operation"] == operation and os["status"] == "Completed"
            for os in od.get("operation_states")
        )
    ]

    # Mark completed data
    for item in completed_data:
        item["for_information_only"] = True

    # Combine all data
    all_data = active_data + completed_data

    if not all_data:
        raise InvalidBarcodeError(f"No TesDetay found for barcode: {barcode}")

    # Group by siparis_no and poz_no
    grouped = {}
    for tesdetay in all_data:
        key = (tesdetay.get("siparis_no"), tesdetay.get("poz_no"))
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(tesdetay)

    # If there's only one group, return the one with minimum sanal_adet
    if len(grouped) == 1:
        group = list(grouped.values())[0]
        return select_tesdetay_from_same_group(group)

    # If there are multiple groups, return all options for client selection
    # But first, select minimum sanal_adet from each group
    options = []
    for group in grouped.values():
        min_sanal_adet = select_tesdetay_from_same_group(group)
        options.append(min_sanal_adet)

    return options


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
