from typing import Dict, List

from ozerpan_ercom_sync.job_card_hooks.helpers import get_glass_list, get_tesdetay_list
from ozerpan_ercom_sync.utils import bulk_insert_child_rows, timer


@timer
def after_insert(doc, method):
    print("\n\n-- Job Card After Insert -- (Start)")
    production_item = doc.production_item
    operation_name = doc.operation

    if operation_name == "Profil Temin" or operation_name == "Sac Kesim":
        return

    parts = production_item.split("-")
    if len(parts) >= 2:
        order_no = parts[0]
        poz_no = parts[1]

    if doc.operation == "Cam":
        glass_stock_code = parts[2]
        if doc.is_corrective_job_card:
            insert_corrective_job_card_to_glass_list(
                doc=doc,
                order_no=order_no,
                poz_no=poz_no,
                glass_stock_code=glass_stock_code,
            )
            # frappe.throw("-- Handle Corrective Cam Operation in after_insert Hook!! --")
        else:
            insert_job_card_to_glass_list(
                doc=doc,
                order_no=order_no,
                poz_no=poz_no,
                glass_stock_code=glass_stock_code,
            )
    else:
        if doc.is_corrective_job_card:
            insert_corrective_job_card_to_operation_states_list(
                doc=doc,
                order_no=order_no,
                poz_no=poz_no,
            )
        else:
            insert_job_card_to_operation_states_list(
                doc=doc,
                order_no=order_no,
                poz_no=poz_no,
            )

    doc.flags.from_after_insert = True
    doc.save()

    print("-- Job Card After Insert -- (End)\n\n")


def insert_corrective_job_card_to_glass_list(
    doc: Dict,
    order_no: str,
    poz_no: str,
    glass_stock_code: str,
) -> None:
    if not doc.custom_target_sanal_adet:
        return

    glass_job_items = [
        {
            "parent": g.get("glass_ref"),
            "job_card_ref": doc.name,
            "status": "Pending",
            "operation": doc.operation,
            "is_corrective": doc.is_corrective_job_card,
        }
        for g in doc.custom_glasses
    ]

    inserted_items = bulk_insert_child_rows(
        child_table="CamListe Job Card",
        parenttype="CamListe",
        parentfield="job_cards",
        rows=glass_job_items,
        extra_fields=["job_card_ref", "status", "operation", "is_corrective"],
    )

    glasses = []
    for item in inserted_items:
        glasses.append(
            {
                "glass_operation_ref": item.get("name"),
                "glass_ref": item.get("parent"),
            }
        )

    doc.set("custom_glasses", glasses)


def insert_job_card_to_glass_list(
    doc: Dict,
    order_no: str,
    poz_no: str,
    glass_stock_code: str,
) -> None:
    glass_list = get_filtered_glass_list(
        doc=doc,
        order_no=order_no,
        poz_no=poz_no,
        glass_stock_code=glass_stock_code,
    )
    selected_glasses = select_target_glasses(glass_list, doc.for_quantity)

    glass_job_items = create_glass_job_items(selected_glasses, doc)

    inserted_items = bulk_insert_child_rows(
        child_table="CamListe Job Card",
        parenttype="CamListe",
        parentfield="job_cards",
        rows=glass_job_items,
        extra_fields=["job_card_ref", "status", "operation", "is_corrective"],
    )

    glasses = []
    for item in inserted_items:
        glasses.append(
            {
                "glass_operation_ref": item.get("name"),
                "glass_ref": item.get("parent"),
            }
        )
    doc.set("custom_glasses", glasses)


def get_filtered_glass_list(
    doc: Dict,
    order_no: str,
    poz_no: str,
    glass_stock_code: str,
) -> List[Dict]:
    glass_list = get_glass_list(
        order_no=order_no,
        poz_no=poz_no,
        glass_stock_code=glass_stock_code,
    )

    return [
        g
        for g in glass_list
        if not any(o.get("operation") == doc.operation for o in g.get("job_cards", []))
    ]


def select_target_glasses(glass_list: List[Dict], quantity: int) -> List[Dict]:
    sorted_glasses = sorted(glass_list, key=lambda x: int(x["sanal_adet"].split("/")[0]))
    unique_sanal_adet = sorted(
        list(set(g["sanal_adet"].split("/")[0] for g in sorted_glasses)), key=int
    )
    target_sanal_adet = unique_sanal_adet[: int(quantity)]

    return [
        g for g in sorted_glasses if g["sanal_adet"].split("/")[0] in target_sanal_adet
    ]


