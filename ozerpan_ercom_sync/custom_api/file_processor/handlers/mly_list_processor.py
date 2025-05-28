from typing import Any, Dict, List

import frappe
import numpy as np
import pandas as pd
from frappe import _

from ozerpan_ercom_sync.custom_api.file_processor.constants import ExcelFileType
from ozerpan_ercom_sync.custom_api.file_processor.handlers import mly_helper
from ozerpan_ercom_sync.custom_api.tes_detay import sync_tes_detay
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
            frappe.throw(
                title="Sipariş Bulunamadı",
                msg="MLY dosyasına ait sipariş bulunamadı. ERCOM'u senkronize ediniz",
            )

    def process(self, file_info: ExcelFileInfo, file_data: bytes) -> Dict[str, Any]:
        print("\n\n\n -- Process Start --")
        try:
            sheets = self.read_excel_file(file_data)

            # Get poz data from ERCOM database
            poz_data = self._get_poz_data(file_info.order_no)
            sync_tes_detay(order_no=file_info.order_no)

            # Get and update sales order
            sales_order = self._get_sales_order(file_info.order_no)
            self._update_sales_order_taxes(sales_order)

            processed_sheets = []
            missing_items = []
            has_glasses = False
            for idx, sheet in enumerate(sheets):
                try:
                    result = self._process_sheet(sheet, poz_data[idx], file_info)

                    if result.get("status") == "error":
                        missing_items.extend(result.get("missing_items", []))
                    else:
                        # Check if this sheet has glass items
                        if result.get("has_glass_items"):
                            has_glasses = True

                        processed_sheets.append(
                            {"sheet_name": sheet.name, "data": result}
                        )

                except IndexError:
                    print("-- Index Error --")
                    frappe.log_error(
                        f"Skipping empty sheet {sheet.name} - no matching poz_data index",
                        "MLY Processing Warning",
                    )
                    continue

            if missing_items:
                # Instead of throwing error, return missing items data
                return {
                    "status": "error",
                    "message": _("Missing items are detected"),
                    "missing_items": missing_items,
                    "processed_sheets": processed_sheets,
                    "total_items_created": len(processed_sheets),
                }

            # Update sales order items
            self._update_sales_order_items(sales_order, processed_sheets)
            sales_order.custom_mly_list_uploaded = True
            sales_order.custom_has_glass_item = has_glasses
            sales_order.save(ignore_permissions=True)

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
                SERI, ACIKLAMA, NOTLAR, PozID, KASAMTUL, KAYITMTUL, KANATMTUL, CAMNET
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
        try:
            print(f"\n\n-- Processing sheet {sheet.name} -- (START)")
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

            # Create grouped dataframes from groups
            grouped_dfs = {
                group: pd.DataFrame(items) if items else pd.DataFrame()
                for group, items in groups.items()
            }

            # Check if this is a glass-only file before creating the main item
            main_profiles = None
            for key, df in grouped_dfs.items():
                if "Ana Profiller" in key:
                    main_profiles = df
                    break

            # Process glass items separately
            glasses = grouped_dfs.get("Camlar", pd.DataFrame())

            # The file is considered glass-only if it has Camlar group but no Ana Profiller group
            is_glass_only = "Camlar" in grouped_dfs and main_profiles is None

            # Log if this is a glass-only file
            if is_glass_only and not glasses.empty:
                print(f"Processing glass-only MLY file for sheet {sheet.name}")
                # For glass-only files, we don't create a main item
                # However, if we later find out all items in the Camlar group are actually profiles,
                # we'll need to re-evaluate this
                item = None
            else:
                # For regular files, create the main item
                print(1)
                item = self._create_item(item_code, total_price, poz_data)
                print(2)

            # Check for profile items mistakenly included in the glass group
            # and filter out real glass items from profile items
            profile_items_in_glass = []
            real_glass_items = []
            missing_glass_items = []

            print(f"Processing {len(glasses)} items in Camlar group")

            for _, row in glasses.iterrows():
                stock_code = row["Stok Kodu"].lstrip("#")
                is_cam_recipe = frappe.db.exists("Cam Recipe", stock_code)
                is_profile_type = frappe.db.exists("Profile Type", stock_code)

                if is_cam_recipe:
                    # This is a real glass item
                    real_glass_items.append(row)
                elif is_profile_type:
                    # This is a profile item mistakenly included in glass group
                    print(
                        f"Found profile item {stock_code} in Camlar group - will be skipped"
                    )
                    profile_items_in_glass.append(row)
                else:
                    # This is a missing glass item
                    missing_glass_items.append(
                        {
                            "stock_code": stock_code,
                            "type": "Cam Recipe",
                            "order_no": item_code.split("-")[0],
                            "poz_no": item_code.split("-")[1],
                        }
                    )

            print(
                f"Found {len(real_glass_items)} real glass items and {len(profile_items_in_glass)} profile items in Camlar group"
            )

            if missing_glass_items:
                return {
                    "status": "error",
                    "message": "Missing glass items detected",
                    "missing_items": missing_glass_items,
                    "sheet_name": sheet.name,
                }

            # Process actual glass items into separate sales order items
            glass_items = []
            for row in real_glass_items:
                stock_code = row["Stok Kodu"].lstrip("#")
                # If this is a glass-only file, use the item_code directly instead of item.name
                base_name = item.name if item else item_code
                glass_item = self._handle_glass_item(
                    row=row,
                    item_name=base_name,
                    stock_code=stock_code,
                    for_qty=poz_data.get("ADET"),
                )
                glass_items.append(glass_item)

            # Check if we should actually treat this as a glass-only file
            # If no real glass items were found (only profiles in glass group), it's not a glass-only file
            if is_glass_only and len(real_glass_items) == 0:
                print(
                    f"Reclassifying sheet {sheet.name}: not a glass-only file (no real glass items found)"
                )
                is_glass_only = False
                # Create the main item since we now know it's not a glass-only file
                item = self._create_item(item_code, total_price, poz_data)

            # Only create BOM if this is not a glass-only file
            bom_result = None
            if not is_glass_only:
                # Create BOM from remaining items (excluding glass items)
                # Filter out glass items from all_items_df and include any profile items found in the glass group
                non_glass_dfs = []
                for group_name, df in grouped_dfs.items():
                    if group_name != "Camlar" and len(df) > 0:
                        non_glass_dfs.append(df)

                # If we have profile items that were in the glass group, add them to all_items_df
                if profile_items_in_glass:
                    print(
                        f"Adding {len(profile_items_in_glass)} profile items from glass group to BOM items"
                    )
                    profile_df = pd.DataFrame(profile_items_in_glass)
                    non_glass_dfs.append(profile_df)

                all_items_df = (
                    pd.concat(non_glass_dfs) if non_glass_dfs else pd.DataFrame()
                )
                # Create BOM for main item
                bom_result = self._create_bom(
                    item.name,
                    poz_data.get("ADET"),
                    main_profiles,
                    all_items_df,
                )

                if bom_result.get("status") == "error":
                    return {
                        "status": "error",
                        "message": "Missing items detected",
                        "missing_items": bom_result.get("missing_items"),
                        "sheet_name": sheet.name,
                    }
            else:
                print(
                    f"Skipping main BOM creation for glass-only file in sheet {sheet.name}"
                )

            print(f"\n\n-- Processing sheet {sheet.name} -- (END)")

            # Prepare result
            result = {
                "glass_items": glass_items,
                "has_glass_items": len(glass_items) > 0,
                "is_glass_only": is_glass_only,
            }

            # Only include main item for non-glass-only files
            if not is_glass_only:
                main_item_result = {
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "description": item.description,
                    "qty": item.custom_quantity,
                    "uom": item.stock_uom,
                    "rate": bom_result.get("total_cost") if bom_result else 0,
                    "bom_no": bom_result.get("docname") if bom_result else None,
                    "groups": {
                        group: {
                            "items_count": len(items),
                            "items": items["Stok Kodu"].tolist()
                            if len(items) > 0
                            else [],
                        }
                        for group, items in grouped_dfs.items()
                    },
                }
                result["main_item"] = main_item_result

            return result

        except Exception as e:
            print("-- Error from _process_sheet:", e)
            frappe.log_error(
                f"Error processing sheet {sheet.name}: {str(e)}",
                "MLY Sheet Processing Error",
            )
            raise

    def _create_item(self, item_code: str, total_price: float, poz_data: Dict) -> Any:
        """Create or update Item document"""
        print(f"\n-- Creating Item {item_code} -- (START)")
        if frappe.db.exists("Item", {"item_code": item_code}):
            item = frappe.get_doc("Item", {"item_code": item_code})
        else:
            item = frappe.new_doc("Item")

        print("Item:", item)
        print("Default BOM:", item.default_bom)

        # Print all fields of the item
        # for field in item.meta.fields:
        #     print(f"Field: {field.fieldname} = {item.get(field.fieldname)}")
        print(1)
        qty = poz_data.get("ADET")
        total_main_profiles_mtul = (
            poz_data.get("KASAMTUL")
            + poz_data.get("KAYITMTUL")
            + poz_data.get("KANATMTUL")
        ) / qty
        print(2)
        item.update(
            {
                "item_code": item_code,
                "item_name": item_code,
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "valuation_rate": total_price,
                "has_serial_no": 1,
                "serial_no_series": f"{item_code}-.#",
                "custom_quantity": qty,
                "description": poz_data.get("ACIKLAMA"),
                "custom_serial": poz_data.get("SERI"),
                "custom_width": poz_data.get("GENISLIK"),
                "custom_height": poz_data.get("YUKSEKLIK"),
                "custom_color": poz_data.get("RENK"),
                "custom_remarks": poz_data.get("NOTLAR"),
                "custom_poz_id": poz_data.get("PozID"),
                "custom_total_main_profiles_mtul": total_main_profiles_mtul,
                "custom_total_glass_m2": poz_data.get("CAMNET") / qty,
                "default_bom": None,
            }
        )

        print(3)
        item.save(ignore_permissions=True)
        print(f"-- Creating Item {item_code} -- (END)\n")
        return item

    def _create_bom(
        self,
        item_name: str,
        qty: float,
        main_profiles: Any,
        df: Any,
    ) -> Dict[str, Any]:
        """Create Bill of Materials document"""
        print(f"\n-- Creating BOM {item_name} -- (START)")

        missing_items = []

        # Only check main profiles if they exist
        if not main_profiles.empty:
            for _, row in main_profiles.iterrows():
                stock_code = row["Stok Kodu"].lstrip("#")
                if not frappe.db.exists("Profile Type", stock_code):
                    missing_items.append(
                        {
                            "stock_code": stock_code,
                            "type": "Profile Type",
                            "order_no": item_name.split("-")[0],
                            "poz_no": item_name.split("-")[1],
                        }
                    )

        for _, row in df.iterrows():
            stock_code = row["Stok Kodu"].lstrip("#")

            if not frappe.db.exists("Item", stock_code):
                print(f"\n\nMISSING ITEM: {stock_code}\n\n")
                missing_items.append(
                    {
                        "stock_code": stock_code,
                        "type": "Item",
                        "order_no": item_name.split("-")[0],
                        "poz_no": item_name.split("-")[1],
                    }
                )

        if missing_items:
            return {
                "status": "error",
                "message": "Missing items detected",
                "missing_items": missing_items,
            }

        company = frappe.defaults.get_user_default("Company")
        bom = frappe.new_doc("BOM")
        bom.item = item_name
        bom.company = company
        bom.quantity = qty
        bom.rm_cost_as_per = "Price List"
        bom.buying_price_list = "Standard Buying"

        # Process profile groups (only if main_profiles exists and not empty)
        profile_group = []
        if not main_profiles.empty:
            for idx, row in main_profiles.iterrows():
                stock_code = row["Stok Kodu"].lstrip("#")
                if not frappe.db.exists("Profile Type", stock_code):
                    raise ValueError(f"Profile Type not found: {stock_code}")
                pt = frappe.get_doc("Profile Type", stock_code)
                profile_group.append(pt.get("group"))

        # Process BOM items
        items_table = []
        accessory_kits_table = []
        for _, row in df.iterrows():
            stock_code = row["Stok Kodu"].lstrip("#")

            item = frappe.get_doc("Item", stock_code)
            if not item.custom_kit:
                items_table.append(self._create_bom_item(row, item))
            else:
                bom.custom_accessory_kit = item.get("item_code")
                bom.custom_accessory_kit_qty = get_float_value(row.get("Miktar"))
                accessory_kits_table.append(
                    {
                        "kit_name": item.get("item_code"),
                        "quantity": get_float_value(row.get("Miktar")),
                    }
                )

        # Get operations based on profile group (skip for empty profile_group)
        middle_operations = None
        if profile_group:
            middle_operations = mly_helper.get_middle_operations(profile_group)
            if middle_operations is None:
                frappe.throw("Middle operations not found for main profile group")
            # Add operations
            self._add_operations_to_bom(bom, middle_operations)

        bom.set("items", items_table)
        bom.set("custom_accessory_kits", accessory_kits_table)
        bom.save(ignore_permissions=True)
        bom.submit()

        print(f"-- Creating BOM {item_name} -- (END)\n")
        return {
            "status": "success",
            "message": "BOM created successfully.",
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

    def _handle_glass_item(
        self,
        row: Dict,
        item_name: str,
        stock_code: str,
        for_qty: int,
    ) -> Dict:
        """Create Glass Item"""
        print("\n\n\n-- Handle Glass Item -- (START)\n")

        if not frappe.db.exists("Cam Recipe", stock_code):
            print("Cam Recipe Not Found:", stock_code)
            raise ValueError(f"Cam Recipe not found: {stock_code}")

        glass_recipe = frappe.get_doc("Cam Recipe", stock_code)

        glass_item_name = f"{item_name}-{stock_code}"

        if frappe.db.exists("Item", {"item_code": glass_item_name}):
            glass_item = frappe.get_doc("Item", {"item_code": glass_item_name})
        else:
            glass_item = frappe.new_doc("Item")

        print(1)
        glass_item.update(
            {
                "item_code": glass_item_name,
                "item_name": glass_item_name,
                "item_group": "Camlar",
                "stock_uom": "Nos",
                "descrioption": row.get("Açıklama", ""),
                "valuation_rate": get_float_value(str(row.get("Toplam Fiyat", "0.0"))),
                "custom_quantity": for_qty,
                "has_serial_no": 1,
                "serial_no_series": f"{glass_item_name}-.#",
                "default_bom": None,
            }
        )

        glass_item.save(ignore_permissions=True)

        print(3)
        company = frappe.defaults.get_user_default("Company")
        bom = frappe.new_doc("BOM")
        bom.item = glass_item_name
        bom.company = company
        bom.quantity = for_qty
        bom.rm_cost_as_per = "Price List"
        bom.buying_price_list = "Standard Buying"

        bom_items_table = []
        for item in glass_recipe.cam_mutable_items:
            uom = item.get("uom")
            item_qty = item.get("qty", 0.0)
            glass_qty = get_float_value(row.get("miktar", 1.0))
            qty = item_qty * glass_qty
            bom_items_table.append(
                {
                    "item_code": item.get("item_code"),
                    "item_name": item.get("item_code"),
                    "uom": item.get("uom"),
                    "qty": round(qty) if uom == "adet" else qty,
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
                    "operation": "cam",
                    "workstation": "cam kalite kontrol ve etiket",
                    "time_in_mins": 10,
                }
            ],
        )

        bom.set("items", bom_items_table)
        bom.save(ignore_permissions=True)
        bom.submit()

        print("\n-- Handle Glass Item -- (END)\n\n\n")
        return {
            "item_code": glass_item.get("item_code"),
            "item_name": glass_item.get("item_name"),
            "description": glass_item.get("description"),
            "uom": "nos",
            "qty": for_qty,
            "rate": glass_item.valuation_rate,
        }

    def _add_operations_to_bom(self, bom: Any, middle_operations: List[str]) -> None:
        """Add operations to BOM"""

        fixed_starting_operations = ["Profil Temin", "Sac Kesim"]
        fixed_ending_operations = ["Çıta", "Kalite"]
        full_operations = (
            fixed_starting_operations + middle_operations + fixed_ending_operations
        )
        operation_items = []
        for operation_name in full_operations:
            o = frappe.get_doc("Operation", operation_name)
            operation_items.append(
                {
                    "operation": o.name,
                    "workstation": o.workstation,
                    "time_in_mins": 10,
                }
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
                data = sheet["data"]
                # Add main item (only for non-glass-only files)
                if data.get("main_item"):
                    items.append(data["main_item"])
                # Add glass items at the same level as main items
                if data.get("glass_items"):
                    for glass_item in data["glass_items"]:
                        items.append(glass_item)

        sales_order.set("items", items)
        # sales_order.save(ignore_permissions=True)
