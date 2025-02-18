from typing import Any, Dict, Optional

import frappe
import numpy as np
from frappe import _

from ozerpan_ercom_sync.custom_api.file_processor.constants import ExcelFileType

from ..base import ExcelProcessorInterface
from ..models.excel_file_info import ExcelFileInfo, SheetData


class MLYListProcessor(ExcelProcessorInterface):
    def validate(self, file_info: ExcelFileInfo) -> None:
        pass

    def process(self, file_info: ExcelFileInfo, file_data: bytes) -> Dict[str, Any]:
        try:
            sheets = self.read_excel_file(file_data)

            processed_sheets = []
            for sheet in sheets:
                processed_data = self._process_mly_list_data(sheet, file_info)
                processed_sheets.append(
                    {"sheet_name": sheet.name, "data": processed_data}
                )

            return {
                "status": "success",
                "message": _("MLY list file processed successfully"),
                "order_no": file_info.order_no,
                "sheet_count": len(sheets),
                "sheets": processed_sheets,
            }

        except Exception as e:
            frappe.log_error(
                f"Error processing MLY3 file: {str(e)}",
                "MLY List Processing Error",
            )
            raise

    def get_supported_file_type(self) -> ExcelFileType:
        return ExcelFileType.MLY

    def _process_mly_list_data(
        self, sheet: SheetData, file_info: ExcelFileInfo
    ) -> Dict[str, Any]:
        try:
            df = sheet.data.replace({np.nan: None})
            df = df.dropna(how="all")
            df = df.dropna(axis=1, how="all")

            records = df.to_dict("records")

            processed_records = []
            for record in records:
                if self._is_valid_record(record):
                    processed_record = self._process_mly_record(record, file_info)
                    if processed_record:
                        processed_records.append(processed_record)

            return {
                "processed_records": len(processed_records),
                "records": processed_records,
            }
        except Exception as e:
            frappe.log_error(
                f"Error processing sheet {sheet.name}: {str(e)}",
                "MLY List Sheet Processing Error",
            )
            raise

    def _is_valid_record(self, record: Dict) -> bool:
        return any(record.values())

    def _process_mly_record(
        self, record: Dict, file_info: ExcelFileInfo
    ) -> Optional[Dict]:
        try:
            # Implement the logic to process each mly record
            # This should be customized based on your specific requirements
            # Example implementation:
            processed_record = {
                "order_no": file_info.order_no,
                "original_data": record,
                # Add more fields based on your requirements
            }

            # You might want to create or update Frappe documents here
            # Example:
            # self._create_or_update_mly_entry(processed_record)

            return processed_record
        except Exception as e:
            frappe.log_error(
                f"Error processing record: {str(e)}", "MLY Record Processing Error"
            )
            return None

    def _create_mly_entry(self, processed_record: Dict) -> None:
        try:
            pass
        except Exception as e:
            frappe.log_error(
                f"Error creating/updating mly entry: {str(e)}", "MLY Entry Error"
            )
            raise
