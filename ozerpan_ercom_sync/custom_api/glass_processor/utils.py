from typing import Any

import frappe


def get_job_card(glass_name: str) -> Any:
    print("\n\n--Get Job Card-- (Start)")

    try:
        glass_doc = frappe.get_doc("CamListe", glass_name)
    except frappe.DoesNotExistError:
        frappe.throw(f"CamListe not found: {glass_name}")

    job_cards = sorted(glass_doc.job_cards, key=lambda x: x.creation, reverse=True)
    try:
        job_card_doc = frappe.get_doc("Job Card", job_cards[0].job_card_ref)
    except frappe.DoesNotExistError:
        frappe.throw(f"Job Card not found for CamListe: {glass_name}")

    return job_card_doc
