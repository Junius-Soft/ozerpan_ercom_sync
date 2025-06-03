"""
Price List Processor for Excel Files.

This module contains the PriceListProcessor class responsible for processing
price list Excel files and updating Sales Orders accordingly.
"""

import frappe
from frappe import _
from typing import Dict, List, Any, Optional, Union

from ..base import ExcelProcessorInterface
from ..constants import ExcelFileType
from ..models.excel_file_info import ExcelFileInfo, SheetData
from ..utils.price_list_utils import (
    validate_sales_order,
    get_sales_order,
    preprocess_excel_data,
    extract_price_details,
    calculate_glass_item_price,
    calculate_pvc_item_price,
    calculate_total_discount,
    update_sales_order,
)


class PriceListProcessor(ExcelProcessorInterface):
    """
    Processor for handling price list Excel files.
    
    This class implements the ExcelProcessorInterface to validate and process
    price list files that contain pricing information for items in a Sales Order.
    """

    def validate(self, file_info: ExcelFileInfo) -> None:
        """
        Validate that the file can be processed.
        
        Args:
            file_info: Information about the file to be processed
            
        Raises:
            ValueError: If validation fails
        """
        validate_sales_order(file_info.order_no)

    def process(self, file_info: ExcelFileInfo, file_data: bytes) -> Dict[str, Any]:
        """
        Process the price list file and update the corresponding Sales Order.
        
        Args:
            file_info: Information about the file to be processed
            file_data: Binary contents of the file
            
        Returns:
            Dictionary with processing results
        """
        try:
            # Extract and preprocess data from Excel file
            sheets: List[SheetData] = self.read_excel_file(file_data)
            if not sheets or len(sheets) == 0:
                raise ValueError(_("No data found in the Excel file"))

            sheet = sheets[0]
            df = preprocess_excel_data(sheet.data)
            records = df.to_dict("records")
            
            # Get the sales order to update
            sales_order = get_sales_order(file_info.order_no)
            
            # Extract price details and initialize tracking variables
            price_details = extract_price_details(records)
            price_list: Dict[str, float] = {}
            updated_count: int = 0
            
            # Process each item in the sales order
            for item in sales_order.items:
                item_code = item.get("item_code")
                item_doc = frappe.get_doc("Item", item_code)
                item_group = item_doc.get("item_group")
                
                if item_group == "Camlar":  # Glass items
                    item_qty = item_doc.get("custom_quantity")
                    price = calculate_glass_item_price(item_code, item_qty, records)
                    if price is not None:
                        price_list[item_code] = price
                        item.rate = price
                        updated_count += 1
                
                elif item_group == "PVC":  # PVC items
                    bom_no = item.get("bom_no", "No Bom")
                    if bom_no == "No Bom":
                        continue
                        
                    item_price, update_result = calculate_pvc_item_price(
                        item_code, bom_no, records
                    )
                    
                    if item_price > 0:
                        price_list[item_code] = item_price
                        item.rate = item_price
                        updated_count += update_result
            
            # Calculate total discount and update sales order
            total_discount = calculate_total_discount(price_details)
            update_sales_order(sales_order, price_list, total_discount)
            
            # Prepare and return result
            if updated_count > 0:
                return {
                    "success": True,
                    "message": _("Price list processed and sales order updated successfully"),
                    "updated_items": updated_count,
                    "sales_order": sales_order.name,
                }
            else:
                frappe.log_error(
                    f"No items were updated for order {file_info.order_no}",
                    "Price List Processing Warning",
                )
                return {
                    "success": False,
                    "message": _("No items were updated in the sales order"),
                    "updated_items": 0,
                    "sales_order": sales_order.name,
                }

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            frappe.log_error(
                f"Error processing FIYAT file: {str(e)}\n{error_trace}",
                "FIYAT List Processing Error",
            )
            frappe.db.rollback()
            return {
                "success": False,
                "message": _("Error processing price list: {0}").format(str(e)),
                "error": str(e),
            }

    def get_supported_file_type(self) -> ExcelFileType:
        """
        Get the file type supported by this processor.
        
        Returns:
            The supported Excel file type
        """
        return ExcelFileType.PRICE