"""
Utility functions for price list processing.

This module contains helper functions for processing price lists,
calculating item prices, and updating sales orders.
"""

from typing import Any, Dict, List, Optional, Tuple

import frappe
import numpy as np
from frappe import _


def validate_sales_order(order_no: str) -> None:
    """
    Validate that a draft sales order exists with the given order number.

    Args:
        order_no: The ERCOM order number to validate

    Raises:
        ValueError: If the order number is missing or no matching sales order is found
    """
    if not order_no:
        raise ValueError(_("Order number is required in filename"))

    if not frappe.db.exists(
        "Sales Order",
        {
            "custom_ercom_order_no": order_no,
            "status": "Draft",
        },
    ):
        raise ValueError(
            _(
                "No such Sales Order found, Please Sync the database before uploading the file."
            )
        )


def get_sales_order(order_no: str) -> Any:
    """
    Get sales order document by ERCOM order number.

    Args:
        order_no: The ERCOM order number to find

    Returns:
        The sales order document

    Raises:
        ValueError: If no matching sales order is found
    """
    sales_order = frappe.get_doc(
        "Sales Order",
        {
            "custom_ercom_order_no": order_no,
            "status": "Draft",
        },
    )

    if not sales_order:
        raise ValueError(
            _("Sales Order not found for order number: {0}").format(order_no)
        )

    return sales_order


def preprocess_excel_data(df: Any) -> Any:
    """
    Clean and preprocess the Excel data.

    Args:
        df: Pandas DataFrame containing the Excel data

    Returns:
        Preprocessed DataFrame

    Raises:
        ValueError: If the DataFrame is empty after preprocessing
    """
    # Replace NaN values with None
    df = df.replace({np.nan: None})
    # Drop rows that are completely empty
    df = df.dropna(how="all")
    # Drop columns that are completely empty
    df = df.dropna(axis=1, how="all")

    if df.empty:
        raise ValueError(_("No data found in the Excel sheet"))

    return df


