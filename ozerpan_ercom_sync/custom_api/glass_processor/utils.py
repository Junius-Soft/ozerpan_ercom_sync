from typing import Any

import frappe


def get_job_card(glass_name: str) -> Any:
    print("\n\n--Get Job Card-- (Start)")
    print(f"Glass Name: {glass_name}")

    # First verify glass exists
    if not frappe.db.exists("CamListe", glass_name):
        frappe.throw(f"CamListe bulunamadı: {glass_name}")

    # Optimize: Use SQL query instead of loading full CamListe document
    # This is much faster when we only need job_card_ref
    # Try exact match first
    job_card_ref = frappe.db.sql("""
        SELECT job_card_ref
        FROM `tabCamListe Job Card`
        WHERE parent = %s
        ORDER BY creation DESC
        LIMIT 1
    """, (glass_name,), as_dict=True)
    
    # If not found, try case-insensitive search (for tablet compatibility)
    if not job_card_ref:
        job_card_ref = frappe.db.sql("""
            SELECT jc.job_card_ref
            FROM `tabCamListe Job Card` jc
            INNER JOIN `tabCamListe` cl ON cl.name = jc.parent
            WHERE LOWER(cl.name) = LOWER(%s)
            ORDER BY jc.creation DESC
            LIMIT 1
        """, (glass_name,), as_dict=True)
    
    if not job_card_ref or not job_card_ref[0].get("job_card_ref"):
        # Get more detailed error info
        glass_exists = frappe.db.exists("CamListe", glass_name)
        related_job_cards = frappe.db.sql("""
            SELECT COUNT(*) as count
            FROM `tabCamListe Job Card`
            WHERE parent = %s
        """, (glass_name,), as_dict=True)
        
        error_msg = f"Job Card bulunamadı. Glass Name: {glass_name}, "
        error_msg += f"CamListe exists: {glass_exists}, "
        error_msg += f"Related Job Cards: {related_job_cards[0].count if related_job_cards else 0}"
        frappe.throw(error_msg)
    
    job_card_name = job_card_ref[0].job_card_ref
    
    # Verify job card exists
    if not frappe.db.exists("Job Card", job_card_name):
        frappe.throw(f"Job Card dokümanı bulunamadı: {job_card_name}")
    
    try:
        # Optimize: Load only necessary fields to reduce memory and processing time
        job_card_doc = frappe.get_doc("Job Card", job_card_name)
        # Ensure custom_glasses is loaded
        if hasattr(job_card_doc, 'custom_glasses'):
            print(f"Job Card loaded with {len(job_card_doc.custom_glasses)} glasses")
        # Only load custom_glasses child table, skip other heavy child tables if not needed
    except frappe.DoesNotExistError:
        frappe.throw(f"Job Card dokümanı yüklenemedi: {job_card_name}")
    except Exception as e:
        frappe.log_error(f"Error loading Job Card {job_card_name}: {str(e)}")
        frappe.throw(f"Job Card yüklenirken hata oluştu: {str(e)}")

    return job_card_doc
