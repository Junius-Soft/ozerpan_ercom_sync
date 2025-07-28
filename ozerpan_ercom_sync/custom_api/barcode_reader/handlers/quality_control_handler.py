import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from ozerpan_ercom_sync.custom_api.barcode_reader.utils.tesdetay import (
    update_operation_status,
)

from ..base import OperationHandler
from ..constants import BarcodeStatus
from ..exceptions import QualityControlError
from ..models.barcode_info import BarcodeInfo
from ..models.quality_data import QualityData
from ..utils.job_card import (
    complete_job,
    is_job_fully_complete,
    submit_job_card,
    update_job_card_status,
)
from .kaynak_kose_handler import KaynakKoseHandler


@dataclass
class UnfinishedOperations:
    name: str
    job_card: str
    status: str
    is_corrective: bool


class QualityControlHandler(OperationHandler):
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

    def handle_barcode(
        self,
        barcode: str,
        job_card: Any,
        employee: str,
        quality_data: Optional[QualityData] = None,
        tesdetay_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.validate_operation(job_card)

        current_barcode = self._get_current_barcode(job_card, barcode, tesdetay_ref)
        related_barcodes = self.get_related_barcodes(job_card, current_barcode)
        quality_json_data = (
            json.loads(current_barcode.quality_data)
            if current_barcode.quality_data
            else None
        )

        if current_barcode.status == BarcodeStatus.COMPLETED:
            return {
                "message": _("This operation for this item is already completed."),
                "status": "error",
                "related_barcodes": [b.barcode for b in related_barcodes],
                "quality_data": quality_json_data,
            }

        elif current_barcode.status == BarcodeStatus.IN_PROGRESS:
            if not quality_data:
                return {
                    "message": _("Quality data is required for quality control"),
                    "status": "error",
                    "related_barcodes": [b.barcode for b in related_barcodes],
                    "quality_data": quality_json_data,
                }

            # Check if all previous operations are completed
            if not self._check_previous_operations_complete(current_barcode):
                frappe.throw(
                    _(
                        "This item has unfinished job cards. All jobs must be finished before quality control."
                    )
                )

            if quality_data.has_failures():
                return self._handle_quality_failure(
                    job_card, current_barcode, related_barcodes, quality_data, employee
                )

            return self._handle_quality_success(
                job_card, current_barcode, related_barcodes, employee, quality_data
            )

        else:  # PENDING or IN_CORRECTION
            in_progress_barcodes = self._get_in_progress_barcodes(job_card)
            if in_progress_barcodes:
                frappe.throw(
                    _(
                        "There is an open quality control process. You should finish the open process before starting a new one."
                    )
                )
                raise

            unfinished_operations = self._get_unfinished_previous_operations(
                job_card,
            )
            if unfinished_operations:
                raise QualityControlError(
                    "This item has unfinished operations.",
                    "unfinished operations",
                    {
                        "unfinished_operations": [
                            {
                                "name": operation.get("name"),
                                "job_card": operation.get("job_card"),
                                "status": operation.get("status"),
                                "is_corrective": operation.get("is_corrective"),
                            }
                            for operation in unfinished_operations
                        ]
                    },
                )

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

    def _handle_quality_success(
        self,
        job_card: Any,
        current_barcode: BarcodeInfo,
        related_barcodes: List[BarcodeInfo],
        employee: str,
        quality_data: QualityData,
    ) -> Dict[str, Any]:
        self._complete_barcode_group(job_card, related_barcodes)
        self._record_quality_result(job_card, employee, quality_data, success=True)

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
            "quality_status": "passed",
            "completed_barcodes": [b.barcode for b in related_barcodes],
        }

    def _handle_quality_failure(
        self,
        job_card: Any,
        current_barcode: BarcodeInfo,
        related_barcodes: List[BarcodeInfo],
        quality_data: QualityData,
        employee: str,
    ) -> Dict[str, Any]:
        if not quality_data.required_operations:
            frappe.throw(_("Correction operations are required when quality check fails"))

        correction_jobs = []
        sorted_operations = sorted(
            quality_data.required_operations, key=lambda x: x.get("priority")
        )

        for op in sorted_operations:
            correction_job = self._create_correction_job(job_card, current_barcode, op)
            correction_jobs.append(correction_job)

        # Set current barcode to correction status
        for barcode in related_barcodes:
            barcode_row = next(
                (b for b in job_card.custom_barcodes if b.barcode == barcode.barcode),
                None,
            )
            if barcode_row:
                barcode_row.status = "In Correction"
                update_operation_status(
                    barcode.tesdetay_ref,
                    job_card.name,
                    BarcodeStatus.IN_CORRECTION,
                    quality_data,
                )

        job_card.save(ignore_permissions=True)

        update_job_card_status(job_card, "On Hold")
        self._record_quality_result(job_card, employee, quality_data, success=False)

        return {
            "status": "failed",
            "quality_status": "failed",
            "correction_jobs": [job.name for job in correction_jobs],
        }

    def _check_previous_operations_complete(self, barcode: BarcodeInfo) -> bool:
        tesdetay = frappe.get_doc("TesDetay", barcode.tesdetay_ref)
        for op_state in tesdetay.operation_states:
            try:
                job_card = frappe.get_doc("Job Card", op_state.job_card_ref)
                if (
                    job_card.get("operation") not in ["Sevkiyat", "Kalite"]
                    and op_state.status == BarcodeStatus.PENDING.value
                ):
                    return False
            except frappe.DoesNotExistError:
                continue
        return True

    def _get_unfinished_previous_operations(
        self,
        job_card: any,
    ) -> List[UnfinishedOperations]:
        job_cards = frappe.get_all(
            "Job Card",
            filters={
                "work_order": job_card.work_order,
                "status": ["not in", ["Cancelled", "Completed"]],
                "operation": ["not in", ["Kalite"]],
            },
            fields=["name", "operation", "status", "is_corrective_job_card"],
        )
        unfinished_operations = []
        for jc in job_cards:
            item = {
                "name": jc.operation,
                "job_card": jc.name,
                "status": jc.status,
                "is_corrective": jc.is_corrective_job_card,
            }
            unfinished_operations.append(item)

        return unfinished_operations

    def _record_quality_result(
        self, job_card: Any, inspector: str, quality_data: QualityData, success: bool
    ) -> None:
        status = "Passed" if success else "Failed"
        comment = f"""Quality Inspection {status}
Time: {frappe.utils.now()}
Notes: {quality_data.overall_notes or "N/A"}

Criteria Results:"""

        for criterion in quality_data.criteria:
            result = "Passed" if criterion.get("passed") else "Failed"
            comment += f"\n- {criterion.get('name')}: {result}"
            if criterion.get("notes"):
                comment += f" ({criterion.get('notes')})"

        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Comment",
                "reference_doctype": "Job Card",
                "reference_name": job_card.name,
                "content": comment,
            }
        ).insert()

    def _create_correction_job(
        self, quality_job_card: Any, current_barcode: BarcodeInfo, operation_data: any
    ):
        try:
            original_job_card = frappe.get_doc(
                "Job Card",
                {
                    "production_item": quality_job_card.production_item,
                    "operation": operation_data.get("operation"),
                    "docstatus": ["!=", 2],
                },
            )
            correction_job = frappe.new_doc("Job Card")
            correction_job.update(
                {
                    "work_order": quality_job_card.work_order,
                    "operation": operation_data.get("operation"),
                    "production_item": quality_job_card.production_item,
                    "for_quantity": 1,
                    "is_corrective_job_card": 1,
                    "for_job_card": original_job_card.name,
                    "workstation": original_job_card.workstation,
                    "workstation_type": original_job_card.workstation_type,
                    "wip_warehouse": original_job_card.wip_warehouse,
                    "custom_target_sanal_adet": current_barcode.sanal_adet,
                    "custom_quality_job_card": quality_job_card.name,
                    # "remarks": self._format_correction_remarks(operation_data),
                    "remarks": operation_data.get("description"),
                }
            )

            correction_job.insert()
            return correction_job

        except frappe.DoesNotExistError:
            frappe.throw(
                _(f"No job card found for operation {operation_data.get('operation')}")
            )
            raise

    def _format_correction_remarks(self, operation_data: Any) -> str:
        return f"""Quality Control Correction Required:
    Description: {operation_data.get("description") if operation_data.get("description") else "N/A"}
    Reason for Correction: {operation_data.get("reason")}
    Priority: {operation_data.get("priority")}"""

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
        quality_data = None
        if current_barcode.status == BarcodeStatus.IN_CORRECTION:
            quality_data = current_barcode.quality_data
        return {
            "status": "in_progress",
            "in_progress_barcodes": [b.barcode for b in related_barcodes],
            "quality_data": json.loads(quality_data) if quality_data else None,
        }

    def _get_current_barcode(
        self, job_card: Any, barcode: str, tesdetay_ref: Optional[str] = None
    ) -> BarcodeInfo:
        # If tesdetay_ref is provided, find the specific barcode entry
        if tesdetay_ref:
            b = next(
                (
                    b
                    for b in job_card.custom_barcodes
                    if b.barcode == barcode and b.tesdetay_ref == tesdetay_ref
                ),
                None,
            )
        else:
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

    _get_other_in_progress_jobs = KaynakKoseHandler._get_other_in_progress_jobs
    _complete_barcode_group = KaynakKoseHandler._complete_barcode_group
    _complete_other_job_cards = KaynakKoseHandler._complete_other_job_cards
    _set_barcodes_in_progress = KaynakKoseHandler._set_barcodes_in_progress
    _get_in_progress_barcodes = KaynakKoseHandler._get_in_progress_barcodes
    _is_sanal_adet_group_complete = KaynakKoseHandler._is_sanal_adet_group_complete
    # _handle_pending_scan = KaynakKoseHandler._handle_pending_scan
