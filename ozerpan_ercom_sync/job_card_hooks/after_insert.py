import frappe

from ozerpan_ercom_sync.utils import timer


@timer
def after_insert(doc, method):
    print("\n\n\n-- Job Card After Insert --")
    if doc.operation == "Cam":
        add_job_cards_into_camliste(doc)
    else:
        add_barcodes_into_job_card(doc)


@timer
def add_job_cards_into_camliste(job_card_doc):
    for glass in job_card_doc.custom_glasses:
        g = frappe.get_doc("CamListe", glass.glass_ref)
        g.append(
            "job_cards",
            {
                "job_card_ref": job_card_doc.name,
                "status": "Pending",
                "operation": job_card_doc.operation,
                "is_corrective": job_card_doc.is_corrective_job_card,
            },
        )

        g.save()


@timer
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
