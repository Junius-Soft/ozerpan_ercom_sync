import json
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from ozerpan_ercom_sync.custom_api.barcode_reader.models.quality_data import QualityData

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

        job_card = self._get_job_card(glass_name)
        current_glass = self._get_current_glass(job_card, glass_name)
        related_glasses = self._get_related_glasses(job_card, current_glass)
        employee = operation_data["employee"]
        print("Glass:", current_glass)

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
        elif current_glass.status == "In Progress":
            print("--In Progress--")
            return self._handle_in_progress_item(job_card, current_glass)
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

        # return self._handle_quality_success(
        #     job_card, current_glass, quality_data, employee
        # )

        return {
            "status": "success",
            "message": _("Quality control completed"),
            "job_card": job_card.name,
        }

    def _handle_quality_failure(
        self,
        job_card: Dict[str, Any],
        current_glass: Dict[str, Any],
        quality_data: QualityData,
        employee: str,
    ) -> Dict[str, Any]:
        correction_job = self._create_correction_job(job_card, current_glass)

    def _create_correction_job(
        self, job_card: Dict[str, Any], current_glass: Dict[str, Any]
    ) -> Dict[str, any]:
        pass

    def _handle_pending_item(
        self,
        job_card: Any,
        current_glass: Dict,
        related_glasses: List[Dict],
        employee: str,
    ) -> Dict[str, Any]:
        print("--- Handle Pending Item ---")
        print("Current Glass:", current_glass)
        print("Related Glasses:", related_glasses)
        in_progress_glasses = [g for g in related_glasses if g.status == "In Progress"]

        if in_progress_glasses:
            self._complete_glasses(job_card, in_progress_glasses)
            if self._is_sanal_adet_group_complete(job_card, in_progress_glasses[0]):
                complete_job(job_card, 1)
                if is_job_fully_complete(job_card):
                    submit_job_card(job_card)
                else:
                    update_job_card_status(job_card, "On Hold")
            else:
                update_job_card_status(job_card, "On Hold")

        self._set_glass_in_progress(job_card, current_glass)
        update_job_card_status(job_card, "Work In Progress", employee)

        return {
            "status": "in_progress",
            "job_card": job_card.name,
            "glass": current_glass,
        }

    def _handle_in_progress_item(
        self,
        job_card: Any,
        current_glass: Dict,
    ) -> Dict[str, Any]:
        print("\n\n\n-- Handle In Progress --")

        # TODO: Continue
        self._complete_glasses(job_card, [current_glass])
        if self._is_sanal_adet_group_complete(job_card, current_glass):
            complete_job(job_card, 1)
            if is_job_fully_complete(job_card):
                submit_job_card(job_card)
            else:
                update_job_card_status(job_card, "On Hold")
        else:
            update_job_card_status(job_card, "On Hold")

        return {
            "status": "success",
            "message": _("Operation completed"),
            "job_card": job_card.name,
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
        status: str,
        quality_data: Optional[QualityData] = None,
    ) -> None:
        glass = frappe.get_doc("CamListe", glass_ref)
        if quality_data:
            glass.quality_data = json.dumps(quality_data.__dict__)

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

    def _get_job_card(self, glass_name: Dict[str, Any]) -> Any:
        parts = glass_name.split("-")
        order_no = parts[0]
        poz_no = parts[1]
        print("Parts:", parts)
        job_card = frappe.get_doc(
            "Job Card",
            {
                "production_item": f"{order_no}-{poz_no}",
                "operation": "Cam",
                "docstatus": ["!=", 2],
            },
        )
        return job_card

    def _set_glass_in_progress(self, job_card: Any, glass: Dict) -> None:
        print("\n\nglass_ref:", job_card.custom_glasses[0].as_dict())
        print("glass:", glass.as_dict())
        glass_row = next(
            (g for g in job_card.custom_glasses if g.glass_ref == glass.glass_ref),
            None,
        )
        print("\n\n\nGlass Row:", glass_row)
        if glass_row:
            glass_row.status = "In Progress"
            self.update_glass_job_card_status(
                glass_row.glass_ref, job_card.name, "In Progress"
            )

        job_card.save()

    def _get_related_glasses(self, job_card: Any, current_glass: Dict) -> List[Dict]:
        return [g for g in job_card.custom_glasses]

    def _get_current_glass(self, job_card: any, glass_name: str) -> Dict:
        glass = next(
            (g for g in job_card.custom_glasses if g.glass_ref == glass_name),
            None,
        )

        return glass
