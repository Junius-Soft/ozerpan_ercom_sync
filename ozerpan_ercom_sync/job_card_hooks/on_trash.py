from typing import Dict, List

import frappe

from ozerpan_ercom_sync.utils import timer


@timer
def on_trash(doc, method) -> None:
    """
    Handle Job Card deletion for both regular and corrective job cards
    Removes job card references from related TesDetay documents
    """
    print("\n\n\n-- Job Card On Trash --")
    remove_job_card_link_from_tesdetay(doc)
    remove_job_card_link_from_glasslist(doc)


def remove_job_card_link_from_glasslist(job_card_doc) -> None:
    glasslist_docs = get_affected_glasslist_docs(job_card_doc)

    for g in glasslist_docs:
        modified = False
        job_cards_to_remove = []

        for jc in g.job_cards:
            if jc.job_card_ref == job_card_doc.name:
                job_cards_to_remove.append(jc)
                modified = True
        for jc in job_cards_to_remove:
            g.job_cards.remove(jc)

        if modified:
            try:
                g.save(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(
                    f"Error updating GlassList {g.name} while deleting job card {job_card_doc.name}: {str(e)}"
                )


def get_affected_glasslist_docs(job_card_doc) -> List[Dict]:
    glass_refs = {g.glass_ref for g in job_card_doc.custom_glasses if g.glass_ref}

    if job_card_doc.is_corrective_job_card:
        additional_refs = frappe.db.sql(
            """
            SELECT DISTINCT parent
            FROM `tabCamListe Job Card`
            WHERE job_card_ref = %s
            """,
            job_card_doc.name,
            as_dict=1,
        )

        glass_refs.update({ref.parent for ref in additional_refs})

    return [
        frappe.get_doc("CamListe", ref)
        for ref in glass_refs
        if frappe.db.exists("CamListe", ref)
    ]


def remove_job_card_link_from_tesdetay(job_card_doc) -> None:
    """
    Remove job card references from TesDetay documents
    Handles both regular and corrective job cards
    """
    # Get all affected TesDetay documents
    tesdetay_docs = get_affected_tesdetay_docs(job_card_doc)

    # Remove operation states referencing this job card
    for td in tesdetay_docs:
        modified = False
        states_to_remove = []

        for op_state in td.operation_states:
            if op_state.job_card_ref == job_card_doc.name:
                states_to_remove.append(op_state)
                modified = True

        # Remove the identified states
        for state in states_to_remove:
            td.operation_states.remove(state)

        if modified:
            try:
                td.save(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(
                    f"Error updating TesDetay {td.name} while deleting job card {job_card_doc.name}: {str(e)}"
                )


def get_affected_tesdetay_docs(job_card_doc) -> List[Dict]:
    """
    Get all TesDetay documents affected by this job card deletion
    Handles both regular and corrective cases
    """
    # Get TesDetay references from custom_barcodes
    tesdetay_refs = {
        b.tesdetay_ref for b in job_card_doc.custom_barcodes if b.tesdetay_ref
    }

    # For corrective job cards, also check operation states directly
    if job_card_doc.is_corrective_job_card:
        # Get additional TesDetay documents that might reference this job card
        additional_refs = frappe.db.sql(
            """
            SELECT DISTINCT parent
            FROM `tabTesDetay Operation Status`
            WHERE job_card_ref = %s
        """,
            job_card_doc.name,
            as_dict=1,
        )

        tesdetay_refs.update({ref.parent for ref in additional_refs})

    # Get all unique TesDetay documents
    return [
        frappe.get_doc("TesDetay", ref)
        for ref in tesdetay_refs
        if frappe.db.exists("TesDetay", ref)
    ]
