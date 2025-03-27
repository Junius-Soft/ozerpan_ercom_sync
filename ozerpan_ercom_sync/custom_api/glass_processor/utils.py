from typing import Any

import frappe


def get_job_card(glass_name: str) -> Any:
    parts = glass_name.split("-")
    production_item = f"{parts[0]}-{parts[1]}"
    active_job_cards = frappe.get_all(
        "Job Card",
        filters={
            "production_item": production_item,
            "operation": "Cam",
            "docstatus": 0,
        },
        as_list=True,
    )

    if active_job_cards:
        for job_card_name in active_job_cards:
            job_card = frappe.get_doc("Job Card", job_card_name[0])

            if job_card.custom_glasses:
                for glass in job_card.custom_glasses:
                    if glass.glass_ref == glass_name and glass.status != "Completed":
                        return job_card

    completed_job_cards = frappe.get_all(
        "Job Card",
        filters={
            "production_item": production_item,
            "operation": "Cam",
        },
        order_by="modified desc",
        as_list=True,
    )

    for job_card_name in completed_job_cards:
        job_card = frappe.get_doc("Job Card", job_card_name[0])

        if job_card.custom_glasses:
            for glass in job_card.custom_glasses:
                if glass.glass_ref == glass_name:
                    return job_card

    raise frappe.ValidationError(
        f"No Job card found with glass {glass} for Cam - {production_item}"
    )
