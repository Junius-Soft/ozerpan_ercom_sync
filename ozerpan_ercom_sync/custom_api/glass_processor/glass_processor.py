import json
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from ozerpan_ercom_sync.custom_api.barcode_reader.models.quality_data import QualityData
from ozerpan_ercom_sync.custom_api.glass_processor.utils import get_job_card

from ..barcode_reader.utils.job_card import (
    complete_job,
    is_job_fully_complete,
    save_with_retry,
    submit_job_card,
    update_job_card_status,
)
from .types import GlassOperationRequest


class GlassOperationProcessor:
    def process(self, operation_data: GlassOperationRequest) -> Dict[str, any]:
        print("\n\n\n-- Process --\n\n\n")
        raw_quality_data = operation_data.quality_data
        glass_name = operation_data.glass_name
        quality_data = QualityData(**raw_quality_data) if raw_quality_data else None
        job_card = get_job_card(glass_name)
        current_glass = self._get_current_glass(job_card, glass_name)
        related_glasses = self._get_related_glasses(job_card, current_glass)
        employee = operation_data["employee"]

        if current_glass.status == "Completed" and not quality_data:
            return {
                "status": "error",
                "message": _("This item is already completed"),
                "item": current_glass,
            }

        if current_glass.status == "Pending" or current_glass.status == "In Correction":
            print("--Pending--")
            return self._handle_pending_item(
                job_card, current_glass, related_glasses, employee
            )
        elif quality_data:
            print("--Quality Control--")
            return self._handle_quality_control(
                job_card, current_glass, related_glasses, quality_data, employee
            )
        else:
            frappe.throw(_("Invalid item status"))

    def _handle_quality_control(
        self,
        job_card: Any,
        current_glass: Dict,
        related_glasses: List[Dict],
        quality_data: QualityData,
        employee: str,
    ):
        print("--- Handle Quality Control --")

        if current_glass.status != "Completed":
            return {
                "status": "Error",
                "message": _("The item must be completed before quality control."),
                "glass_item": current_glass,
            }

        if quality_data.has_failures():
            return self._handle_quality_failure(
                job_card, current_glass, quality_data, employee
            )

        glass_quality_data = current_glass.quality_data

        return {
            "status": "success",
            "message": _("Quality control completed"),
            "job_card": job_card.name,
            "quality_data": json.loads(glass_quality_data)
            if glass_quality_data
            else None,
        }

    def _handle_quality_failure(
        self,
        job_card: Dict[str, Any],
        current_glass: Dict[str, Any],
        quality_data: QualityData,
        employee: str,
    ) -> Dict[str, Any]:
        print("\n\n\n-- Handle Quality Failure --")
        correction_job = self._create_correction_job(
            job_card, current_glass, quality_data
        )

        glass_quality_data = current_glass.quality_data
        job_card.save()

        return {
            "status": "failed",
            "quality_status": "failed",
            "correction_job": correction_job.name,
            "quality_data": json.loads(glass_quality_data)
            if glass_quality_data
            else None,
        }

    def _create_correction_job(
        self,
        quality_job_card: Dict[str, Any],
        current_glass: Dict[str, Any],
        quality_data: Dict[str, Any],
    ) -> Dict[str, any]:
        try:
            print("\n\n\n-- Create Correction Job --")

            correction_job = frappe.new_doc("Job Card")
            correction_job.update(
                {
                    "work_order": quality_job_card.work_order,
                    "operation": quality_job_card.operation,
                    "production_item": quality_job_card.production_item,
                    "for_quantity": 1,
                    "is_corrective_job_card": 1,
                    "for_job_card": quality_job_card.name,
                    "workstation": quality_job_card.workstation,
                    "workstation_type": quality_job_card.workstation_type,
                    "wip_warehouse": quality_job_card.wip_warehouse,
                    "custom_target_sanal_adet": current_glass.sanal_adet,
                    "custom_quality_job_card": quality_job_card.name,
                    "remarks": quality_data.overall_notes,
                }
            )
            glasses = [
                {
                    "glass_ref": current_glass.get("glass_ref"),
                    "order_no": current_glass.get("order_no"),
                    "stock_code": current_glass.get("stock_code"),
                    "poz_no": current_glass.get("poz_no"),
                    "sanal_adet": current_glass.get("sanal_adet"),
                    "status": "Pending",
                    "quality_data": current_glass.get("quality_data"),
                }
            ]

            self.update_glass_job_card_status(
                glass_ref=current_glass.glass_ref,
                job_card_name=quality_job_card.name,
                quality_data=quality_data,
            )
            correction_job.set("custom_glasses", glasses)
            correction_job.insert()
            return correction_job
        except Exception as e:
            frappe.log_error(f"Error creating correction job: {str(e)}")
            frappe.throw(_("Failed to create correction job"))

    def _handle_pending_item(
        self,
        job_card: Any,
        current_glass: Dict,
        related_glasses: List[Dict],
        employee: str,
    ) -> Dict[str, Any]:
        print("--- Handle Pending Item ---")

        if job_card.status != "Work In Progress":
            update_job_card_status(job_card, "Work In Progress", employee)

        self._complete_glasses(job_card, [current_glass])
        if self._is_sanal_adet_group_complete(job_card, current_glass):
            complete_job(job_card, 1)
            if is_job_fully_complete(job_card):
                submit_job_card(job_card)
            else:
                update_job_card_status(job_card, "On Hold")
        else:
            update_job_card_status(job_card, "On Hold")

        glass_quality_data = current_glass.quality_data

        return {
            "status": "completed",
            "job_card": job_card.name,
            "glass": current_glass.glass_ref,
            "quality_data": json.loads(glass_quality_data)
            if glass_quality_data
            else None,
        }

    def _handle_in_progress_item(
        self,
        job_card: Any,
        current_glass: Dict,
    ) -> Dict[str, Any]:
        print("\n\n\n-- Handle In Progress --")

        self._complete_glasses(job_card, [current_glass])
        if self._is_sanal_adet_group_complete(job_card, current_glass):
            complete_job(job_card, 1)
            if is_job_fully_complete(job_card):
                submit_job_card(job_card)
            else:
                update_job_card_status(job_card, "On Hold")
        else:
            update_job_card_status(job_card, "On Hold")

        glass_quality_data = current_glass.quality_data

        return {
            "status": "completed",
            "job_card": job_card.name,
            "glass": current_glass.glass_ref,
            "quality_data": json.loads(glass_quality_data)
            if glass_quality_data
            else None,
        }

    def _complete_glasses(self, job_card: Any, glasses: List[Dict]):
        for glass in glasses:
            glass_row = next(
                (g for g in job_card.custom_glasses if g.glass_ref == glass.glass_ref),
                None,
            )
            if glass_row:
                self.update_glass_job_card_status(
                    glass.glass_ref, job_card.name, "Completed"
                )

        save_with_retry(job_card)

    def update_glass_job_card_status(
        self,
        glass_ref: str,
        job_card_name: str,
        status: Optional[str] = None,
        quality_data: Optional[QualityData] = None,
    ) -> None:
        glass = frappe.get_doc("CamListe", glass_ref)
        if quality_data:
            glass.quality_data = json.dumps(quality_data.__dict__)

        if status:
            for jc in glass.job_cards:
                if jc.job_card_ref == job_card_name:
                    jc.status = status
                    glass.save()
                    break

    def _is_sanal_adet_group_complete(self, job_card: any, glass: Dict) -> bool:
        job_card = frappe.get_doc("Job Card", job_card.name)
        related_glasses = [
            g for g in job_card.custom_glasses if g.sanal_adet == glass.sanal_adet
        ]
        return all(g.status == "Completed" for g in related_glasses)

    def _get_related_glasses(self, job_card: Any, current_glass: Dict) -> List[Dict]:
        return [g for g in job_card.custom_glasses]

    def _get_current_glass(self, job_card: any, glass_name: str) -> Dict:
        glass = next(
            (g for g in job_card.custom_glasses if g.glass_ref == glass_name),
            None,
        )

        return glass
