from typing import Any, Dict, List, Optional

from frappe import _

from ozerpan_ercom_sync.utils import timer

from ..base import OperationHandler
from ..constants import BarcodeStatus
from ..models.barcode_info import BarcodeInfo
from ..models.quality_data import QualityData
from .kaynak_kose_handler import KaynakKoseHandler


class DefaultOperationHandler(OperationHandler):
    def get_related_barcodes(
        self, job_card: Any, current_barcode: BarcodeInfo
    ) -> List[BarcodeInfo]:
        """Get barcodes with same sanal_adet."""
        return [
            BarcodeInfo(
                barcode=b.barcode,
                model=b.model,
                sanal_adet=int(b.sanal_adet),
                tesdetay_ref=b.tesdetay_ref,
                status=BarcodeStatus(b.status),
                job_card_ref=job_card.name,
                quality_data=b.quality_data,
            )
            for b in job_card.custom_barcodes
            if int(b.sanal_adet) == current_barcode.sanal_adet
        ]

    @timer
    def handle_barcode(
        self,
        barcode: str,
        job_card: Any,
        employee: str,
        quality_data: Optional[QualityData] = None,
    ) -> Dict[str, Any]:
        self.validate_operation(job_card)

        current_barcode = self._get_current_barcode(job_card, barcode)
        related_barcodes = self.get_related_barcodes(job_card, current_barcode)

        if current_barcode.status == BarcodeStatus.COMPLETED:
            uncompleted_job_cards = self._get_uncompleted_job_cards(
                current_barcode, job_card.operation
            )
            if not uncompleted_job_cards:
                return {
                    "message": _("All the related Job Cards are already completed."),
                    "status": "error",
                    "related_barcodes": [b.barcode for b in related_barcodes],
                }

            next_job_card = uncompleted_job_cards[0]
            next_barcode = self._get_current_barcode(next_job_card, barcode)
            next_related_barcodes = self.get_related_barcodes(next_job_card, next_barcode)

            if next_barcode.status == BarcodeStatus.PENDING:
                return self._handle_pending_scan(
                    next_job_card, next_barcode, next_related_barcodes, employee
                )
            else:
                return self._handle_in_progress_scan(
                    next_job_card, next_barcode, next_related_barcodes, employee
                )

        elif current_barcode.status == BarcodeStatus.IN_PROGRESS:
            other_job_cards = self._get_other_in_progress_jobs(
                current_barcode.tesdetay_ref
            )
            if other_job_cards:
                self._complete_other_job_cards(other_job_cards)

            return self._handle_in_progress_scan(
                job_card, current_barcode, related_barcodes, employee
            )

        else:  # PENDING
            other_job_cards = None
            for related_barcode in related_barcodes:
                other_job_cards = self._get_other_in_progress_jobs(
                    related_barcode.tesdetay_ref
                )
                if other_job_cards:
                    break

            if other_job_cards:
                self._complete_other_job_cards(other_job_cards)

            return self._handle_pending_scan(
                job_card, current_barcode, related_barcodes, employee
            )

    # Use same helper methods as KaynakKoseHandler
    _get_uncompleted_job_cards = KaynakKoseHandler._get_uncompleted_job_cards
    _get_other_in_progress_jobs = KaynakKoseHandler._get_other_in_progress_jobs
    _complete_other_job_cards = KaynakKoseHandler._complete_other_job_cards
    _handle_in_progress_scan = KaynakKoseHandler._handle_in_progress_scan
    _handle_pending_scan = KaynakKoseHandler._handle_pending_scan
    _get_in_progress_barcodes = KaynakKoseHandler._get_in_progress_barcodes
    _is_sanal_adet_group_complete = KaynakKoseHandler._is_sanal_adet_group_complete
    _complete_barcode_group = KaynakKoseHandler._complete_barcode_group
    _set_barcodes_in_progress = KaynakKoseHandler._set_barcodes_in_progress
    _get_current_barcode = KaynakKoseHandler._get_current_barcode
