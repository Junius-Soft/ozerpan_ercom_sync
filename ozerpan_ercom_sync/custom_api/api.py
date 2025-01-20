import frappe


@frappe.whitelist()
def read_barcode(barcode: str, employee: str, operation: str):
    print("\n\n\n-- Read Barcode --")

    td = frappe.get_doc("TesDetay", {"barkod": barcode})

    production_item_name = f"{td.siparis_no}-{td.poz_no}"
    job_card = frappe.get_doc(
        "Job Card", {"production_item": production_item_name, "operation": operation}
    )

    connected_barcodes = list(
        filter(
            lambda x: x.model == td.model and int(x.sanal_adet) == int(td.sanal_adet),
            job_card.custom_barcodes,
        )
    )
    # TODO: Handle Job Card Start|Pause|Complete
    for cb in connected_barcodes:
        cb_doc = frappe.get_doc("TesDetay", cb.tesdetay_ref)
        for os in cb_doc.operation_states:
            if os.job_card_ref == job_card.name:
                os.status = "In Progress"
                os.save(ignore_permissions=True)
    job_card.save(ignore_permissions=True)

    print("\n\n\n")

    # frappe.throw("-- Read Barcode --")
