from typing import Any, Dict, Optional, TypedDict

import frappe

from .barcode_reader.exceptions import (
    BarcodeError,
    InvalidBarcodeError,
    QualityControlError,
)
from .barcode_reader.reader import BarcodeReader


class BarcodeRequest(TypedDict):
    barcode: str
    employee: str
    operation: str
    quality_data: Optional[Dict[str, Any]]


@frappe.whitelist()
def read_barcode(
    barcode: str, employee: str, operation: str, quality_data: Optional[Dict] = None
) -> Dict[str, Any]:
    try:
        print("\n\n\n")
        print("--- Read Barcode ---")
        reader = BarcodeReader()
        result = reader.read_barcode(
            barcode=barcode,
            employee=employee,
            operation=operation,
            quality_data=quality_data,
        )
        print("\n\n\n")
        return result
    except QualityControlError as e:
        return {
            "status": "error",
            "message": str(e.message),
            "error_type": e.error_type,
            **(e.data or {}),
        }
    except InvalidBarcodeError as e:
        return {"status": "error", "message": str(e), "error_type": "invalid_barcode"}
    except BarcodeError as e:
        return {"status": "error", "message": str(e), "error_type": "barcode_operation"}
    except Exception as e:
        frappe.log_error(f"Error reading barcode: {str(e)}", "Barcode Reader Error")
        return {
            "status": "error",
            "message": str(e),
            "error_type": "system",
        }
