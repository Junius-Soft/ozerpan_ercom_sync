from datetime import datetime

import frappe

from ozerpan_ercom_sync.market.utils import update_sales_order_taxes

from .operations import MarketOrderOperation


def create_market_sales_order(
    customer: dict,
    market_order_data: dict,
    ercom_sales_order: dict | None = None,
):
    print("\n\n-- Create Market Sales Order -- START\n")

    missing_items = []

    order_no = generate_market_order_no(
        ercom_sales_order=ercom_sales_order.get("name")
        if ercom_sales_order is not None
        else None,
    )

    print("\n[DEBUG]:", "Order No:", order_no, "\n")

    customer_name = customer.get("customer_name")
    delivery_date = frappe.utils.add_to_date(
        datetime.now(),
        days=10,
        as_string=True,
    )

    new_sales_order = frappe.new_doc("Sales Order")
    new_sales_order_data = {
        "name": order_no,
        "custom_ercom_order_ref": ercom_sales_order.name if ercom_sales_order else None,
        "transaction_date": frappe.utils.now(),
        "delivery_date": delivery_date,
        "customer": customer_name,
        "custom_remarks": market_order_data.get("remarks"),
        "company": frappe.defaults.get_user_default("company"),
        "order_type": "Sales",
        "currency": "TRY",
        "selling_price_list": "Standard Selling",
        "apply_discount_on": "Grand Total",
        "additional_discount_percentage": customer.get("custom_total_discount_rate"),
    }

    new_sales_order.update(new_sales_order_data)
    update_sales_order_taxes(new_sales_order)

    for poz in market_order_data.get("poz_list"):
        item_code = f"{order_no}-{poz.get('poz_no')}"
        new_item = _create_market_item(item_code=item_code, poz_data=poz)
        new_bom_result = _create_market_bom(
            item_code=item_code,
            poz_data=poz,
            missing_items=missing_items,
        )
        new_sales_order.append(
            "items",
            {
                "item_code": new_item.item_code,
                "item_name": new_item.item_name,
                "delivery_date": delivery_date,
                "qty": new_item.custom_quantity,
                "uom": new_item.stock_uom,
                "rate": poz.get("unit_price"),
            },
        )

    if missing_items:
        frappe.db.rollback()
        return new_bom_result

    new_sales_order.save(ignore_permissions=True)

    print("\n-- Create Market Sales Order -- END\n\n")
    return {"status": "success"}


def _create_market_bom(item_code: str, poz_data: dict, missing_items: list):
    print("\n\n-- Create Market BOM -- START\n")

    bom = frappe.new_doc("BOM")
    bom.item = item_code
    bom.company = frappe.defaults.get_user_default("Company")
    bom.quantity = poz_data.get("quantity")
    bom.rm_cost_as_per = "Price List"
    bom.buying_price_list = "Standard Buying"

    _add_operations_to_bom(bom=bom, product_type=poz_data.get("product_name"))

    items_table = []

    for group_name, materials in poz_data.get("production_materials").items():
        for m in materials:
            if not frappe.db.exists("Item", m.get("stock_code")):
                missing_items.append(
                    {
                        "stock_code": m.get("stock_code"),
                        "type": group_name,
                        "order_no": item_code.split("-")[0],
                        "poz_no": item_code.split("-")[1],
                    }
                )

            else:
                items_table.append(
                    {
                        "item_code": m.get("stock_code"),
                        "item_name": m.get("stock_code"),
                        "qty": m.get("quantity"),
                        "uom": m.get("unit_of_measure", "Nos"),
                        # "rate": 0,
                    }
                )

    if len(missing_items) > 0:
        return {
            "status": "error",
            "missing_items": missing_items,
        }

    bom.set("items", items_table)
    bom.save(ignore_permissions=True)
    bom.submit()

    print("\n-- Create Market BOM -- END\n\n")


def _create_market_item(item_code: str, poz_data: dict[str, any]):
    print("\n\n-- Create Market Item -- START\n")

    if frappe.db.exists("Item", {"item_code": item_code}):
        item = frappe.get_doc("Item", {"item_code": item_code})
    else:
        item = frappe.new_doc("Item")

    item.update(
        {
            "item_code": item_code,
            "item_name": item_code,
            "item_group": poz_data.get("product_name"),
            "stock_uom": "Nos",
            "valuation_rate": poz_data.get("unit_price"),
            "has_serial_no": 1,
            "serial_no_series": f"{item_code}-.#",
            "custom_quantity": poz_data.get("quantity", 1),
            "custom_remarks": poz_data.get("remarks"),
            "default_bom": None,
        }
    )
    item.save(ignore_permissions=True)
    print("\n-- Create Market Item -- END\n\n")
    return item


def generate_market_order_no(ercom_sales_order: str | None = None):
    """
    Generate a unique market order number in the format MM000001.
    Market orders start with "MM" followed by 6 digits.
    """

    if ercom_sales_order:
        return f"M{ercom_sales_order}"

    # Query for existing market orders (those starting with "MM")
    existing_orders = frappe.db.sql(
        """
        SELECT name
        FROM `tabSales Order`
        WHERE name LIKE 'MM%'
        ORDER BY name DESC
        LIMIT 1
        """,
        as_dict=True,
    )

    if existing_orders:
        # Extract the numeric part from the latest order
        latest_order = existing_orders[0]["name"]
        try:
            # Get the numeric part after "MM" and increment it
            numeric_part = int(latest_order[2:])
            next_number = numeric_part + 1
        except (ValueError, IndexError):
            # If there's an issue parsing, start from 1
            next_number = 1
    else:
        # No existing market orders, start from 1
        next_number = 1

    # Format the number with leading zeros (6 digits total)
    return f"MM{next_number:06d}"


def _add_operations_to_bom(bom: any, product_type: str):
    operation_name = MarketOrderOperation[product_type].value
    operation_items = []

    try:
        operation_doc = frappe.get_doc("Operation", operation_name)
        operation_items.append(
            {
                "operation": operation_doc.name,
                "workstation": operation_doc.workstation,
                "time_in_mins": 9,
            }
        )

        quality_operation_doc = frappe.get_doc("Operation", "Kalite")
        operation_items.append(
            {
                "operation": quality_operation_doc.name,
                "workstation": quality_operation_doc.workstation,
                "time_in_mins": 9,
            }
        )
    except Exception as e:
        print(f"An error occurred: {e}")
        raise

    bom.with_operations = 1
    bom.set("operations", operation_items)
