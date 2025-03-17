from typing import Any, Dict, List

import frappe
import numpy as np
import pandas as pd
from frappe import _

from ozerpan_ercom_sync.custom_api.file_processor.constants import ExcelFileType
from ozerpan_ercom_sync.custom_api.file_processor.handlers import mly_helper
from ozerpan_ercom_sync.custom_api.utils import get_float_value
from ozerpan_ercom_sync.db_pool import DatabaseConnectionPool

from ..base import ExcelProcessorInterface
from ..models.excel_file_info import ExcelFileInfo, SheetData

DEFAULT_TAX_ACCOUNT = {
    "name": "ERCOM HESAPLANAN KDV 20",
    "number": "391.99",
    "tax_rate": 20,
}


class MLYListProcessor(ExcelProcessorInterface):
    def validate(self, file_info: ExcelFileInfo) -> None:
        print("-- Validate --")
        if not file_info.order_no:
            raise ValueError(_("Order number is required"))

        # Validate sales order exists
        if not frappe.db.exists(
            "Sales Order",
            {
                "custom_ercom_order_no": file_info.order_no,
                "status": "Draft",
            },
        ):
            raise ValueError(
                _(
                    "No such Sales Order found. Please sync the database before uploading the file."
                )
            )

    def process(self, file_info: ExcelFileInfo, file_data: bytes) -> Dict[str, Any]:
        print("-- Process Start --")
        try:
            sheets = self.read_excel_file(file_data)

            # Get poz data from ERCOM database
            poz_data = self._get_poz_data(file_info.order_no)

            print("File Info:", file_info)

            # Get and update sales order
            sales_order = self._get_sales_order(file_info.order_no)
            self._update_sales_order_taxes(sales_order)

            processed_sheets = []
            for idx, sheet in enumerate(sheets):
                try:
                    result = self._process_sheet(sheet, poz_data[idx], file_info)
                    processed_sheets.append({"sheet_name": sheet.name, "data": result})
                except IndexError:
                    print("-- Index Error --")
                    frappe.log_error(
                        f"Skipping empty sheet {sheet.name} - no matching poz_data index",
                        "MLY Processing Warning",
                    )
                    continue

            # Update sales order items
            self._update_sales_order_items(sales_order, processed_sheets)

            print("-- Process End --")
            return {
                "status": "success",
                "message": _("MLY list file processed successfully"),
                "order_no": file_info.order_no,
                "sheet_count": len(sheets),
                "processed_sheets": len(processed_sheets),
                "sheets": processed_sheets,
            }

        except Exception as e:
            frappe.log_error(
                f"Error processing MLY file: {str(e)}",
                "MLY List Processing Error",
            )
            raise

    def get_supported_file_type(self) -> ExcelFileType:
        print("-- Get Supported File Type --")
        return ExcelFileType.MLY

    def _get_poz_data(self, order_no: str) -> List[Dict]:
        """Get order data from dbpoz table using connection pool"""
        print("-- Get Poz Data --")
        db_pool = DatabaseConnectionPool()
        try:
            query = """
                SELECT SAYAC, SIPARISNO, GENISLIK, YUKSEKLIK, ADET, RENK,
                SERI, ACIKLAMA, NOTLAR, PozID
                FROM dbpoz WHERE SIPARISNO = %(order_no)s
            """
            results = db_pool.execute_query(query, {"order_no": order_no})
            return results
        except Exception as e:
            error_msg = f"Error fetching data for order {order_no}: {str(e)}"
            frappe.log_error(error_msg)
            raise frappe.ValidationError(error_msg)

    def _process_sheet(
        self, sheet: SheetData, poz_data: Dict, file_info: ExcelFileInfo
    ) -> Dict[str, Any]:
        print("-- Process Sheet --")
        try:
            df = sheet.data.replace({np.nan: None})
            df = df.dropna(how="all")
            df = df.dropna(axis=1, how="all")

            groups = {}
            temp_group_items = []
            current_group_name = None

            # Exclude last 3 rows
            df_without_tail = df.iloc[:-3]

            for idx, row in df_without_tail.iterrows():
                stock_code = str(row["Stok Kodu"])

                # if 'Toplamı' in stock_code:
                if not stock_code.startswith("#"):
                    current_group_name = stock_code.replace(" Toplamı", "")
                    groups[current_group_name] = temp_group_items
                    temp_group_items = []
                    current_group_name = None
                elif stock_code.startswith("#"):
                    temp_group_items.append(row)

            if temp_group_items:
                groups["Ungrouped"] = temp_group_items

            tail = df.tail(3).copy()
            item_code = f"{tail['Stok Kodu'].iloc[0]}-{tail['Stok Kodu'].iloc[1]}"
            total_price = tail["Toplam Fiyat"].iloc[0]

            item = self._create_item(item_code, total_price, poz_data)

            grouped_dfs = {
                group: pd.DataFrame(items) if items else pd.DataFrame()
                for group, items in groups.items()
            }

            main_profiles = grouped_dfs.get("Ana Profiller", pd.DataFrame())

            glasses = grouped_dfs.get("Camlar", pd.DataFrame())
            glass_stock_codes = (
                [code.lstrip("#") for code in glasses["Stok Kodu"].tolist()]
                if not glasses.empty
                else []
            )

            all_items_df = pd.concat(
                [df for group_name, df in grouped_dfs.items() if len(df) > 0]
            )

            bom_result = self._create_bom(
                item.name,
                poz_data.get("ADET"),
                main_profiles,
                all_items_df,
                glass_stock_codes,
            )

            return {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "description": item.description,
                "qty": item.custom_quantity,
                "uom": item.stock_uom,
                "rate": bom_result.get("total_cost"),
                "bom_no": bom_result.get("docname"),
                "groups": {
                    group: {
                        "items_count": len(items),
                        "items": items["Stok Kodu"].tolist() if len(items) > 0 else [],
                    }
                    for group, items in grouped_dfs.items()
                },
            }

        except Exception as e:
            print("-- Error from _process_sheet:", e)
            frappe.log_error(
                f"Error processing sheet {sheet.name}: {str(e)}",
                "MLY Sheet Processing Error",
            )
            raise

    def _create_item(self, item_code: str, total_price: float, poz_data: Dict) -> Any:
        """Create or update Item document"""
        print("-- Create Item --")
        if frappe.db.exists("Item", {"item_code": item_code}):
            item = frappe.get_doc("Item", {"item_code": item_code})
        else:
            item = frappe.new_doc("Item")

        item.update(
            {
                "item_code": item_code,
                "item_name": item_code,
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "valuation_rate": total_price,
                "description": poz_data.get("ACIKLAMA"),
                "custom_serial": poz_data.get("SERI"),
                "custom_width": poz_data.get("GENISLIK"),
                "custom_height": poz_data.get("YUKSEKLIK"),
                "custom_color": poz_data.get("RENK"),
                "custom_quantity": poz_data.get("ADET"),
                "custom_remarks": poz_data.get("NOTLAR"),
                "custom_poz_id": poz_data.get("PozID"),
            }
        )

        item.save(ignore_permissions=True)
        return item

    def _create_bom(
        self, item_name: str, qty: float, main_profiles: Any, df: Any, glass_stock_codes
    ) -> Dict[str, Any]:
        """Create Bill of Materials document"""
        print("-- Create BOM --")
        company = frappe.defaults.get_user_default("Company")
        bom = frappe.new_doc("BOM")
        bom.item = item_name
        bom.company = company
        bom.quantity = qty
        bom.rm_cost_as_per = "Price List"
        bom.buying_price_list = "Standard Selling"

        # Process profile groups
        profile_group = []
        for idx, row in main_profiles.iterrows():
            stock_code = row["Stok Kodu"].lstrip("#")
            if not frappe.db.exists("Profile Type", stock_code):
                raise ValueError(f"Profile Type not found: {stock_code}")
            pt = frappe.get_doc("Profile Type", stock_code)
            profile_group.append(pt.get("group"))

        # Process BOM items
        items_table = []
        for _, row in df.iterrows():
            stock_code = row["Stok Kodu"].lstrip("#")
            if stock_code in glass_stock_codes:
                glass_item = self._handle_glass_item(row, item_name, stock_code)
                items_table.append(glass_item)
                continue

            if not frappe.db.exists("Item", stock_code):
                print("Item Not Found:", stock_code)
                raise ValueError(f"Item not found: {stock_code}")

            item = frappe.get_doc("Item", stock_code)
            if not item.custom_kit:
                items_table.append(self._create_bom_item(row, item))
            else:
                bom.custom_accessory_kit = item.get("item_code")
                bom.custom_accessory_kit_qty = get_float_value(row.get("Miktar"))

        # Add operations
        self._add_operations_to_bom(bom, mly_helper.get_middle_operations(profile_group))

        bom.set("items", items_table)
        bom.save(ignore_permissions=True)
        bom.submit()

        return {
            "msg": "BOM created successfully.",
            "docname": bom.name,
            "total_cost": bom.total_cost,
        }

    def _create_bom_item(self, row: Dict, item: Any) -> Dict:
        """Create BOM item entry"""
        rate = get_float_value(str(row.get("Birim Fiyat", "0.0")))
        amount = get_float_value(str(row.get("Toplam Fiyat", "0.0")))
        item_qty = (
            round((amount / rate), 7)
            if rate != 0.0
            else get_float_value(row.get("Miktar"))
        )

        return {
            "item_code": item.get("item_code"),
            "item_name": item.get("item_name"),
            "description": item.get("description"),
            "uom": str(row.get("Birim")),
            "qty": item_qty,
            "rate": rate,
        }

    def _handle_glass_item(self, row: Dict, item_name: str, stock_code: str) -> Dict:
        """Create Glass Item"""
        print("\n")
        print("-- Create Glass Item --")

        if not frappe.db.exists("Cam Recipe", stock_code):
            print("Cam Recipe Not Found:", stock_code)
            raise ValueError(f"Cam Recipe not found: {stock_code}")

        glass_recipe = frappe.get_doc("Cam Recipe", stock_code)

        glass_item_name = f"{item_name}-{stock_code}"

        if frappe.db.exists("Item", {"item_code": glass_item_name}):
            glass_item = frappe.get_doc("Item", {"item_code": glass_item_name})
        else:
            glass_item = frappe.new_doc("Item")

        glass_item.update(
            {
                "item_code": glass_item_name,
                "item_name": glass_item_name,
                "item_group": "Camlar",
                "stock_uom": "Nos",
                "descrioption": row.get("Açıklama", ""),
                "valuation_rate": get_float_value(str(row.get("Toplam Fiyat", "0.0"))),
            }
        )

        glass_item.save()

        company = frappe.defaults.get_user_default("Company")
        bom = frappe.new_doc("BOM")
        bom.item = glass_item_name
        bom.company = company
        bom.quantity = 1
        bom.rm_cost_as_per = "Price List"
        bom.buying_price_list = "Standard Selling"

        bom_items_table = []
        for item in glass_recipe.cam_mutable_items:
            uom = item.get("uom")
            item_qty = item.get("qty", 0.0)
            glass_qty = get_float_value(row.get("Miktar", 1.0))
            qty = item_qty * glass_qty
            bom_items_table.append(
                {
                    "item_code": item.get("item_code"),
                    "item_name": item.get("item_code"),
                    "uom": item.get("uom"),
                    "qty": round(qty) if uom == "Adet" else qty,
                }
            )

        for item in glass_recipe.cam_fixed_items:
            bom_items_table.append(
                {
                    "item_code": item.get("item_code"),
                    "item_name": item.get("item_code"),
                    "uom": item.get("uom"),
                    "qty": item.get("qty"),
                }
            )

        bom.with_operations = 1
        bom.set(
            "operations",
            [
                {
                    "operation": "Cam",
                    "workstation": "Cam Kalite Kontrol ve Etiket",
                    "time_in_mins": 10,
                }
            ],
        )

        bom.set("items", bom_items_table)
        bom.save()
        bom.submit()

        return {
            "item_code": glass_item.get("item_code"),
            "item_name": glass_item.get("item_name"),
            "description": glass_item.get("description"),
            "uom": "Nos",
            "qty": 1,
            "rate": glass_item.valuation_rate,
        }

        print("\n")

    def _add_operations_to_bom(self, bom: Any, middle_operations: List[str]) -> None:
        """Add operations to BOM"""
        fixed_starting_operations = ["Profil Temin", "Sac Kesim"]
        fixed_ending_operations = ["Çıta", "Kalite", "Sevkiyat"]
        full_operations = (
            fixed_starting_operations + middle_operations + fixed_ending_operations
        )

        operation_items = []
        for operation_name in full_operations:
            o = frappe.get_doc("Operation", operation_name)
            operation_items.append(
                {"operation": o.name, "workstation": o.workstation, "time_in_mins": 10}
            )

        bom.with_operations = 1
        bom.set("operations", operation_items)

    def _get_sales_order(self, order_no: str) -> Any:
        """Get sales order document"""
        sales_order = frappe.get_last_doc(
            "Sales Order",
            {
                "custom_ercom_order_no": order_no,
                "status": "Draft",
            },
        )

        return sales_order

    def _update_sales_order_taxes(self, sales_order: Any) -> None:
        """Update sales order tax information"""
        tax_account = self._get_tax_account()

        existing_tax = next(
            (
                tax
                for tax in sales_order.taxes
                if tax.account_head == tax_account.get("name")
            ),
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

    def _get_tax_account(self) -> Any:
        """Get or create tax account"""
        account_filters = {
            "account_name": DEFAULT_TAX_ACCOUNT["name"],
            "account_number": DEFAULT_TAX_ACCOUNT["number"],
        }

        if not frappe.db.exists("Account", account_filters):
            company = frappe.get_doc(
                "Company", frappe.defaults.get_user_default("company")
            )
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

    def _update_sales_order_items(
        self, sales_order: Any, processed_sheets: List[Dict]
    ) -> None:
        """Update sales order with processed items"""
        items = []
        for sheet in processed_sheets:
            if sheet.get("data"):
                items.append(sheet["data"])

        sales_order.set("items", items)
        sales_order.save(ignore_permissions=True)
