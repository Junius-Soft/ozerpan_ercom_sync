from typing import Any, Dict, List, Set

import frappe
from frappe import _


def fetch_surme_orders(order_no: str = None) -> Set[str]:
    filters = {"operation": ["like", "%Sürme Hazırlık%"]}
    if order_no:
        filters["production_item"] = ["like", f"%{order_no}%"]

    job_cards = frappe.get_list(
        doctype="Job Card",
        filters=filters,
        fields=["name", "production_item"],
        page_length=20,
    )

    orders = set()
    for jc in job_cards:
        order_no = jc["production_item"].split("-")[0]
        orders.add(order_no)

    return orders


def get_custom_barcodes(job_card_name: str) -> List[str]:
    custom_barcodes = frappe.get_all(
        "Ozerpan Job Card Items",
        filters={"parent": job_card_name},
        fields=["barcode"],
        as_list=1,
    )
    return [b[0] for b in custom_barcodes]


def get_barcode_details(barcode: str) -> Dict[str, Any]:
    td = frappe.get_doc("TesDetay", {"barkod": barcode})
    return {
        "oto_no": td.oto_no,
        "barkod": td.barkod,
        "stok_kodu": td.stok_kodu,
        "sanal_adet": td.sanal_adet,
        "model": td.model,
        "pozisyon": td.pozisyon,
        "olcu": td.olcu,
        "aci1": td.aci1,
        "aci2": td.aci2,
        "yukseklik": td.yukseklik,
        "ds_kodu": td.ds_kodu,
        "ds_boyu": td.ds_boyu,
        "aciklama": td.aciklama,
    }


def get_item_details(item_code: str) -> Dict[str, Any]:
    item = frappe.get_doc("Item", {"item_code": item_code})
    return {
        "adet": item.custom_quantity,
        "seri": item.custom_serial,
        "renk": item.custom_color,
        "notlar": item.custom_remarks,
        "resim": item.image,
    }


def fetch_surme_poz_details(order_no: str) -> Dict[str, Any]:
    if not order_no:
        frappe.throw(_("Order number must be provided"))

    filters = {
        "operation": ["like", "%Sürme Hazırlık%"],
        "production_item": ["like", f"{order_no}%"],
    }

    job_cards = frappe.get_list(
        doctype="Job Card",
        filters=filters,
        fields=["name", "production_item", "work_order"],
        page_length=20,
    )

    order_poz_set = set()
    order_poz_details: Dict[str, Any] = {}

    for jc in job_cards:
        barcodes = get_custom_barcodes(jc["name"])
        barcode_items = []
        poz_detail: Dict[str, Any] = {}

        for b in barcodes:
            td = frappe.get_doc("TesDetay", {"barkod": b})

            if "cari_kod" not in poz_detail:
                poz_detail.update(
                    {
                        "cari_kod": td.cari_kod,
                        "bayi_adi": td.bayi_adi,
                        "musteri": td.musteri,
                    }
                )

            barcode_items.append(get_barcode_details(b))

        item_code = jc["production_item"]
        poz_detail.update(get_item_details(item_code))
        poz_detail["tesdetay"] = barcode_items

        order_poz_details[item_code] = poz_detail
        order_poz_set.add(item_code)

    return {
        "order_poz_list": list(order_poz_set),
        "order_poz_details": order_poz_details,
    }
