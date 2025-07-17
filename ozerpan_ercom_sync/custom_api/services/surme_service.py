from typing import Any, Dict, List, Set

import frappe
from frappe import _

from ..barcode_reader.utils.job_card import format_job_card_response


def fetch_surme_orders(
    operation_type: str,
    order_no: str = None,
) -> Set[str]:
    """Fetch and cache Surme orders."""
    if not operation_type:
        frappe.throw(_("Operation Type is required."))
        return

    # filters = {"operation": ["like", f"%{operation_type}%"]}
    # filters = {"operation": operation_type}
    filters = {"operation": operation_type, "status": ["!=", "Completed"]}

    if order_no:
        filters["production_item"] = ["like", f"%{order_no}%"]

    job_cards = frappe.get_list(
        doctype="Job Card",
        filters=filters,
        fields=["production_item", "name"],
        page_length=20,
    )
    return {jc["production_item"].split("-")[0] for jc in job_cards}


def get_custom_barcodes(job_card_name: str) -> List[str]:
    """Get custom barcodes for a job card."""
    return [
        b[0]
        for b in frappe.get_all(
            "Ozerpan Job Card Items",
            filters={"parent": job_card_name},
            fields=["barcode"],
            as_list=1,
        )
    ]


def get_barcode_details(barcode: str) -> Dict[str, Any]:
    """Get and cache barcode details."""
    td = frappe.get_doc("TesDetay", {"barkod": barcode})
    pt = frappe.get_doc("Profile Type", td.stok_kodu)

    return {
        field: getattr(td, field)
        for field in [
            "oto_no",
            "barkod",
            "stok_kodu",
            "sanal_adet",
            "model",
            "pozisyon",
            "olcu",
            "aci1",
            "aci2",
            "yukseklik",
            "ds_kodu",
            "ds_boyu",
            "aciklama",
        ]
    } | {"profil": pt.description}


def get_item_details(item_code: str) -> Dict[str, Any]:
    """Get and cache item details."""
    item = frappe.get_doc("Item", {"item_code": item_code})
    return {
        "adet": item.custom_quantity,
        "seri": item.custom_serial,
        "renk": item.custom_color,
        "notlar": item.custom_remarks,
        "resim": item.image,
    }


def get_glasses(order_no: str, poz_no: str) -> List[Dict]:
    """Get unique glasses for an order and position."""
    return list(
        {
            g.stok_kodu: g
            for g in frappe.get_all(
                doctype="CamListe",
                filters={"order_no": order_no, "poz_no": poz_no},
                fields=["name", "stok_kodu", "aciklama"],
            )
        }.values()
    )


def fetch_surme_poz_details(
    operation_type: str,
    order_no: str,
) -> Dict[str, Any]:
    """Fetch Surme position details."""

    if not operation_type:
        frappe.throw(_("Operation Type is required."))
        return

    if not order_no:
        frappe.throw(_("Order number must be provided"))

    sales_order = frappe.get_doc("Sales Order", order_no)

    job_cards = frappe.get_all(
        doctype="Job Card",
        filters={
            "operation": ["like", f"%{operation_type}%"],
            "production_item": ["like", f"{order_no}%"],
            "status": ["!=", "Completed"],

        },
        fields=["name", "production_item", "work_order"],
        page_length=20,
    )

    print("Job Cards:", job_cards)

    order_poz_details: Dict[str, Any] = {}
    job_cards_response: list[dict[str, Any]] = []

    for jc in job_cards:
        barcodes = get_custom_barcodes(jc["name"])
        barcode_items = []
        poz_detail: Dict[str, Any] = {}

        # Process first barcode for customer details
        if barcodes:
            first_td = frappe.get_doc("TesDetay", {"barkod": barcodes[0]})
            poz_detail.update(
                {
                    "cari_kod": first_td.cari_kod,
                    "bayi_adi": first_td.bayi_adi,
                    "musteri": first_td.musteri,
                }
            )

        # Process all barcodes
        barcode_items = [get_barcode_details(b) for b in barcodes]

        item_code = jc["production_item"]
        poz_no = item_code.split("-")[1]

        # Update poz details
        poz_detail.update(get_item_details(item_code))
        poz_detail.update(
            {
                "siparis_tarihi": sales_order.transaction_date,
                "sevkiyat_tarihi": sales_order.delivery_date,
                "cam_liste": get_glasses(order_no, poz_no),
                "tesdetay": barcode_items,
            }
        )

        order_poz_details[item_code] = poz_detail
        print("Name:", jc.name)
        jc_doc = format_job_card_response(frappe.get_doc("Job Card", jc.name))
        job_cards_response.append(jc_doc)

    poz_nolar = list(order_poz_details.keys())
    job_cards = frappe.get_all(
        "Job Card",
        filters={"production_item": ["in", poz_nolar]},
        fields=["*"]
    )
    job_cards_by_poz = {jc["production_item"]: jc for jc in job_cards}

    for poz_no, details in order_poz_details.items():
        jobcard = frappe.db.get_value(
            "Job Card",
            {"production_item": poz_no, "operation": operation_type},
            "*",
            as_dict=True
        )
        details["job_card"] = jobcard

    return {
        "order_poz_details": order_poz_details,
    }
