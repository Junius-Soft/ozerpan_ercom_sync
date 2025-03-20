from typing import Any, Dict

import frappe
from frappe import _

from ..barcode_reader.utils.job_card import (
    complete_job,
    is_job_fully_complete,
    submit_job_card,
    update_job_card_status,
)


class GlassOperationProcessor:
    def process(self, glasses: Dict[str, Any], employee: str) -> Dict[str, any]:
        print("\n\n\n-- Process --\n\n\n")
        if glasses["current_glass"].status == "Completed":
            return {"status": "error", "message": _("This item is already completed")}

        job_card = self._get_job_card(glasses["current_glass"])

        if glasses["current_glass"].status == "Pending":
            print("--Pending--")
            return self._handle_pending_item(job_card, glasses, employee)
        elif glasses["current_glass"].status == "In Progress":
            print("--In Progress--")
            return self._handle_in_progress_item(job_card, glasses)
        else:
            frappe.throw(_("Invalid item status"))

    def _get_job_card(self, glass_item: Dict[str, Any]) -> Any:
        job_card = frappe.get_doc(
            "Job Card",
            {
                "production_item": f"{glass_item.parent}-{glass_item.poz_no}",
                "operation": "Cam",
                "docstatus": ["!=", 2],
            },
        )

        return job_card

    def _handle_pending_item(
        self, job_card: Any, glasses: Dict[str, Any], employee: str
    ) -> Dict[str, Any]:
        print("--- Handle Pending Item ---")
        current_glass = glasses["current_glass"]
        related_glasses = glasses["related_glasses"]

        print("Related Glasses:", len(related_glasses))

        # Check for in progress related glasses
        in_progress_glasses = [g for g in related_glasses if g.status == "In Progress"]
        if in_progress_glasses:
            for glass in in_progress_glasses:
                self._complete_glass(glass)
            if self._is_sanal_adet_group_complete(in_progress_glasses[0]):
                complete_job(job_card, 1)
                if is_job_fully_complete(job_card):
                    submit_job_card(job_card)
                else:
                    update_job_card_status(job_card, "On Hold")
            else:
                update_job_card_status(job_card, "On Hold")

        frappe.db.set_value("CamListe Item", current_glass.name, "status", "In Progress")
        update_job_card_status(job_card, "Work In Progress", employee)

        return {
            "status": "success",
            "message": _("Operation started"),
            "job_card": job_card.name,
        }

    def _handle_in_progress_item(
        self, job_card: Any, glasses: Dict[str, Any]
    ) -> Dict[str, Any]:
        current_glass = glasses["current_glass"]

        self._complete_glass(current_glass)
        if self._is_sanal_adet_group_complete(current_glass):
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

    def _complete_glass(self, glass: Dict):
        frappe.db.set_value("CamListe Item", glass.name, "status", "Completed")

    def _is_sanal_adet_group_complete(self, glass: Dict):
        filters = {
            "parent": glass.parent,
            "poz_no": glass.poz_no,
            "sanal_adet": glass.sanal_adet,
        }

        virtual_quantity_group = frappe.get_all(
            "CamListe Item", filters=filters, fields=["*"]
        )
        print("Virtual Quantity Group:")
        for item in virtual_quantity_group:
            print("Name:", item.name)
            print("Status:", item.status)
            print("Virtual Qty:", item.sanal_adet)

        return all(g.status == "Completed" for g in virtual_quantity_group)
