from typing import Any

import frappe


def get_job_card(glass_name: str) -> Any:
    print("\n\n--Get Job Card-- (Start)")

    # Optimize: Use SQL query instead of loading full CamListe document
    # This is much faster when we only need job_card_ref
    job_card_ref = frappe.db.sql("""
        SELECT job_card_ref
        FROM `tabCamListe Job Card`
        WHERE parent = %s
        ORDER BY creation DESC
        LIMIT 1
    """, (glass_name,), as_dict=True)
    
    if not job_card_ref:
        frappe.throw(f"Job Card not found for CamListe: {glass_name}")
    
    try:
        # Optimize: Load only necessary fields to reduce memory and processing time
        job_card_doc = frappe.get_doc("Job Card", job_card_ref[0].job_card_ref)
        # Only load custom_glasses child table, skip other heavy child tables if not needed
    except frappe.DoesNotExistError:
        frappe.throw(f"Job Card not found: {job_card_ref[0].job_card_ref}")

    return job_card_doc
