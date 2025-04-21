from typing import Dict, List, Optional

import frappe

from ozerpan_ercom_sync.utils import timer


@timer
def before_save(doc, method) -> None:
    print("\n\n\n-- Job Card Before Save --")
    production_item = doc.production_item
    operation_name = doc.operation

    # order_no, poz_no = production_item.split("-")
    parts = production_item.split("-")
    if len(parts) >= 2:
        order_no = parts[0]
        poz_no = parts[1]

    if operation_name == "Profil Temin" or operation_name == "Sac Kesim":
        return
    elif operation_name == "Cam":
        if doc.is_corrective_job_card:
            handle_glass_corrective_job_card(doc, order_no, poz_no)
            pass
        else:
            handle_glass_regular_job_card(doc, order_no, poz_no)
    else:
        if doc.is_corrective_job_card:
            handle_barcode_corrective_job_card(doc, order_no, poz_no)
        else:
            handle_barcode_regular_job_card(doc, order_no, poz_no, operation_name)


def handle_glass_corrective_job_card(doc, order_no: str, poz_no: str) -> None:
    if not doc.custom_target_sanal_adet:
        return

    glass_list = doc.custom_glasses
    glasses = []
    for glass in glass_list:
        glass_doc = frappe.get_doc("CamListe", glass.glass_ref)
        job_card = get_glass_job_card_data(doc, glass_doc)

        glasses.append(
            {
                "glass_ref": glass.get("glass_ref"),
                "order_no": glass.get("order_no"),
                "stock_code": glass.get("stock_code"),
                "poz_no": glass.get("poz_no"),
                "sanal_adet": glass.get("sanal_adet"),
                "status": job_card.get("status", "Pending"),
                "quality_data": glass.get("quality_data"),
            }
        )

    doc.set("custom_glasses", glasses)


def handle_glass_regular_job_card(doc, order_no: str, poz_no: str) -> None:
    glasses = []
    glass_list = get_glass_list(order_no, poz_no)

    for glass in glass_list:
        job_card = get_glass_job_card_data(doc, glass)

        glasses.append(
            {
                "glass_ref": glass.get("name"),
                "order_no": glass.get("order_no"),
                "stock_code": glass.get("stock_code"),
                "poz_no": glass.get("poz_no"),
                "sanal_adet": glass.get("sanal_adet"),
                "status": job_card.get("status", "Pending"),
                "quality_data": glass.get("quality_data"),
            }
        )

    glasses = sorted(glasses, key=lambda x: x["sanal_adet"])
    doc.set("custom_glasses", glasses)


def get_glass_job_card_data(doc, glass: Dict) -> Dict[str, str]:
    for jc in glass.get("job_cards", []):
        if jc.get("job_card_ref") == doc.name:
            return {
                "status": jc.get("status", "Pending"),
                "operation": doc.operation,
                "is_corrective": 1 if doc.is_corrective_job_card else 0,
            }

    return {
        "status": "Pending",
        "operation": doc.operation,
        "is_corrective": 1 if doc.is_corrective_job_card else 0,
    }


def handle_barcode_corrective_job_card(doc, order_no: str, poz_no: str) -> None:
    """Handle barcode assignment for corrective job cards"""
    if not doc.custom_target_sanal_adet:
        return

    # Get only barcodes with matching sanal_adet
    tesdetay_list = get_tesdetay_list(
        order_no, poz_no, target_sanal_adet=doc.custom_target_sanal_adet
    )

    barcodes = []
    for td in tesdetay_list:
        operation_data = get_operation_status_data(doc, td)

        barcodes.append(
            {
                "tesdetay_ref": td.get("name"),
                "barcode": td.get("barkod"),
                "model": td.get("model"),
                "stock_code": td.get("stok_kodu"),
                "poz_no": td.get("poz_no"),
                "sanal_adet": td.get("sanal_adet"),
                "status": operation_data.get("status", "Pending"),
            }
        )

    doc.set("custom_barcodes", barcodes)


def handle_barcode_regular_job_card(
    doc, order_no: str, poz_no: str, operation_name: str
) -> None:
    """Handle barcode assignment for regular job cards"""
    barcodes = []
    tesdetay_list = get_tesdetay_list(order_no, poz_no)

    for td in tesdetay_list:
        if "KAYIT" in td.get("model"):
            if operation_name in [
                "Kaynak Köşe Temizleme",
                "Kanat Hazırlık",
                "Kanat Bağlama",
            ]:
                continue

        operation_data = get_operation_status_data(doc, td)

        barcodes.append(
            {
                "tesdetay_ref": td.get("name"),
                "barcode": td.get("barkod"),
                "model": td.get("model"),
                "stock_code": td.get("stok_kodu"),
                "poz_no": td.get("poz_no"),
                "sanal_adet": td.get("sanal_adet"),
                "status": operation_data.get("status", "Pending"),
                "quality_data": td.get("quality_data"),
            }
        )

    barcodes = sorted(barcodes, key=lambda x: x["sanal_adet"])
    doc.set("custom_barcodes", barcodes)


def get_operation_status_data(doc, tesdetay: Dict) -> Dict[str, str]:
    """
    Get operation status data including operation and corrective status

    Args:
        doc: Job Card document
        tesdetay: TesDetay document data

    Returns:
        Dict containing status, operation name and corrective flag
    """
    for os in tesdetay.get("operation_states", []):
        if os.get("job_card_ref") == doc.name:
            # Update operation states with job card data
            if doc.get("operation"):
                os["operation"] = doc.operation
            if doc.get("is_corrective_job_card"):
                os["is_corrective"] = 1

            return {
                "status": os.get("status", "Pending"),
                "operation": doc.operation,
                "is_corrective": 1 if doc.is_corrective_job_card else 0,
            }

    return {
        "status": "Pending",
        "operation": doc.operation,
        "is_corrective": 1 if doc.is_corrective_job_card else 0,
    }


def get_tesdetay_list(
    order_no: str, poz_no: str, target_sanal_adet: Optional[str] = None
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
