import frappe
from frappe import _


def before_save(doc, method):
    if doc.workflow_state == "Muhasebe Onay Bekleniyor":
        if not doc.custom_mly_list_uploaded:
            frappe.throw(_("Please upload MLY file."))
        elif doc.custom_has_glass_item and not doc.custom_glass_list_uploaded:
            frappe.throw(_("Please upload CAMLISTE file."))
    # frappe.throw(doc.workflow_state)
