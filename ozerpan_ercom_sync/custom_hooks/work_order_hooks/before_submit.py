import frappe


def before_submit(doc, method):
    print("\n\n-- Ozerpan Ercom Sync | Work Order - On Submit -- [START]\n")

    doc.status = "In Process"
    doc.actual_start_date = frappe.utils.now()

    print("\n-- Ozerpan Ercom Sync | Work Order - On Submit -- [END]\n\n")
