"""
OPT File Processor for Excel Files.

This module contains the OPTProcessor class responsible for processing
OPT Excel files and creating/updating Opt Genel documents.
"""

import re
from typing import Any, Dict, List

import frappe
import pandas as pd
from frappe import _

from ozerpan_ercom_sync.custom_api.utils import get_float_value
from ozerpan_ercom_sync.utils import get_mysql_connection

from ..base import ExcelProcessorInterface
from ..constants import ExcelFileType
from ..models.excel_file_info import ExcelFileInfo, SheetData


class OPTProcessor(ExcelProcessorInterface):
    """
    Processor for handling OPT Excel files.

    This class implements the ExcelProcessorInterface to validate and process
    OPT files that contain profile data for creating/updating Opt Genel documents.
    """

    def validate(self, file_info: ExcelFileInfo) -> None:
        """
        Validate that the file can be processed.

        Args:
            file_info: Information about the file to be processed

        Raises:
            ValueError: If validation fails
        """
        # Basic validation - OPT files don't have strict pre-requirements
        # Additional validation will be done during processing
        pass

    def process(self, file_info: ExcelFileInfo, file_data: bytes) -> Dict[str, Any]:
        """
        Process the OPT file and create/update the corresponding Opt Genel document.

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
            if df.empty:
                raise ValueError(_("Empty sheet found"))

            # Extract opt number from column header
            opt_no = self._extract_opt_no(df.columns[3] if len(df.columns) > 3 else "")
            if not opt_no:
                raise ValueError(_("Could not extract opt number from Excel file"))

            # Clean and prepare dataframe
            df.columns = df.iloc[1].str.strip()
            df = df.iloc[2:].reset_index(drop=True)
            df = df.dropna(subset=["Stok Kodu"]).reset_index(drop=True)

            # Validate cleaned dataframe
            if df.empty:
                raise ValueError(_("No valid data rows found after cleaning"))

            # Get machine number from database
            machine_no = self._get_machine_number(opt_no)
            if not machine_no:
                raise ValueError(
                    _("Machine not found for opt number: {0}").format(opt_no)
                )

            # Create/update Opt Genel document
            doc_name = self._create_opt_genel_doc(
                opt_no, file_info.order_no, machine_no, df
            )

            # Optionally create/update Super Kesim document (uncomment when needed)
            super_kesim_name = self._create_super_kesim_doc(
                opt_no, file_info.order_no, machine_no, df
            )

            return {
                "success": True,
                "message": _("OPT file processed and Opt Genel updated successfully"),
                "opt_no": opt_no,
                "opt_code": file_info.order_no,
                "document_name": doc_name,
                "super_kesim_document_name": super_kesim_name,
                "machine_no": machine_no,
            }

        except Exception as e:
            import traceback

            error_trace = traceback.format_exc()
            frappe.log_error(
                f"Error processing OPT file: {str(e)}\n{error_trace}",
                "OPT File Processing Error",
            )
            frappe.db.rollback()
            return {
                "success": False,
                "message": _("Error processing OPT file: {0}").format(str(e)),
                "error": str(e),
            }

    def get_supported_file_type(self) -> ExcelFileType:
        """
        Get the file type supported by this processor.

        Returns:
            The supported Excel file type
        """
        return ExcelFileType.OPT

    def _extract_opt_no(self, column_header: str) -> str:
        """
        Extract opt number from column header string.

        Args:
            column_header: The column header to extract from

        Returns:
            The extracted opt number or empty string if not found
        """
        match = re.match(r"(\d+)", str(column_header))
        return match.group(1) if match else ""

    def _get_machine_number(self, opt_no: str) -> int:
        """
        Get machine number from database for given opt number.

        Args:
            opt_no: The opt number to look up

        Returns:
            The machine number, or 0 if not found
        """
        try:
            with get_mysql_connection() as connection:
                cursor = connection.cursor()
                query = f"SELECT MAKINA FROM dbtes WHERE OTONO = '{opt_no}'"
                cursor.execute(query)
                machines = cursor.fetchall()
                machine = machines[0] if machines else {}
                return machine.get("MAKINA", 0)
        except Exception as e:
            frappe.log_error(
                f"Error getting machine number for opt {opt_no}: {str(e)}",
                "OPT Machine Number Error",
            )
            return 0

    def _get_machine_name(self, machine_no: int) -> str:
        """
        Get the machine name corresponding to a machine number.

        Args:
            machine_no: The machine number

        Returns:
            The machine name or empty string if not found
        """
        machine_names = {2: "Murat TT", 23: "Murat NR242", 24: "Kaban CNC FA-1030"}
        return machine_names.get(machine_no, "")

    def _create_opt_genel_doc(
        self, opt_no: str, opt_code: str, machine_no: int, df: pd.DataFrame
    ) -> str:
        """
        Create or update an Opt Genel document with item data from dataframe.

        Args:
            opt_no: The opt number
            opt_code: The opt code
            machine_no: The machine number
            df: DataFrame containing the item data

        Returns:
            The name of the created/updated document

        Raises:
            Exception: If document creation/update fails
        """
        try:
            # Get existing doc or create new
            if frappe.db.exists("Opt Genel", {"opt_no": opt_no}):
                opt = frappe.get_doc("Opt Genel", {"opt_no": opt_no})
            else:
                opt = frappe.new_doc("Opt Genel")

            # Set basic fields
            opt.opt_no = opt_no
            opt.opt_code = opt_code
            opt.machine_no = self._get_machine_name(machine_no)

            # Process items
            items_data = []
            missing_items = []

            for idx, row in df.iterrows():
                try:
                    stock_code = str(row["Stok Kodu"]).strip()
                    item_code = frappe.db.exists("Item", {"item_code": stock_code})

                    if not item_code:
                        missing_items.append(stock_code)
                        frappe.log_error(
                            f"Item not found for stock code: {stock_code}",
                            "OPT Missing Item",
                        )
                        continue

                    # Calculate boy (length per piece)
                    adet = get_float_value(str(row["Adet"]))
                    profil = get_float_value(str(row["Profil"]))
                    boy = round(profil / adet, 1) if adet > 0 else 0

                    items_data.append(
                        {
                            "item_code": item_code,
                            "item_name": str(row["Açıklama"]).strip(),
                            "amountboy": adet,
                            "amountmt": get_float_value(str(row["Kullanılan"])),
                            "amountpcs": get_float_value(str(row["Parça"])),
                            "boy": boy,
                        }
                    )

                except Exception as e:
                    frappe.log_error(
                        f"Error processing row {idx} in OPT file: {str(e)}",
                        "OPT Row Processing Error",
                    )
                    continue

            # Check if we have missing items
            if missing_items:
                raise ValueError(
                    _("Items not found for stock codes: {0}").format(
                        ", ".join(missing_items)
                    )
                )

            # Set the profile list
            opt.set("profile_list", items_data)
            opt.save(ignore_permissions=True)

            frappe.db.commit()

            return opt.name

        except Exception as e:
            frappe.log_error(
                f"Error creating/updating Opt Genel doc: {str(e)}",
                "OPT Document Error",
            )
            raise

    def _create_super_kesim_doc(
        self, opt_no: str, opt_code: str, machine_no: int, df: pd.DataFrame
    ) -> str:
        """
        Create or update a Super Kesim document with item data from dataframe.

        Note: This method is available for future use but not currently called.

        Args:
            opt_no: The opt number
            opt_code: The opt code
            machine_no: The machine number
            df: DataFrame containing the item data

        Returns:
            The name of the created/updated document

        Raises:
            Exception: If document creation/update fails
        """
        try:
            # Get existing doc or create new
            if frappe.db.exists("Super Kesim", {"opt_no": opt_no}):
                opt = frappe.get_doc("Super Kesim", {"opt_no": opt_no})
            else:
                opt = frappe.new_doc("Super Kesim")

            # Set basic fields
            opt.opt_no = opt_no
            opt.opt_code = opt_code
            opt.machine_no = self._get_machine_name(machine_no)

            # Process items
            items_data = []
            missing_items = []

            for idx, row in df.iterrows():
                try:
                    stock_code = str(row["Stok Kodu"]).strip()
                    item_code = frappe.db.exists("Item", {"item_code": stock_code})

                    if not item_code:
                        missing_items.append(stock_code)
                        frappe.log_error(
                            f"Item not found for stock code: {stock_code}",
                            "Super Kesim Missing Item",
                        )
                        continue

                    items_data.append(
                        {
                            "item_code": item_code,
                            "item_name": str(row["Açıklama"]).strip(),
                            "amountboy": get_float_value(str(row["Adet"])),
                            "amountmt": get_float_value(str(row["Kullanılan"])),
                            "amountpcs": get_float_value(str(row["Parça"])),
                        }
                    )

                except Exception as e:
                    frappe.log_error(
                        f"Error processing row {idx} in Super Kesim file: {str(e)}",
                        "Super Kesim Row Processing Error",
                    )
                    continue

            # Check if we have missing items
            if missing_items:
                raise ValueError(
                    _("Items not found for stock codes: {0}").format(
                        ", ".join(missing_items)
                    )
                )

            # Set the profile list
            opt.set("profile_list", items_data)
            opt.save(ignore_permissions=True)

            frappe.db.commit()

            return opt.name

        except Exception as e:
            frappe.log_error(
                f"Error creating/updating Super Kesim doc: {str(e)}",
                "Super Kesim Document Error",
            )
            raise
