import frappe


def on_update(doc, method):
    print("\n\n--Production Plan - On Update-- (START)\n")

    for item in doc.po_items:
        parts = item.item_code.split("-")
        is_pvc = False if len(parts) > 2 else True

        if is_pvc:
            bom = frappe.get_doc("BOM", item.bom_no)
            kkt_operation = next(
                (o for o in bom.operations if o.operation == "Kaynak Köşe Temizleme"),
                None,
            )
            if kkt_operation:
                frappe.db.set_value(
                    "BOM Operation",
                    kkt_operation.name,
                    "workstation",
                    item.custom_workstation,
                )
        else:
            item.custom_workstation = "Bottero"

    print("\n--Production Plan - On Update-- (END)\n\n")
