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
            if "_" in filename:  # Format: S500227_CAMLISTE.XLS or S500389_MLY3dfe7ea.XLS
                parts = filename.split("_")
                order_no = parts[0].strip()
                # Extract the beginning part of the file type string before any random additions
                file_type_str = "".join(
                    c
                    for c in parts[1].split(".")[0].strip().upper()
                    if c.isalpha() or c.isdigit()
                )

                # Match against known types
                for ft in ExcelFileType:
                    if file_type_str.startswith(ft.value):
                        file_type = ft
                        break
                else:  # no break occurred
                    raise ValueError(f"Unknown file type: {file_type_str}")

            else:  # Format: S404325-MLY3.XLS
                parts = filename.split("-")
                order_no = parts[0].strip()
                file_type_str = parts[1].split(".")[0].strip().upper()

                # Match against known types
                for ft in ExcelFileType:
                    if file_type_str.startswith(ft.value):
                        file_type = ft
                        break
                else:  # no break occurred
                    raise ValueError(f"Unknown file type: {file_type_str}")

            return cls(
                order_no=order_no,
                file_type=file_type,
                original_name=filename,
                file_url=file_url,
            )

        except Exception as e:
            raise ValueError(f"Error parsing filename {filename}: {str(e)}")
