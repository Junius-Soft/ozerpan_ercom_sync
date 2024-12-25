import logging
from typing import Dict

import frappe
import pandas as pd
from frappe import _

from ozerpan_ercom_sync.custom_api.utils import get_float_value, show_progress


def validate_dataframe(df: pd.DataFrame) -> None:
    """Validate DataFrame meets requirements"""
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError("Invalid or empty Excel file")

    required_columns = {"STOK KODU", "AÇIKLAMA", "OLCU"}
    if not required_columns.issubset(df.columns):
        raise ValueError(
            f"Missing required columns: {required_columns - set(df.columns)}"
        )


def process_dst_file(file: Dict, logger: logging.Logger) -> None:
    try:
        df = pd.read_excel(file.get("path"))
        validate_dataframe(df)
        update_opt_dst(file.get("code"), df, logger)

    except Exception as e:
        logger.error(f"Error processing Excel file: {str(e)}")
        raise


def process_row(row: pd.Series) -> Dict:
    """Process a single DataFrame row"""
    stock_code = str(row["STOK KODU"])
    item_code = frappe.db.exists("Item", {stock_code})

    if not item_code:
        error_msg = f"Item not found for stock code: {stock_code}"
        raise ValueError(error_msg)

    return {
        "item_code": item_code,
        "item_name": str(row["AÇIKLAMA"]),
        "size": get_float_value(str(row["OLCU"])),
        "quantity": row["qty"],
    }


def update_opt_dst(opt_code: str, df: pd.DataFrame, logger: logging.Logger) -> None:
    try:
        opt = frappe.get_doc("Opt Genel", {"opt_code": opt_code})
        items_data = []
        df_len = len(df)

        # Group by stock code, description and size
        grouped_df = (
            df.groupby(["STOK KODU", "AÇIKLAMA", "OLCU"]).size().reset_index(name="qty")
        )
        print("GroupDF:", grouped_df)

        for idx, row in grouped_df.iterrows():
            show_progress(
                idx + 1,
                len(grouped_df),
                _("Opt DST table sync."),
                _("Updating items {0} of {1}").format(idx + 1, len(grouped_df)),
            )

            try:
                item_data = process_row(row)
                item_data["qty"] = int(row["qty"])
                items_data.append(item_data)
            except ValueError as e:
                logger.error(str(e))
                frappe.throw(str(e))

        opt.set("dst_list", items_data)
        opt.save(ignore_permissions=True)
        logger.info(f"Successfully updated Opt Genel: {opt.name}")

    except Exception as e:
        logger.error(f"Error creating/updating Opt Genel doc: {str(e)}")
        raise
