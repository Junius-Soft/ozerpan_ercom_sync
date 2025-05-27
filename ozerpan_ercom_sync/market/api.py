from typing import Any, Dict, List, Optional, TypedDict

import frappe


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
