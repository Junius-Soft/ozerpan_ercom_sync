

from ozerpan_ercom_sync.utils import bulk_delete_child_rows, timer


@timer
def on_trash(doc, method) -> None:
    """
    Handle Job Card deletion for both regular and corrective job cards
    Removes job card references from related TesDetay documents
    """
    print("\n\n\n-- Job Card On Trash --")
    remove_job_card_link_from_tesdetay(doc)
    remove_job_card_link_from_glasslist(doc)


@timer
def remove_job_card_link_from_glasslist(job_card_doc) -> None:
    bulk_delete_child_rows(
        child_table="CamListe Job Card",
        parent_field="job_card_ref",
        references=[job_card_doc.name],
    )


@timer
def remove_job_card_link_from_tesdetay(job_card_doc) -> None:
    """
    Remove job card references from TesDetay documents
    Handles both regular and corrective job cards
    """

    bulk_delete_child_rows(
        child_table="TesDetay Operation Status",
        parent_field="job_card_ref",
        references=[job_card_doc.name],
    )
