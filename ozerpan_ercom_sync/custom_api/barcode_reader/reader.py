from typing import Any, Dict, Optional

from frappe import _

from .constants import OperationType
from .exceptions import InvalidBarcodeError
from .models.quality_data import QualityData
from .utils.get_poz_data import get_poz_data
from .utils.job_card import format_job_card_response, get_job_card
from .utils.tesdetay import get_tesdetay


class BarcodeReader:
    def __init__(self):
        self.handlers = {}
        self._register_handlers()

    def _register_handlers(self):
        from .handlers.default_handler import DefaultOperationHandler
        from .handlers.kanat_hazirlik_handler import KanatHazirlikHandler
        from .handlers.kaynak_kose_handler import KaynakKoseHandler
        from .handlers.quality_control_handler import QualityControlHandler

        self.handlers = {
            OperationType.KAYNAK_KOSE.value: KaynakKoseHandler(),
            OperationType.KANAT_HAZIRLIK.value: KanatHazirlikHandler(),
            OperationType.KALITE.value: QualityControlHandler(),
            "default": DefaultOperationHandler(),
        }

    def read_barcode(
        self,
        barcode: str,
        employee: str,
        operation: str,
        quality_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        print("\n\n\n")
        print("--- Reader.read_barcode ---")
        tesdetay = get_tesdetay(barcode=barcode, operation=operation)
        if not tesdetay:
            raise InvalidBarcodeError("Invalid Barcode")

        job_card = get_job_card(
            operation=operation,
            production_item=f"{tesdetay.get('siparis_no')}-{tesdetay.get('poz_no')}",
            barcode=barcode,
        )

        handler = self.handlers.get(operation, self.handlers["default"])

        parsed_quality_data = QualityData(**quality_data) if quality_data else None

        result = handler.handle_barcode(
            barcode=barcode,
            job_card=job_card,
            employee=employee,
            quality_data=parsed_quality_data,
        )

        poz_data = get_poz_data(barcode)
        formatted_job_card = format_job_card_response(job_card)

        return {
            "status": "success",
            "message": _("Barcode processed successfully"),
            **result,
            "poz_data": poz_data,
            "job_card": formatted_job_card,
        }
