import frappe


@frappe.whitelist()
def get_poz_data(barcode: str):
    print("\n\n\n-- Get Poz Data API --")

    print("Barcode:", barcode)
    tesdetay = frappe.get_doc("TesDetay", {"barkod": barcode})

    bom_name = f"BOM-{tesdetay.siparis_no}-{tesdetay.poz_no}"
    bom_doc = get_latest_default_bom(bom_name)
    bom_item_doc = frappe.get_doc("Item", f"{tesdetay.siparis_no}-{tesdetay.poz_no}")

    print(f"{bom_item_doc}")

    print("BOM fields:")
    for field in bom_doc.items[0].__dict__:
        print(f"{field}: {bom_doc.items[0].get(field)}")

    # print("BOM Item fields:")
    # for field in bom_item_doc.__dict__:
    #     print(f"{field}: {bom_item_doc.get(field)}")
    # print(f"\n{bom_item_doc.image}\n")

    grouped_items = group_bom_items_by_category(bom_doc)

    if bom_doc.custom_accessory_kit:
        kit = frappe.get_doc("Item", bom_doc.custom_accessory_kit)
        print("\n\nKit:", kit)
        print("bom_doc_qty:", bom_doc.custom_accessory_kit_qty)
        grouped_items["accessory_kit"] = [
            {
                "item_code": kit.item_code,
                "item_name": kit.item_name,
                "quantity": bom_doc.custom_accessory_kit_qty,
                "image": kit.image,
            }
        ]

    for group, items in grouped_items.items():
        print(f"\n{group}")
        for item in items:
            print(item)

    data = {
        "siparis_no": tesdetay.get("siparis_no"),
        "poz_no": tesdetay.get("poz_no"),
        "sanal_adet": tesdetay.get("sanal_adet"),
        "bayi_adi": tesdetay.get("bayi_adi"),
        "max_sanal_adet": bom_doc.get("quantity"),
        "serial": bom_item_doc.get("serial"),
        "color": bom_item_doc.get("color"),
        "items": grouped_items,
    }
    return data
    print("\n\n\n")


def group_bom_items_by_category(bom_doc):
    """Group BOM Items by their item_group."""
    grouped_items = {}

    for item in bom_doc.items:
        item_group = frappe.get_value("Item", item.item_code, "item_group")
        if item_group not in grouped_items:
            grouped_items[item_group] = []
        grouped_items[item_group].append(
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
