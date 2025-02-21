from typing import Any, Dict, List

import frappe
import numpy as np
from frappe import _

from ozerpan_ercom_sync.custom_api.file_processor.constants import ExcelFileType

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
        if not file_info.order_no:
            raise ValueError(_("Order number is required"))

    def process(self, file_info: ExcelFileInfo, file_data: bytes) -> Dict[str, Any]:
        try:
            sheets = self.read_excel_file(file_data)

            total_processed = 0
            total_created = 0
            processed_sheets = []

            for sheet in sheets:
                # TODO: Generate ASC files with the format below:
                # {Serial\Type}         {incremented_serial}{cari_unvan}/{order_no_-4} {poz_no}                            0Y       {adet}            {width}      {height}      {gap}                                                                       5
                result = self._process_glass_list_data(sheet, file_info)
                processed_sheets.append({"sheet_name": sheet.name, **result})
                total_processed += result.get("processed_records")
                total_created += result.get("created_records", 0)

            return {
                "status": "success",
                "message": _("Glass list file processed successfully"),
                "order_no": file_info.order_no,
                "sheet_count": len(sheets),
                "total_processed": total_processed,
                "total_created": total_created,
                "sheets": processed_sheets,
            }

        except Exception as e:
            frappe.log_error(
                f"Error processing CAMLISTE file: {str(e)}",
                "Glass List Processing Error",
            )
            raise

    def get_supported_file_type(self) -> ExcelFileType:
        return ExcelFileType.CAM

    def _process_glass_list_data(
        self, sheet: SheetData, file_info: ExcelFileInfo
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
                    self._process_record(items, record)
                    created_count += 1

            cam_liste_doc.set("items", items)
            cam_liste_doc.save()

            return {
                "processed_records": len(items),
                "created_records": created_count,
                # "records": processed_records,
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

    def _process_record(self, items: List[Dict], record: Dict):
        try:
            item_data = {
                "stok_kodu": self._clean_stock_code(record["STOKKODU"]),
                "aciklama": record.get("ACIKLAMA"),
                "adet": record.get("ADET", 0),
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
            items.append(item_data)

        except Exception as e:
            frappe.log_error(
                f"Error processing record: {str(e)}",
                "Glass Record Processing Error",
            )
            return None
