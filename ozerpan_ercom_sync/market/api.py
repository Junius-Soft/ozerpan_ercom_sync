from typing import Any, Dict, List, Optional, TypedDict

import frappe
from frappe import _

from ozerpan_ercom_sync.market.sales_order.service import create_market_sales_order
from ozerpan_ercom_sync.market.utils import get_user_customer_details


class SalesOrder(TypedDict):
    name: str
    # Add other fields that might be returned by get_list


@frappe.whitelist()
def get_ercom_orders(search_filter: Optional[str] = None) -> Dict[str, List[SalesOrder]]:
    print("\n\n\n-- Get Customer -- (START)\n")
    username: str = frappe.session.user

    customer: Optional[str] = frappe.db.get_value(
        "Customer", {"custom_user_link": username}
    )

    filters: Dict[str, Any] = {"customer": customer}

    if search_filter:
        filters["name"] = ["like", f"%{search_filter}%"]

    sales_orders: List[SalesOrder] = frappe.db.get_list(
        "Sales Order", filters=filters, order_by="creation desc", limit=10
    )

    print("\n-- Get Customer -- (END)\n\n\n")
    return {"sales_orders": sales_orders}


@frappe.whitelist()
def sales_order(data):
    return data


@frappe.whitelist()
def create_sales_order(data):
    print("\n\n-- Create Sales Order (Market) -- START\n")
    response: dict[str, any] = {}
    customer = get_user_customer_details(frappe.session.user)

    if not customer:
        frappe.throw(_("Customer not found."))

    try:
        ercom_sales_order = frappe.get_doc("Sales Order", data.get("order_no"))
    except frappe.DoesNotExistError as e:
        print(f"Ercom Sales Order not found. Error: {e}")
        ercom_sales_order = None

    response.update({"ercom_sales_order": ercom_sales_order})

    new_sales_order_result = create_market_sales_order(
        ercom_sales_order=ercom_sales_order,
        customer=customer,
        market_order_data=data,
    )

    if new_sales_order_result.get("status") == "error":
        frappe.local.response["http_status_code"] = 400
        frappe.local.response["message"] = new_sales_order_result
        return

    print("\n-- Create Sales Order (Market) -- END\n\n")
    return {
        "status": "success",
        "data": data,
    }