def extract_price_details(records: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Extract price details such as taxes and discounts from records.

    Args:
        records: List of record dictionaries from the Excel file

    Returns:
        Dictionary of price details with keys as detail names and values as amounts
    """
    price_details: Dict[str, float] = {}

    for record in records:
        if record.get("STOK_KODU") is None and record.get("KDV_ORANI"):
            kdv_key = record.get("KDV_ORANI")
            if kdv_key:
                price_details[kdv_key.lower().replace(" ", "_")] = record.get("TUTAR", 0)

    return price_details


def extract_order_details(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    record = records[0]
    delivery_date = f"{int(record.get('SEVK_TAR_GUN'))}-{int(record.get('SEVK_TAR_AY'))}-{int(record.get('SEVK_TAR_YIL'))}"
    delivery_date = frappe.utils.getdate(delivery_date)

    order_details: Dict[str, Any] = {
        "customer": record.get("MUSTERI_CARI_UNVANI"),
        "authorized_staff": record.get("YETKILI"),
        "date": record.get("TARIH"),
        "delivery_date": delivery_date,
    }
    poz_details: Dict[str, int] = {}
    for record in records:
        key = record.get("SATIS_NO")
        value = record.get("MUSTERI_CARI_UNVANI")
        if key == "Toplam Poz":
            poz_details.update({"total_poz": value})
        if key == "Toplam Doğrama":
            poz_details.update({"total_cutting": value})

    return {**order_details, **poz_details}


def create_or_update_fiyat2_doc(
    order_no: str,
    records: List[Dict[str, Any]],
    order_details: Dict[str, Any],
    price_details: Dict[str, float],
):
    try:
        fiyat2_doc = frappe.get_doc("Fiyat2 List", order_no)
    except frappe.DoesNotExistError:
        fiyat2_doc = frappe.new_doc("Fiyat2 List")
    except Exception as e:
        print(f"An error occurred: {e}")

    items = []

    for r in records:
        if r.get("SATIS_NO") != order_no:
            continue

        stock_code = r.get("STOK_KODU").lstrip("#")

        if not frappe.db.exists("Item", stock_code):
            if stock_code.upper().startswith("AKS"):
                stock_code = f"Q{stock_code}"
            else:
                raise ValueError(_("Item [{0}] not found").format(stock_code))

        items.append(
            {
                "stock_code": stock_code,
                "stock_name": r.get("STOK_ADI"),
                "qty": r.get("MIKTAR"),
                "uom": r.get("BIRIM"),
                "unit_price": r.get("BIRIM_FIYAT"),
                "discount": r.get("ISKONTO"),
                "kdv_rate": r.get("KDV_ORANI"),
                "price": r.get("TUTAR"),
            }
        )

    fiyat2_doc.update(
        {
            "order_no": order_no,
            "total_poz": order_details.get("total_poz"),
            "total_cutting": order_details.get("total_cutting"),
            "customer": order_details.get("customer"),
            "authorized_staff": order_details.get("authorized_staff"),
            "date": order_details.get("date"),
            "delivery_date": order_details.get("delivery_date"),
            "assembly": price_details.get("montaj"),
            "discount1": abs(price_details.get("i̇skonto_1")),
            "discount2": price_details.get("i̇skonto_2"),
            "kdv_total": price_details.get("kdv_toplamı"),
            "subtotal": price_details.get("ara_toplam"),
            "grand_total": price_details.get("genel_toplam"),
        }
    )

    fiyat2_doc.set("items", items)
    fiyat2_doc.save(ignore_permissions=True)

    return fiyat2_doc


def calculate_glass_item_price(
    item_code: str, item_qty: float, records: List[Dict[str, Any]]
) -> Optional[float]:
    """
    Calculate the price for a glass item.

    Args:
        item_code: The item code
        item_qty: The item quantity
        records: List of record dictionaries from the Excel file

    Returns:
        Calculated price or None if not found
    """
    code_parts = item_code.split("-")
    item_doc = frappe.get_doc("Item", item_code)
    glass_stock_code = code_parts[2]
    glass_qty = item_doc.get("custom_amount_per_piece")

    record = next(
        (
            r
            for r in records
            if r.get("STOK_KODU") and r.get("STOK_KODU").lstrip("#") == glass_stock_code
        ),
        None,
    )

    if record is None:
        frappe.log_error(
            f"Glass stock code {glass_stock_code} not found in price list",
            "Price List Processing Warning",
        )
        return None

    unit_price = record.get("BIRIM_FIYAT")
    if unit_price is None:
        return None

    return (unit_price * glass_qty) / item_qty


def calculate_pvc_item_price(
    item_code: str, bom_no: str, records: List[Dict[str, Any]]
) -> Tuple[float, int]:
    """
    Calculate the price for a PVC item using its BOM.

    Args:
        item_code: The item code
        bom_no: The BOM number
        records: List of record dictionaries from the Excel file

    Returns:
        Tuple of (calculated price, update count)
    """
    bom = frappe.get_doc("BOM", bom_no)
    kits = bom.get("custom_accessory_kits")
    bom_qty: float = bom.get("quantity")
    item_price: float = 0.0
    update_success = True

    # Process BOM items
    for bom_item in bom.get("items"):
        i_code = bom_item.get("item_code")
        record = next(
            (
                r
                for r in records
                if r.get("STOK_KODU") and r.get("STOK_KODU").lstrip("#") == i_code
            ),
            None,
        )
        if record is None:
            frappe.msgprint(f"Warning: BOM item {i_code} not found in price list")
            continue

        unit_price = record.get("BIRIM_FIYAT")
        if unit_price is None:
            frappe.msgprint(f"Warning: Unit price not found for BOM item {i_code}")
            continue

        qty = round(bom_item.get("qty", 0), 2)
        price = round(unit_price * (qty / bom_qty), 2)
        item_price += price

    # Process accessory kits
    for kit in kits:
        kit_name: str = kit.get("kit_name")
        kit_qty: float = float(kit.get("quantity"))
        if kit_name.startswith("Q"):
            kit_name = kit_name.lstrip("Q")

        record = next(
            (
                r
                for r in records
                if r.get("STOK_KODU") and r.get("STOK_KODU").lstrip("#") == kit_name
            ),
            None,
        )
        if record is None:
            frappe.msgprint(f"Warning: Kit {kit_name} not found in price list")
            continue

        unit_price = record.get("BIRIM_FIYAT")
        if unit_price is None:
            frappe.msgprint(f"Warning: Unit price not found for kit {kit_name}")
            continue

        price = round(unit_price * (kit_qty / bom_qty), 2)
        item_price += price

    return (item_price, 1 if update_success else 0)


def calculate_total_discount(price_details: Dict[str, float]) -> float:
    """
    Calculate the total discount amount from price details.

    Args:
        price_details: Dictionary of price details

    Returns:
        Total discount amount
    """
    return sum(
        abs(value) for key, value in price_details.items() if "skonto" in key.lower()
    )


def update_sales_order(
    sales_order: Any, price_list: Dict[str, float], total_discount: float
) -> int:
    """
    Update the sales order with calculated prices and discount.

    Args:
        sales_order: The sales order document
        price_list: Dictionary mapping item codes to prices
        total_discount: The total discount amount

    Returns:
        Number of updated items
    """
    updated_count = 0

    for item in sales_order.items:
        item_code = item.get("item_code")
        if item_code in price_list:
            item.rate = price_list[item_code]
            updated_count += 1

    sales_order.apply_discount_on = "Net Total"
    sales_order.discount_amount = total_discount
    sales_order.custom_price_list_uploaded = 1

    if updated_count > 0:
        sales_order.save()
        frappe.db.commit()

    return updated_count
