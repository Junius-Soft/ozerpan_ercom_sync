from typing import Dict, List, Optional

import frappe


def before_insert(doc, method):
    print("\n\n-- Job Card Before Insert -- (Start)")

    production_item = doc.production_item
    operation_name = doc.operation

    parts = production_item.split("-")
    if len(parts) >= 2:
        order_no = parts[0]
        poz_no = parts[1]

    if operation_name == "Profil Temin" or operation_name == "Sac Kesim":
        return

    if operation_name == "Cam":
        frappe.throw("--Handle Cam Operation!!--")
    else:
        if doc.is_corrective_job_card:
            frappe.throw("-- Handle Corrective Job Card for Barcodes --")
        else:
            tesdetay_list = get_tesdetay_list(
                order_no=order_no,
                poz_no=poz_no,
            )

            filtered_tesdetay_list = [
                td
                for td in tesdetay_list
                if not any(
                    os.get("operation") == doc.operation
                    for os in td.get("operation_states", [])
                )
            ]

            sorted_tesdetay_list = sorted(
                filtered_tesdetay_list, key=lambda x: int(x["sanal_adet"])
            )

            unique_sanal_adet = sorted(
                list(set(td["sanal_adet"] for td in sorted_tesdetay_list)), key=int
            )
            target_sanal_adet = unique_sanal_adet[: doc.for_quantity]

            selected_tesdetay_list = [
                td for td in sorted_tesdetay_list if td["sanal_adet"] in target_sanal_adet
            ]

            for td in selected_tesdetay_list:
                print(
                    f"barcode: {td.get('barkod')}, name: {td.get('name')}, poz_no: {td.get('poz_no')}, sanal_adet: {td.get('sanal_adet')}"
                )

    print("-- Job Card Before Insert -- (End)\n\n")


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
    filters = {"siparis_no": order_no, "poz_no": poz_no}

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

    return organized_data
