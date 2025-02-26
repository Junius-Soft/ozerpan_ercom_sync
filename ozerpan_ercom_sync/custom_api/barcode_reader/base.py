from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from .models.barcode_info import BarcodeInfo
from .models.quality_data import QualityData


class OperationHandler(ABC):
    @abstractmethod
    def handle_barcode(
        self,
        barcode: str,
        job_card: Any,
        employee: str,
        quality_data: Optional[QualityData] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_related_barcodes(
        self, job_card: Any, current_barcode: BarcodeInfo
    ) -> List[BarcodeInfo]:
        pass

    def validate_operation(self, job_card: Any) -> None:
        if job_card.docstatus == 2:
            frappe.throw(_("Cannot process cancelled job card"))
