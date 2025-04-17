from ozerpan_ercom_sync.utils import bulk_insert_child_rows, timer


@timer
def after_insert(doc, method):
    print("\n\n\n-- Job Card After Insert --")
    if doc.operation == "Cam":
        add_job_cards_into_camliste(doc)
    else:
        add_job_cards_into_tesdetay(doc)


def add_job_cards_into_camliste(job_card_doc):
    # TODO: Use bulk insert

    rows = []

    for i, glass in enumerate(job_card_doc.custom_glasses):
        rows.append(
            {
                "parent": glass.glass_ref,
                "job_card_ref": job_card_doc.name,
                "status": "Pending",
                "operation": job_card_doc.operation,
                "is_corrective": job_card_doc.is_corrective_job_card,
            }
        )

    bulk_insert_child_rows(
        child_table="CamListe Job Card",
        parenttype="CamListe",
        parentfield="job_cards",
        rows=rows,
        extra_fields=["job_card_ref", "status", "operation", "is_corrective"],
    )


def add_job_cards_into_tesdetay(job_card_doc):
    rows = []

    for i, barcode in enumerate(job_card_doc.custom_barcodes):
        rows.append(
            {
                "parent": barcode.tesdetay_ref,
                "job_card_ref": job_card_doc.name,
                "status": "Pending",
                "operation": job_card_doc.operation,
                "is_corrective": job_card_doc.is_corrective_job_card,
            }
        )

    bulk_insert_child_rows(
        child_table="TesDetay Operation Status",
        parenttype="TesDetay",
        parentfield="operation_states",
        rows=rows,
        extra_fields=["job_card_ref", "status", "operation", "is_corrective"],
    )
