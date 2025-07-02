from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from ozerpan_ercom_sync.utils import (
    bulk_update_operation_status,
)

from ..base import OperationHandler
from ..constants import BarcodeStatus
from ..models.barcode_info import BarcodeInfo
from ..models.quality_data import QualityData
from ..utils.job_card import (
    complete_job,
    is_job_fully_complete,
    save_with_retry,
    submit_job_card,
    update_job_card_status,
)


class KanatHazirlikHandler(OperationHandler):
    def get_related_barcodes(
        self, job_card: Any, current_barcode: BarcodeInfo
    ) -> List[BarcodeInfo]:
        """
        For Kanat Hazirlik operation:
        - Only KANAT barcodes can be scanned
        - Group KANAT barcodes by araba_no, yer_no, and sanal_adet
        - Include related Kasa and Kayit barcodes that are not completed
        """
        result = []

        # Validate that only KANAT barcodes are accepted
        if current_barcode.model != "KANAT":
            frappe.throw(_("Only KANAT barcodes are allowed in Kanat Hazirlik operation"))

        # Get current KANAT's araba_no and yer_no
        current_tesdetay = frappe.get_doc("TesDetay", current_barcode.tesdetay_ref)
        current_araba_no = current_tesdetay.araba_no
        current_yer_no = current_tesdetay.yer_no

        for b in job_card.custom_barcodes:
            # Include KANAT barcodes with matching araba_no, yer_no, and sanal_adet
            if b.model == "KANAT" and int(b.sanal_adet) == int(
                current_barcode.sanal_adet
            ):
                tesdetay = frappe.get_doc("TesDetay", b.tesdetay_ref)
                if (
                    tesdetay.araba_no == current_araba_no
                    and tesdetay.yer_no == current_yer_no
                ):
                    result.append(
                        BarcodeInfo(
                            barcode=b.barcode,
                            model=b.model,
                            sanal_adet=int(b.sanal_adet),
                            tesdetay_ref=b.tesdetay_ref,
                            status=BarcodeStatus(b.status),
                            job_card_ref=job_card.name,
                            quality_data=b.quality_data,
                        )
                    )

            # Include Kasa and Kayit barcodes with same sanal_adet that are not completed
            elif (
                b.model in ["KASA", "KAYIT"]
                and int(b.sanal_adet) == int(current_barcode.sanal_adet)
                and b.status != BarcodeStatus.COMPLETED.value
            ):
                result.append(
                    BarcodeInfo(
                        barcode=b.barcode,
                        model=b.model,
                        sanal_adet=int(b.sanal_adet),
                        tesdetay_ref=b.tesdetay_ref,
                        status=BarcodeStatus(b.status),
                        job_card_ref=job_card.name,
                        quality_data=b.quality_data,
                    )
                )

        return result

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
            # Get job cards with same operation only when barcode is completed
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
            # Get all job cards for the barcode when it's in progress
            other_job_cards = self._get_other_in_progress_jobs(
                current_barcode.tesdetay_ref
            )
            if other_job_cards:
                self._complete_other_job_cards(other_job_cards)

            return self._handle_in_progress_scan(
                job_card, current_barcode, related_barcodes, employee
            )

        else:  # PENDING
            return self._handle_pending_scan(
                job_card, current_barcode, related_barcodes, employee
            )

    def _get_uncompleted_job_cards(
        self, barcode: BarcodeInfo, operation: str
    ) -> List[Any]:
        """Get uncompleted job cards for the barcode with the same operation."""
        tesdetay = frappe.get_doc("TesDetay", barcode.tesdetay_ref)
        uncompleted_jobs = []

        for op_state in tesdetay.operation_states:
            try:
                job_card = frappe.get_doc("Job Card", op_state.job_card_ref)
                if (
                    job_card.docstatus == 0  # Draft
                    and job_card.operation == operation  # Same operation
                    and op_state.status != BarcodeStatus.COMPLETED.value
                ):
                    uncompleted_jobs.append(job_card)
            except frappe.DoesNotExistError:
                continue

        return uncompleted_jobs

    def _get_other_in_progress_jobs(self, tesdetay_ref: str) -> List[Any]:
        """Get all in-progress job cards for the TesDetay."""
        tesdetay = frappe.get_doc("TesDetay", tesdetay_ref)
        in_progress_jobs = []

        for op_state in tesdetay.operation_states:
            if op_state.status == BarcodeStatus.IN_PROGRESS.value:
                try:
                    job_card = frappe.get_doc("Job Card", op_state.job_card_ref)
                    if job_card.docstatus == 0 and job_card.operation != "Kalite":
                        in_progress_jobs.append(job_card)
                except frappe.DoesNotExistError:
                    continue

        return in_progress_jobs

    def _complete_other_job_cards(self, job_cards: List[Any]) -> None:
        """Complete other in-progress job cards."""
        for job_card in job_cards:
            if job_card.operation == "Kalite":
                continue
            in_progress_barcodes = self._get_in_progress_barcodes(job_card)
            if in_progress_barcodes:
                self._complete_barcode_group(job_card, in_progress_barcodes)
                if self._is_sanal_adet_group_complete(job_card, in_progress_barcodes[0]):
                    complete_job(job_card, 1)
                    if is_job_fully_complete(job_card):
                        submit_job_card(job_card)
                    else:
                        update_job_card_status(job_card, "On Hold")
                else:
                    update_job_card_status(job_card, "On Hold")

    def _handle_in_progress_scan(
        self,
        job_card: Any,
        current_barcode: BarcodeInfo,
        related_barcodes: List[BarcodeInfo],
        employee: str,
    ) -> Dict[str, Any]:
        self._complete_barcode_group(job_card, related_barcodes)

        if self._is_sanal_adet_group_complete(job_card, current_barcode):
            complete_job(job_card, 1)

            if is_job_fully_complete(job_card):
                submit_job_card(job_card)
            else:
                update_job_card_status(job_card, "On Hold")
        else:
            update_job_card_status(job_card, "On Hold")

        return {
            "status": "completed",
            "completed_barcodes": [b.barcode for b in related_barcodes],
        }

    def _handle_pending_scan(
        self,
        job_card: Any,
        current_barcode: BarcodeInfo,
        related_barcodes: List[BarcodeInfo],
        employee: str,
    ) -> Dict[str, Any]:
        in_progress_barcodes = self._get_in_progress_barcodes(job_card)
        if in_progress_barcodes:
            self._complete_barcode_group(job_card, in_progress_barcodes)
            if self._is_sanal_adet_group_complete(job_card, in_progress_barcodes[0]):
                complete_job(job_card, 1)
            else:
                update_job_card_status(job_card, "On Hold")

        self._set_barcodes_in_progress(job_card, related_barcodes)
        update_job_card_status(job_card, "Work In Progress", employee)
        return {
            "status": "in_progress",
            "in_progress_barcodes": [b.barcode for b in related_barcodes],
        }

    def _get_in_progress_barcodes(self, job_card: Any) -> List[BarcodeInfo]:
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
            if b.status == BarcodeStatus.IN_PROGRESS.value
        ]

    def _is_sanal_adet_group_complete(
        self, job_card: Any, current_barcode: BarcodeInfo
    ) -> bool:
        job_card = frappe.get_doc("Job Card", job_card.name)
        related_barcodes = [
            b
            for b in job_card.custom_barcodes
            if int(b.sanal_adet) == int(current_barcode.sanal_adet)
        ]
        return all(b.status == BarcodeStatus.COMPLETED.value for b in related_barcodes)

    def _complete_barcode_group(self, job_card: Any, barcodes: List[BarcodeInfo]) -> None:
        tesdetay_refs = [b.tesdetay_ref for b in barcodes]
        job_card_refs = [job_card.name] * len(barcodes)

        bulk_update_operation_status(
            tesdetay_refs,
            job_card_refs,
            BarcodeStatus.COMPLETED.value,
        )
        save_with_retry(doc=job_card)

    def _set_barcodes_in_progress(
        self, job_card: Any, barcodes: List[BarcodeInfo]
    ) -> None:
        tesdetay_refs = [b.tesdetay_ref for b in barcodes]
        job_card_refs = [job_card.name] * len(barcodes)

        bulk_update_operation_status(
            tesdetay_refs,
            job_card_refs,
            BarcodeStatus.IN_PROGRESS.value,
        )

    def _get_current_barcode(self, job_card: Any, barcode: str) -> BarcodeInfo:
        b = next((b for b in job_card.custom_barcodes if b.barcode == barcode), None)
        if not b:
            frappe.throw(_("Barcode not found in job card"))

        return BarcodeInfo(
            barcode=b.barcode,
            model=b.model,
            sanal_adet=int(b.sanal_adet),
            tesdetay_ref=b.tesdetay_ref,
            status=BarcodeStatus(b.status),
            job_card_ref=job_card.name,
            quality_data=b.quality_data,
        )
