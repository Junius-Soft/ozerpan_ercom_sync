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
    sanal_adet: Optional[str] = None,
    tesdetay_name: Optional[str] = None,
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
        # If multiple with same order_no and poz_no, return all options for client selection
        return candidates

    # If order_no and poz_no are provided, filter by them first
    if order_no and poz_no:
        # Filter by order_no and poz_no, then by operation status
        filtered_data = [
            od
            for od in organized_data
            if od.get("siparis_no") == order_no
            and od.get("poz_no") == poz_no
            and od.get("operation_states")
            and od.get("name") == tesdetay_name
            and any(
                os["operation"] == operation and os["status"] != "Completed"
                for os in od.get("operation_states")
            )
        ]

        # If sanal_adet is also provided, filter by it for exact match
        if sanal_adet is not None:
            filtered_data = [
                od for od in filtered_data if od.get("sanal_adet") == sanal_adet
            ]

        if tesdetay_name is not None:
            filtered_data = [
                od for od in filtered_data if od.get("name") == tesdetay_name
            ]

        if filtered_data:
            # If multiple TesDetays with same order_no and poz_no, return all options for client selection
            result = select_tesdetay_from_same_group(filtered_data)
            return result if not isinstance(result, list) else result

        # Check for completed ones with same order_no and poz_no
        completed_data = [
            od
            for od in organized_data
            if od.get("siparis_no") == order_no
            and od.get("poz_no") == poz_no
            and od.get("operation_states")
            and od.get("name") == tesdetay_name
            and any(
                os["operation"] == operation and os["status"] == "Completed"
                for os in od.get("operation_states")
            )
        ]

        # If sanal_adet is also provided, filter completed data by it
        if sanal_adet is not None:
            completed_data = [
                od for od in completed_data if od.get("sanal_adet") == sanal_adet
            ]

        if completed_data:
            completed_result = select_tesdetay_from_same_group(completed_data)
            if isinstance(completed_result, list):
                for item in completed_result:
                    item["for_information_only"] = True
                return completed_result
            else:
                completed_result["for_information_only"] = True
                return completed_result

        error_msg = f"No TesDetay found for barcode: {barcode} with order_no: {order_no} and poz_no: {poz_no}"
        if sanal_adet is not None:
            error_msg += f" and sanal_adet: {sanal_adet}"
        raise InvalidBarcodeError(error_msg)

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

    # Group by siparis_no, poz_no, and sanal_adet
    grouped = {}
    for tesdetay in all_data:
        key = (
            tesdetay.get("siparis_no"),
            tesdetay.get("poz_no"),
            tesdetay.get("sanal_adet"),
        )
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(tesdetay)

    # If there's only one group, return the first item
    if len(grouped) == 1:
        group = list(grouped.values())[0]
        return group[0]

    # If there are multiple groups, return all options for client selection
    # Return one representative from each group (they should be identical within each group)
    options = []
    for group in grouped.values():
        options.append(group[0])

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
