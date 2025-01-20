import frappe


def on_trash(doc, method):
    print("\n\n\n-- Job Card On Trash --")

    remove_job_card_link_from_tesdetay(doc)

    print("\n\n\n")


def remove_job_card_link_from_tesdetay(job_card_doc):
    for barcode in job_card_doc.custom_barcodes:
        td = frappe.get_doc("TesDetay", barcode.tesdetay_ref)
        for os in td.operation_states:
            if os.job_card_ref == job_card_doc.name:
                td.operation_states.remove(os)
                td.save(ignore_permissions=True)
