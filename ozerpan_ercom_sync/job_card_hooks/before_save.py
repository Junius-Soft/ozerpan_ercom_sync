import frappe

def before_save(doc, method) -> None:
    if getattr(doc.flags, "from_after_insert", True):
        return
    if not frappe.db.exists(doc.doctype, doc.name):
        return

    print("\n\n-- Job Card Before Save -- (Start)")





    print("-- Job Card Before Save -- (End)\n\n")
