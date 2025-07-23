import frappe
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry


def on_submit(doc, method):
    print("\n\n-- Ozerpan Ercom Sync | Job Card - On Submit -- [START]\n")
    if doc.operation != "Kalite":
        return

    sales_order_name = frappe.db.get_value("Work Order", doc.work_order, "sales_order")

    item_price = frappe.db.get_value(
        "Sales Order Item",
        {
            "parent": sales_order_name,
            "item_code": doc.production_item,
        },
        ["rate"],
    )

    production_item = frappe.get_doc("Item", doc.production_item)
    production_item.valuation_rate = item_price
    production_item.save(ignore_permissions=True)

    try:
        se_dict = make_stock_entry(
            work_order_id=doc.work_order,
            purpose="Manufacture",
        )

        se_doc = frappe.new_doc("Stock Entry")
        se_doc.update(se_dict)
        se_doc.save(ignore_permissions=True)
        se_doc.submit()
    except Exception as e:
        print(f"An error occurred: {e}")

    print("\n-- Ozerpan Ercom Sync | Job Card - On Submit -- [END]\n\n")
