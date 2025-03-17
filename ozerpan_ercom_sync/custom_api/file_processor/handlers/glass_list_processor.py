import datetime
import os
from typing import Any, Dict, List

import frappe
import numpy as np
from frappe import _

from ozerpan_ercom_sync.custom_api.file_processor.constants import ExcelFileType
from ozerpan_ercom_sync.custom_api.file_processor.handlers.mly_list_processor import (
    MLYListProcessor,
)

from ..base import ExcelProcessorInterface
from ..models.excel_file_info import ExcelFileInfo, SheetData


class GlassListProcessor(ExcelProcessorInterface):
    REQUIRED_FIELDS = [
        "STOKKODU",
        "ACIKLAMA",
        "ADET",
        "GEN",
        "YUK",
        "BM2",
        "TM2",
        "POZNO",
        "SIPARISNO",
    ]

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
        try:
            sheets = self.read_excel_file(file_data)
            sales_order = self._get_sales_order(file_info.order_no)
            if sales_order.items[0].item_code == "Place Holder Item":
                raise ValueError(_("Please upload MLY file first."))

            total_processed = 0
            total_created = 0
            processed_sheets = []
            all_asc_file_paths = {}
            poz_quantity: Dict = {}

            for item in sales_order.items:
                code_parts = item.item_code.split("-")
                poz_no = code_parts[1]
                poz_quantity[poz_no] = int(item.qty)

            for sheet in sheets:
                result = self._process_glass_list_data(sheet, file_info, poz_quantity)
                asc_file_paths = self._generate_asc_files(sheet, file_info)

                # Add the ASC file paths to the sheet result for tracking
                sheet_result = {
                    "sheet_name": sheet.name,
                    **result,
                }

                processed_sheets.append(sheet_result)
                total_processed += result.get("processed_records")
                total_created += result.get("created_records", 0)

                # Merge ASC file paths dictionaries
                all_asc_file_paths.update(asc_file_paths)

            # Check if any ASC files were generated
            if not all_asc_file_paths:
                frappe.log_error(
                    f"No ASC files were generated for any sheet in order {file_info.order_no}",
                    "ASC File Generation Warning",
                )

            return {
                "status": "success",
                "message": _("Glass list file processed successfully"),
                "order_no": file_info.order_no,
                "sheet_count": len(sheets),
                "total_processed": total_processed,
                "total_created": total_created,
                "sheets": processed_sheets,
                "asc_file_paths": all_asc_file_paths,
                "asc_file_count": len(all_asc_file_paths),
            }

        except Exception as e:
            frappe.log_error(
                f"Error processing CAMLISTE file: {str(e)}",
                "Glass List Processing Error",
            )
            raise

    def get_supported_file_type(self) -> ExcelFileType:
        return ExcelFileType.CAM

    def _generate_asc_files(
        self, sheet: SheetData, file_info: ExcelFileInfo
    ) -> Dict[str, str]:
        try:
            # Clean and prepare data
            df = (
                sheet.data.replace({np.nan: None})
                .dropna(how="all")
                .dropna(axis=1, how="all")
            )
            records = df.to_dict("records")

            # Group records by stock code and calculate totals
            total_item_count = 0
            grouped_records = {}
            for record in records:
                # Validate required fields for ASC file
                if not self._validate_asc_record(record):
                    continue

                stock_code = self._clean_stock_code(record.get("STOKKODU"))
                if not stock_code:
                    frappe.log_error(
                        "Empty stock code found in record", "ASC File Generation Warning"
                    )
                    continue

                # Convert ADET to int and handle invalid values
                try:
                    adet = int(record.get("ADET", 0))
                    record["ADET"] = adet
                    total_item_count += adet
                except (ValueError, TypeError):
                    record["ADET"] = 0

                grouped_records.setdefault(stock_code, []).append(
                    {**record, "STOKKODU": stock_code}
                )

            generated_files = {}
            for stock_code, group_records in grouped_records.items():
                try:
                    # Skip empty groups
                    if not group_records:
                        continue

                    # Check if records have valid ADET values
                    if any(record.get("ADET", 0) <= 0 for record in group_records):
                        frappe.log_error(
                            f"Some records have zero or negative ADET for stock code {stock_code}",
                            "ASC File Generation Warning",
                        )

                    # Get order number
                    order_no = group_records[0].get("SIPARISNO")
                    if not order_no:
                        frappe.log_error(
                            f"Missing SIPARISNO for stock code {stock_code}",
                            "ASC File Generation Warning",
                        )
                        continue

                    # Create directory and file path
                    site_path = frappe.utils.get_site_path()
                    asc_dir = os.path.join(site_path, "public", "files", "asc")
                    os.makedirs(asc_dir, exist_ok=True)

                    asc_file_path = os.path.join(
                        asc_dir,
                        f"OP_{order_no}_{stock_code}.asc",
                    )

                    # Validate glass doc exists
                    if not frappe.db.exists("Cam", stock_code):
                        frappe.log_error(
                            f"Cam document not found for stock code {stock_code}",
                            "ASC File Generation Error",
                        )
                        continue

                    glass_doc = frappe.get_doc("Cam", stock_code)

                    # Write ASC file
                    with open(asc_file_path, "w") as asc_file:
                        frappe.log_error(
                            f"Writing ASC file for stock code {stock_code}, order {order_no}",
                            "ASC File Generation Info",
                        )

                        first_record = group_records[0]
                        current_date = datetime.datetime.now().strftime("%d%m%Y")

                        # Write header with safe text conversion
                        cari_unvan = self._safe_get_text(first_record, "CARIUNVAN")
                        musteri = self._safe_get_text(first_record, "MUSTERI")

                        header = "{:<31}{:>9}{:>18}\n{:>8}\n".format(
                            f"{self._turkishToEnglish(cari_unvan)}/{self._turkishToEnglish(musteri)}",
                            current_date,
                            f"{total_item_count}V4",
                            len(group_records),
                        )
                        asc_file.write(header)

                        # Sort and write records
                        group_records.sort(
                            key=lambda x: (x.get("YUK", 0), x.get("GEN", 0)), reverse=True
                        )

                        for idx, record in enumerate(group_records, 1):
                            try:
                                line = self._format_asc_line(
                                    idx=idx, record=record, glass_doc=glass_doc
                                )
                                asc_file.write(line)
                            except Exception as line_error:
                                frappe.log_error(
                                    f"Error writing line for record {idx}, stock code {stock_code}: {str(line_error)}",
                                    "ASC File Line Generation Error",
                                )

                        # Flush and close file explicitly
                        asc_file.flush()

                    # Verify file was written correctly
                    if (
                        os.path.exists(asc_file_path)
                        and os.path.getsize(asc_file_path) > 0
                    ):
                        generated_files[stock_code] = asc_file_path
                    else:
                        frappe.log_error(
                            f"ASC file for {stock_code} was created but is empty or missing",
                            "ASC File Generation Error",
                        )

                except Exception as e:
                    frappe.log_error(
                        f"Error processing stock code {stock_code}: {str(e)}",
                        "ASC File Generation Error",
                    )

            if not generated_files:
                frappe.log_error(
                    f"No ASC files were generated for sheet {sheet.name}",
                    "ASC File Generation Warning",
                )

            return generated_files

        except Exception as e:
            frappe.log_error(
                f"Error generating ASC files for sheet {sheet.name}: {str(e)}",
                "Glass List Sheet Processing Error",
            )
            raise

    def _turkishToEnglish(self, text):
        """Convert Turkish characters to English equivalents"""
        if not text:
            return ""

        if not isinstance(text, str):
            try:
                text = str(text)
            except Exception:
                return ""

        char_map = {
            "ç": "c",
            "ğ": "g",
            "ı": "i",
            "ö": "o",
            "ş": "s",
            "ü": "u",
            "Ç": "C",
            "Ğ": "G",
            "İ": "I",
            "Ö": "O",
            "Ş": "S",
            "Ü": "U",
        }
        for char in char_map:
            text = text.replace(char, char_map[char])
        return text

    def _safe_get_text(self, record, field):
        """Safely get text field value with fallback to empty string"""
        value = record.get(field, "")
        if value is None:
            return ""
        return str(value)

    def _validate_asc_record(self, record: Dict) -> bool:
        """Validate record has all necessary fields for ASC file generation"""
        required_fields = [
            "STOKKODU",
            "ADET",
            "GEN",
            "YUK",
            "POZNO",
            "SIPARISNO",
            "CARIUNVAN",
            "MUSTERI",
        ]
        for field in required_fields:
            if field not in record or record[field] is None:
                return False
        return True

    def _format_asc_line(self, idx: int, record: Dict, glass_doc: Any) -> str:
        """Format a line for ASC file with safe access to fields"""
        try:
            # Safely get values with defaults
            cari_unvan = self._safe_get_text(record, "CARIUNVAN")
            siparis_no = self._safe_get_text(record, "SIPARISNO")

            # Handle potential errors in converting values
            try:
                adet = int(record.get("ADET", 0))
            except (ValueError, TypeError):
                adet = 0

            try:
                gen = int(record.get("GEN", 0))
            except (ValueError, TypeError):
                gen = 0

            try:
                yuk = int(record.get("YUK", 0))
            except (ValueError, TypeError):
                yuk = 0

            try:
                poz_no = int(record.get("POZNO", 0))
            except (ValueError, TypeError):
                poz_no = 0

            try:
                gap = int(glass_doc.gap)
            except (ValueError, TypeError, AttributeError):
                gap = 0

            # Format the line with validated values
            return "{:<15}{:>20}{:>30}{:>8}{:>15}{:>9}{:>8}{:>72}\n".format(
                f"0{glass_doc.serial}\\0{glass_doc.type}",
                f"{idx}{cari_unvan[:6]}/{siparis_no[-4:] if len(siparis_no) >= 4 else siparis_no} {poz_no:02d}",
                "0Y",
                adet,
                gen,
                yuk,
                gap,
                "5",
            )
        except Exception as e:
            frappe.log_error(
                f"Error formatting ASC line: {str(e)}", "ASC Line Format Error"
            )
            # Return a minimal valid line to avoid breaking the whole file
            return "ERROR_IN_LINE\n"

    def _process_glass_list_data(
        self, sheet: SheetData, file_info: ExcelFileInfo, poz_quantity: Dict
    ) -> Dict[str, Any]:
        try:
            df = sheet.data.replace({np.nan: None})
            df = df.dropna(how="all")
            df = df.dropna(axis=1, how="all")

            records = df.to_dict("records")

            if frappe.db.exists("CamListe", {"order_no": file_info.order_no}):
                cam_liste_doc = frappe.get_doc(
                    "CamListe", {"order_no": file_info.order_no}
                )
            else:
                cam_liste_doc = frappe.new_doc("CamListe")
                cam_liste_doc.order_no = file_info.order_no

            items = []
            created_count = 0

            for record in records:
                if self._is_valid_record(record):
                    self._process_record(items, record, poz_quantity)
                    created_count += 1

            cam_liste_doc.set("items", items)
            cam_liste_doc.save()

            return {
                "processed_records": len(items),
                "created_records": created_count,
            }
        except Exception as e:
            frappe.log_error(
                f"Error processing sheet {sheet.name}: {str(e)}",
                "Glass List Sheet Processing Error",
            )
            raise

    def _is_valid_record(self, record: Dict) -> bool:
        if not record:
            return False

        for field in self.REQUIRED_FIELDS:
            if field not in record or record[field] is None:
                return False

        return True

    def _clean_stock_code(self, stock_code: str) -> str:
        if not stock_code:
            return ""
        return stock_code.replace("#", "").strip()

    def _process_record(self, items: List[Dict], record: Dict, poz_quantity: Dict):
        try:
            item_data = {
                "stok_kodu": self._clean_stock_code(record["STOKKODU"]),
                "aciklama": record.get("ACIKLAMA"),
                "gen": record.get("GEN", 0),
                "yuk": record.get("YUK", 0),
                "bm2": record.get("BM2", 0),
                "tm2": record.get("TM2", 0),
                "poz_no": record.get("POZNO"),
                "cari_kod": record.get("CARIKOD"),
                "cari_unvan": record.get("CARIUNVAN"),
                "musteri": record.get("MUSTERI"),
                "kucuk_cam": record.get("KUCUK_CAM", 0),
                "menfez": record.get("MENFEZ", 0),
                "karolaj": record.get("KAROLAJ", 0),
                "status": "Pending",
            }
            qty = int(record.get("ADET"))
            poz_no = record.get("POZNO")
            poz_qty = poz_quantity[str(poz_no)]
            for i in range(poz_qty):
                for j in range(qty):
                    new_item = item_data.copy()
                    new_item["sanal_adet"] = i + 1
                    items.append(new_item)

        except Exception as e:
            frappe.log_error(
                f"Error processing record: {str(e)}",
                "Glass Record Processing Error",
            )
            return None

    _get_sales_order = MLYListProcessor._get_sales_order
