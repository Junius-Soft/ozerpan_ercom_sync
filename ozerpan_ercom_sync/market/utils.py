import frappe


def get_user_customer_details(username):
    try:
        return frappe.get_doc("Customer", {"custom_user_link": username})
    except Exception:
        return None


def update_sales_order_taxes(sales_order: any) -> None:
    """Update sales order tax information"""
    tax_account = _get_tax_account()

    existing_tax = next(
        (tax for tax in sales_order.taxes if tax.account_head == tax_account.get("name")),
        None,
    )

    if not existing_tax:
        sales_order.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": tax_account.get("name"),
                "rate": tax_account.get("tax_rate"),
                "description": tax_account.get("name"),
            },
        )


def _get_tax_account() -> any:
    """Get or create tax account"""

    DEFAULT_TAX_ACCOUNT = {
        "name": "ERCOM HESAPLANAN KDV 20",
        "number": "391.99",
        "tax_rate": 20,
    }

    account_filters = {
        "account_name": DEFAULT_TAX_ACCOUNT["name"],
        "account_number": DEFAULT_TAX_ACCOUNT["number"],
    }

    if not frappe.db.exists("Account", account_filters):
        company = frappe.get_doc("Company", frappe.defaults.get_user_default("company"))
        account = frappe.new_doc("Account")
        account.update(
            {
                "account_name": DEFAULT_TAX_ACCOUNT["name"],
                "account_number": DEFAULT_TAX_ACCOUNT["number"],
                "parent_account": f"391 - HESAPLANAN KDV - {company.abbr}",
                "currency": "TRY",
                "account_type": "Tax",
                "tax_rate": DEFAULT_TAX_ACCOUNT["tax_rate"],
            }
        )
        account.save(ignore_permissions=True)
        return account

    return frappe.get_doc("Account", account_filters)
