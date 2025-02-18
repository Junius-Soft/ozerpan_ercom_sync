import io
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import pandas as pd

from .constants import ExcelFileType
from .models.excel_file_info import ExcelFileInfo, SheetData


class ExcelProcessorInterface(ABC):
    @abstractmethod
    def validate(self, file_info: ExcelFileInfo) -> None:
        pass

    @abstractmethod
    def process(self, file_info: ExcelFileInfo, file_data: bytes) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_supported_file_type(self) -> ExcelFileType:
        pass

    def read_excel_file(self, file_data: bytes) -> List[SheetData]:
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_data))
            sheets = []

            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                if not df.empty:
                    sheets.append(
                        SheetData(
                            name=sheet_name,
                            data=df,
                            row_count=len(df),
                            column_count=len(df.columns),
                        )
                    )

            return sheets

        except Exception as e:
            raise ValueError(f"Error reading excel file: {str(e)}")
