"""
DST File Processor for Excel Files.

This module contains the DSTProcessor class responsible for processing
DST Excel files and updating Opt Genel documents accordingly.
"""

from typing import Any, Dict, List

import frappe
import pandas as pd
from frappe import _

from ozerpan_ercom_sync.custom_api.utils import get_float_value, show_progress

from ..base import ExcelProcessorInterface
from ..constants import ExcelFileType
from ..models.excel_file_info import ExcelFileInfo, SheetData


class DSTProcessor(ExcelProcessorInterface):
    """
    Processor for handling DST Excel files.

    This class implements the ExcelProcessorInterface to validate and process
    DST files that contain item data for updating Opt Genel documents.
    """

    def validate(self, file_info: ExcelFileInfo) -> None:
        """
        Validate that the file can be processed.

        Args:
            file_info: Information about the file to be processed

        Raises:
            ValueError: If validation fails
        """
        # Check if the corresponding Opt Genel document exists
        if not frappe.db.exists("Opt Genel", {"opt_code": file_info.order_no}):
            raise ValueError(
                _("Opt Genel document not found for order: {0}").format(
                    file_info.order_no
                )
            )

    def process(self, file_info: ExcelFileInfo, file_data: bytes) -> Dict[str, Any]:
        """
        Process the DST file and update the corresponding Opt Genel document.

        Args:
            file_info: Information about the file to be processed
            file_data: Binary contents of the file

        Returns:
            Dictionary with processing results
        """
        try:
            # Extract data from Excel file
            sheets: List[SheetData] = self.read_excel_file(file_data)
            if not sheets or len(sheets) == 0:
                raise ValueError(_("No data found in the Excel file"))

            sheet = sheets[0]
            df = sheet.data

            # Validate dataframe
            self._validate_dataframe(df)

            # Update Opt Genel document
            updated_count = self._update_opt_dst(file_info.order_no, df)

            return {
                "success": True,
                "message": _("DST file processed and Opt Genel updated successfully"),
                "updated_items": updated_count,
                "opt_code": file_info.order_no,
            }

        except Exception as e:
            import traceback

            error_trace = traceback.format_exc()
            frappe.log_error(
                f"Error processing DST file: {str(e)}\n{error_trace}",
                "DST File Processing Error",
            )
            frappe.db.rollback()
            return {
                "success": False,
                "message": _("Error processing DST file: {0}").format(str(e)),
                "error": str(e),
            }

    def get_supported_file_type(self) -> ExcelFileType:
        """
        Get the file type supported by this processor.

        Returns:
            The supported Excel file type
        """
        return ExcelFileType.DST

    def _validate_dataframe(self, df: pd.DataFrame) -> None:
        """
        Validate DataFrame meets requirements.

        Args:
            df: DataFrame to validate

        Raises:
            ValueError: If validation fails
        """
        if not isinstance(df, pd.DataFrame) or df.empty:
            raise ValueError(_("Invalid or empty Excel file"))

        required_columns = {"STOK KODU", "AÇIKLAMA", "OLCU"}
        if not required_columns.issubset(df.columns):
            missing_cols = required_columns - set(df.columns)
            raise ValueError(
                _("Missing required columns: {0}").format(", ".join(missing_cols))
            )

    def _process_row(self, row: pd.Series) -> Dict[str, Any]:
        """
        Process a single DataFrame row.

        Args:
            row: DataFrame row to process

        Returns:
            Dictionary with processed item data

        Raises:
            ValueError: If item is not found
        """
        stock_code = str(row["STOK KODU"]).strip()
        item_code = frappe.db.exists("Item", {"item_code": stock_code})

        if not item_code:
            raise ValueError(_("Item not found for stock code: {0}").format(stock_code))

        return {
            "item_code": item_code,
            "item_name": str(row["AÇIKLAMA"]).strip(),
            "size": get_float_value(str(row["OLCU"])),
            "quantity": int(row["qty"]),
        }

    def _update_opt_dst(self, opt_code: str, df: pd.DataFrame) -> int:
        """
        Update Opt Genel document with DST data.

        Args:
            opt_code: The opt code to update
            df: DataFrame containing the data

        Returns:
            Number of items processed

        Raises:
            Exception: If update fails
        """
        try:
            # Get the Opt Genel document
            opt = frappe.get_doc("Opt Genel", {"opt_code": opt_code})

            # Group by stock code, description and size
            grouped_df = (
                df.groupby(["STOK KODU", "AÇIKLAMA", "OLCU"])
                .size()
                .reset_index(name="qty")
            )

            items_data = []
            processed_count = 0

            for idx, row in grouped_df.iterrows():
                # Show progress if in interactive mode
                try:
                    show_progress(
                        idx + 1,
                        len(grouped_df),
                        _("DST table sync"),
                        _("Updating items {0} of {1}").format(idx + 1, len(grouped_df)),
                    )
                except Exception:
                    # Progress display might not be available in all contexts
                    pass

                try:
                    item_data = self._process_row(row)
                    items_data.append(item_data)
                    processed_count += 1
                except ValueError as e:
                    frappe.log_error(
                        f"Error processing item in DST file: {str(e)}",
                        "DST Item Processing Error",
                    )
                    # Continue processing other items rather than failing completely
                    continue

            # Update the document
            opt.set("dst_list", items_data)
            opt.save(ignore_permissions=True)

            frappe.db.commit()

            return processed_count

        except Exception as e:
            frappe.log_error(
                f"Error updating Opt Genel document: {str(e)}",
                "DST Document Update Error",
            )
            raise
