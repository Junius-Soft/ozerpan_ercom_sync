import frappe


def after_insert(doc, method):
    print("\n\n\n-- Job Card After Insert --")

    add_barcodes_into_job_card(doc)

    print("\n\n\n")


def add_barcodes_into_job_card(job_card_doc):
    for barcode in job_card_doc.custom_barcodes:
        td = frappe.get_doc("TesDetay", barcode.tesdetay_ref)
        td.append(
            "operation_states",
            {
                "job_card_ref": job_card_doc.name,
                "status": "Pending",
                "operation": job_card_doc.operation,
                "is_corrective": job_card_doc.is_corrective_job_card,
            },
        )
        td.save(ignore_permissions=True)
