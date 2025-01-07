import frappe


def after_insert(doc, method):
    print("\n\n\n")

    bom = frappe.get_doc("BOM", doc.bom_no)

    print(bom.get("items"))
    print(doc.custom_ozerpan_items)

    print("\n\n\n")
    # return
    frappe.throw("-- Job Card After Insert --")
