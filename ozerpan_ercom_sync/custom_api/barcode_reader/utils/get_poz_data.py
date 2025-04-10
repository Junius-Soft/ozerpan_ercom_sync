import frappe


@frappe.whitelist()
def get_poz_data(barcode: str):
    print("\n\n\n--- Get Poz Data ---")
    tesdetay = frappe.get_doc("TesDetay", {"barkod": barcode})
    sales_order = frappe.get_doc("Sales Order", tesdetay.siparis_no)

    bom_name = f"BOM-{tesdetay.siparis_no}-{tesdetay.poz_no}"
    bom_doc = get_latest_default_bom(bom_name)
    bom_item_doc = frappe.get_doc("Item", f"{tesdetay.siparis_no}-{tesdetay.poz_no}")

    grouped_items = group_bom_items_by_category(bom_doc)

    accessory_kits = bom_doc.custom_accessory_kits

    if accessory_kits:
        for kit in accessory_kits:
            kit_doc = frappe.get_doc("Item", kit.kit_name)
            if "accessory_kits" not in grouped_items:
                grouped_items["accessory_kits"] = []
            grouped_items["accessory_kits"].append(
                {
                    "item_code": kit_doc.item_code,
                    "item_name": kit_doc.item_name,
                    "quantity": kit.quantity,
                    "image": kit_doc.image,
                }
            )

    data = {
        "siparis_no": tesdetay.get("siparis_no"),
        "poz_no": tesdetay.get("poz_no"),
        "sanal_adet": tesdetay.get("sanal_adet"),
        "bayi_adi": tesdetay.get("bayi_adi"),
        "musteri": tesdetay.get("musteri"),
        "max_sanal_adet": bom_doc.get("quantity"),
        "serial": bom_item_doc.get("custom_serial"),
        "color": bom_item_doc.get("custom_color"),
        "remarks": sales_order.get("custom_remarks"),
        "items": grouped_items,
    }

    return data


def group_bom_items_by_category(bom_doc):
    """Group BOM Items by their item_group."""
    ITEM_GROUPS = {
        "destek_saci": ["pvc destek sacları"],
        "satis": ["pvc satış", "satış stoğu"],
        "yardimci_profil": ["pvc hat1 yardımcı profiller", "pvc hat2 yardımcı profiller"],
        "panel": ["pvc hat1 paneller"],
        "ana_profil": ["pvc hat1 ana profiller", "pvc hat2 ana profiller"],
        "cita": ["pvc hat1 çıtalar"],
        "aksesuar": ["pvc hat1 aksesuarlar", "pvc hat2 aksesuarlar"],
        "orta_kayit": ["pvc hat1 ortakayıt bağlantı", "pvc hat2 ortakayıt bağlantı"],
        "fitil_ve_esik": ["pvc hat1 fitil ve eşikler"],
        "cam_unite": [
            "cam ünite",
            "cam üniteler",
            "cam ünite üretim",
            "cam ünite malzemeler",
            "cam ünite kimyasallar",
            "cam ünite karolaj çıtaları",
            "cam ünite ara çıtalar",
            "tek camlar",
            "camlar",
        ],
        "ortak_fitil": ["ortak fitiller"],
        "ortak_vida": ["ortak vidalar"],
        "ortak_izolasyon": ["ortak izolasyon"],
        "pvc_kollari": ["pvc kolları"],
        "aluminyum_dograma_sistemi": ["alüminyum doğrama sistem aks"],
    }
    grouped_items = {}

    for item in bom_doc.items:
        item_group = frappe.get_value("Item", item.item_code, "item_group")
        normalized_group = item_group.lower()

        target_group = None
        for group_key, group_values in ITEM_GROUPS.items():
            if any(value in normalized_group for value in group_values):
                target_group = group_key
                break

        if target_group:
            if target_group not in grouped_items:
                grouped_items[target_group] = []
            grouped_items[target_group].append(
                {
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "quantity": item.qty,
                    "image": item.image,
                }
            )

    return grouped_items


def get_latest_default_bom(base_name: str):
    """Get latest default BOM matching the base name pattern."""
    boms = frappe.get_all(
        "BOM",
        filters={"name": ["like", f"{base_name}%"], "is_default": 1, "is_active": 1},
        order_by="creation desc",
        limit=1,
    )

    if not boms:
        frappe.throw(f"No active default BOM found for {base_name}")

    return frappe.get_doc("BOM", boms[0].name)
