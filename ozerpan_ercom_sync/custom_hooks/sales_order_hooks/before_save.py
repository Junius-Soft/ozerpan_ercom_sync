import frappe
from frappe import _


def before_save(doc, method):
    print("\n\nSales Order Before Save -- START\n")

    if not doc.custom_ercom_order_no:
        return

    if doc.workflow_state == "Muhasebe Onay Bekleniyor":
        if not doc.custom_mly_list_uploaded or not doc.custom_price_list_uploaded:
            frappe.throw(_("Please upload required files."))
        elif doc.custom_has_glass_item and not doc.custom_glass_list_uploaded:
            frappe.throw(_("Please upload CAMLISTE file."))

    print("\n\nSales Order Before Save -- END\n")
