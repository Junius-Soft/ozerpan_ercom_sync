import frappe


def on_update(doc, method):
    print("\n\n--Production Plan - On Update-- (START)\n")

    for item in doc.po_items:
        if not item.custom_workstation:
            continue
        bom = frappe.get_doc("BOM", item.bom_no)
        kkt_operation = next(
            o for o in bom.operations if o.operation == "Kaynak Köşe Temizleme"
        )
        frappe.db.set_value(
            "BOM Operation",
            kkt_operation.name,
            "workstation",
            item.custom_workstation,
        )

    print("\n--Production Plan - On Update-- (END)\n\n")
