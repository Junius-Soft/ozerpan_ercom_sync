from dataclasses import dataclass

import pandas as pd

from ..constants import ExcelFileType


@dataclass
class SheetData:
    name: str
    data: pd.DataFrame
    row_count: int
    column_count: int


@dataclass
class ExcelFileInfo:
    order_no: str
    file_type: ExcelFileType
    original_name: str
    file_url: str

    @classmethod
    def from_filename(cls, filename: str, file_url: str) -> "ExcelFileInfo":
        try:
            if "_" in filename:  # Format: S500227_CAMLISTE.XLS
                parts = filename.split("_")
                order_no = parts[0].strip()
                file_type_str = parts[1].split(".")[0].strip().upper()
            else:  # Format: S404325-MLY3.XLS
                parts = filename.split("-")
                order_no = parts[0].strip()
                file_type_str = parts[1].split(".")[0].strip().upper()

            file_type = None
            for ft in ExcelFileType:
                if ft.value == file_type_str:
                    file_type = ft
                    break

            if not file_type:
                raise ValueError(f"Unknown file type: {file_type_str}")

            return cls(
                order_no=order_no,
                file_type=file_type,
                original_name=filename,
                file_url=file_url,
            )

        except Exception as e:
            raise ValueError(f"Error parsing filename {filename}: {str(e)}")
