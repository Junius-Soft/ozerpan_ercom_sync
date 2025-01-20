import frappe


def before_save(doc, method):
    print("\n\n\n-- Job Card Before Save --")
    production_item = doc.production_item
    operation_name = doc.operation
    order_no, poz_no = production_item.split("-")

    if operation_name == "Profil Temin" or operation_name == "Sac Kesim":
        return

    barcodes = []
    tesdetay_list = get_tesdetay_list(order_no, poz_no)

    for td in tesdetay_list:
        if "KAYIT" in td.get("model"):
            if (
                operation_name == "Kaynak Köşe Temizleme"
                or operation_name == "Kanat Hazırlık"
                or operation_name == "Kanat Bağlama"
            ):
                continue

        operation_status = "Pending"
        for os in td.get("operation_states"):
            if os.get("job_card_ref") == doc.name:
                operation_status = os.get("status")
                break

        barcodes.append(
            {
                "tesdetay_ref": td.get("name"),
                "barcode": td.get("barkod"),
                "model": td.get("model"),
                "stock_code": td.get("stok_kodu"),
                "poz_no": td.get("poz_no"),
                "sanal_adet": td.get("sanal_adet"),
                "status": operation_status,
            }
        )

    barcodes = sorted(barcodes, key=lambda x: x["sanal_adet"])
    doc.set("custom_barcodes", barcodes)


def get_tesdetay_list(order_no, poz_no):
    results = frappe.db.sql(
        """
        SELECT
            td.name,
            td.poz_no,
            td.sanal_adet,
            td.barkod,
            td.model,
            td.stok_kodu,
            os.job_card_ref,
            os.status,
            os.idx
        FROM `tabTesDetay` td
        LEFT JOIN `tabTesDetay Operation Status` os ON td.name = os.parent
        WHERE siparis_no = %s AND poz_no = %s
        ORDER BY td.name, os.idx
        """,
        (order_no, poz_no),
        as_dict=1,
    )

    current_doc = None
    organized_data = []
    for row in results:
        if current_doc is None or current_doc["name"] != row.name:
            current_doc = {
                "name": row.name,
                "poz_no": row.poz_no,
                "sanal_adet": row.sanal_adet,
                "barkod": row.barkod,
                "model": row.model,
                "stok_kodu": row.stock_kodu,
                "operation_states": [],
            }
            organized_data.append(current_doc)

        if row.job_card_ref:
            current_doc["operation_states"].append(
                {"job_card_ref": row.job_card_ref, "status": row.status, "idx": row.idx}
            )

    return organized_data
