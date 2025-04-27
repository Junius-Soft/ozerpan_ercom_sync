from typing import Dict, List, Optional

import frappe


def get_glass_list(
    order_no: str, poz_no: str, target_sanal_adet: Optional[str] = None
) -> List[Dict]:
    filters = {"order_no": order_no, "poz_no": poz_no}

    if target_sanal_adet is not None:
        filters["sanal_adet"] = target_sanal_adet

    results = frappe.db.sql(
        """
        SELECT
            gl.name,
            gl.order_no,
            gl.stok_kodu as stock_code,
            gl.poz_no,
            gl.sanal_adet,
            gl.quality_data,
            jc.job_card_ref,
            jc.status,
            jc.operation,
            jc.is_corrective,
            jc.idx
        FROM `tabCamListe` gl
        LEFT JOIN `tabCamListe Job Card` jc ON gl.name = jc.parent
        WHERE gl.order_no = %(order_no)s
        AND gl.poz_no = %(poz_no)s
        {sanal_adet_filter}
        ORDER BY gl.name, jc.idx
        """.format(
            sanal_adet_filter="AND gl.sanal_adet = %(sanal_adet)s"
            if target_sanal_adet is not None
            else ""
        ),
        filters,
        as_dict=1,
    )

    current_doc = None
    organized_data = []

    for row in results:
        if current_doc is None or current_doc["name"] != row.name:
            current_doc = {
                "name": row.name,
                "order_no": row.order_no,
                "poz_no": row.poz_no,
                "sanal_adet": row.sanal_adet,
                "stock_code": row.stock_code,
                "quality_data": row.quality_data,
                "job_cards": [],
            }
            organized_data.append(current_doc)

        if row.job_card_ref:
            current_doc["job_cards"].append(
                {
                    "job_card_ref": row.job_card_ref,
                    "status": row.status,
                    "operation": row.operation,
                    "is_corrective": row.is_corrective,
                    "idx": row.idx,
                }
            )

    return organized_data


def get_tesdetay_list(
    order_no: str,
    poz_no: str,
    target_sanal_adet: Optional[str] = None,
) -> List[Dict]:
    """
    Get TesDetay records for given order and position numbers.

    Args:
        order_no: Order number
        poz_no: Position number
        target_sanal_adet: Optional sanal_adet to filter results

    Returns:
        List of TesDetay records with their operation states
    """
    print("\n\n-- Get TesDetay List Helper -- (Start)")
    filters = {"siparis_no": order_no, "poz_no": poz_no}

    print("Order No:", order_no)
    print("Poz No:", poz_no)

    if target_sanal_adet is not None:
        filters["sanal_adet"] = target_sanal_adet

    results = frappe.db.sql(
        """
        SELECT
            td.name,
            td.poz_no,
            td.sanal_adet,
            td.barkod,
            td.model,
            td.stok_kodu,
            td.quality_data,
            os.job_card_ref,
            os.status,
            os.operation,
            os.is_corrective,
            os.idx
        FROM `tabTesDetay` td
        LEFT JOIN `tabTesDetay Operation Status` os ON td.name = os.parent
        WHERE td.siparis_no = %(siparis_no)s
        AND td.poz_no = %(poz_no)s
        {sanal_adet_filter}
        ORDER BY td.name, os.idx
        """.format(
            sanal_adet_filter="AND td.sanal_adet = %(sanal_adet)s"
            if target_sanal_adet is not None
            else ""
        ),
        filters,
        as_dict=1,
    )

    current_doc = None
    organized_data = []

    for row in results:
        if current_doc is None or current_doc["name"] != row.name:
            current_doc = {
                "name": row.name,
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

    print("-- Get TesDetay List Helper -- (End)\n\n")
    return organized_data
