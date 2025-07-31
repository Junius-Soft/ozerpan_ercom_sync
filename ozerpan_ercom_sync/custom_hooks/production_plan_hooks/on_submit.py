from ozerpan_ercom_sync.custom_api.tes_detay import sync_tes_detay


def on_submit(doc, method):
    print("\n\n--Production Plan - On Submit-- (START)\n")
    for so in doc.sales_orders:
        sync_tes_detay(order_no=so.sales_order, opti_no=doc.custom_opti_no)

    print("\n--Production Plan - On Submit-- (END)\n\n")