def create_glass_job_items(glasses: List, doc: Dict) -> List[Dict]:
    """Create glass job item records for bulk insert"""
    return [
        {
            "parent": g.get("name"),
            "job_card_ref": doc.name,
            "status": "Pending",
            "operation": doc.operation,
            "is_corrective": doc.is_corrective_job_card,
        }
        for g in glasses
    ]


def insert_corrective_job_card_to_operation_states_list(
    doc: Dict,
    order_no: str,
    poz_no: str,
) -> None:
    if not doc.custom_target_sanal_adet:
        return

    tesdetay_list = get_tesdetay_list(
        order_no=order_no,
        poz_no=poz_no,
        target_sanal_adet=doc.custom_target_sanal_adet,
    )

    operation_states = create_operation_states(tesdetay_list, doc)

    inserted_items = bulk_insert_child_rows(
        child_table="TesDetay Operation Status",
        parenttype="TesDetay",
        parentfield="operation_states",
        rows=operation_states,
        extra_fields=["job_card_ref", "status", "operation", "is_corrective"],
    )

    barcodes = []
    for item in inserted_items:
        barcodes.append(
            {
                "operation_status_ref": item.get("name"),
                "tesdetay_ref": item.get("parent"),
            }
        )

    doc.set("custom_barcodes", barcodes)


def insert_job_card_to_operation_states_list(
    doc: Dict,
    order_no: str,
    poz_no: str,
) -> None:
    tesdetay_list = get_filtered_tesdetay_list(doc, order_no, poz_no)
    selected_tesdetays = select_target_tesdetay(tesdetay_list, doc.for_quantity)

    operation_states = create_operation_states(selected_tesdetays, doc)

    inserted_items = bulk_insert_child_rows(
        child_table="TesDetay Operation Status",
        parenttype="TesDetay",
        parentfield="operation_states",
        rows=operation_states,
        extra_fields=["job_card_ref", "status", "operation", "is_corrective"],
    )

    barcodes = []
    for item in inserted_items:
        barcodes.append(
            {
                "operation_status_ref": item.get("name"),
                "tesdetay_ref": item.get("parent"),
            }
        )

    # barcodes = sorted(barcodes, key=lambda x: int(x["sanal_adet"]))
    doc.set("custom_barcodes", barcodes)


def get_filtered_tesdetay_list(
    doc: Dict,
    order_no: str,
    poz_no: str,
) -> List[Dict]:
    tesdetay_list = get_tesdetay_list(order_no=order_no, poz_no=poz_no)

    return [
        td
        for td in tesdetay_list
        if not any(
            os.get("operation") == doc.operation for os in td.get("operation_states", [])
        )
    ]


def select_target_tesdetay(tesdetay_list: List[Dict], quantity: int) -> List[Dict]:
    sorted_tesdetay = sorted(tesdetay_list, key=lambda x: int(x["sanal_adet"]))
    unique_sanal_adet = sorted(
        list(set(td["sanal_adet"] for td in sorted_tesdetay)), key=int
    )

    target_sanal_adet = unique_sanal_adet[: int(quantity)]

    return [td for td in sorted_tesdetay if td["sanal_adet"] in target_sanal_adet]


def create_operation_states(tesdetays: List, doc: Dict) -> List[Dict]:
    """Create operation states records for bulk insert."""
    return [
        {
            "parent": td.get("name"),
            "job_card_ref": doc.name,
            "status": "Pending",
            "operation": doc.operation,
            "is_corrective": doc.is_corrective_job_card,
        }
        for td in tesdetays
    ]


########################################################################
def add_job_cards_into_camliste(job_card_doc):
    rows = []

    for i, glass in enumerate(job_card_doc.custom_glasses):
        rows.append(
            {
                "parent": glass.glass_ref,
                "job_card_ref": job_card_doc.name,
                "status": "Pending",
                "operation": job_card_doc.operation,
                "is_corrective": job_card_doc.is_corrective_job_card,
            }
        )

    bulk_insert_child_rows(
        child_table="CamListe Job Card",
        parenttype="CamListe",
        parentfield="job_cards",
        rows=rows,
        extra_fields=["job_card_ref", "status", "operation", "is_corrective"],
    )


def add_job_cards_into_tesdetay(job_card_doc):
    rows = []

    for i, barcode in enumerate(job_card_doc.custom_barcodes):
        rows.append(
            {
                "parent": barcode.tesdetay_ref,
                "job_card_ref": job_card_doc.name,
                "status": "Pending",
                "operation": job_card_doc.operation,
                "is_corrective": job_card_doc.is_corrective_job_card,
            }
        )

    bulk_insert_child_rows(
        child_table="TesDetay Operation Status",
        parenttype="TesDetay",
        parentfield="operation_states",
        rows=rows,
        extra_fields=["job_card_ref", "status", "operation", "is_corrective"],
    )
