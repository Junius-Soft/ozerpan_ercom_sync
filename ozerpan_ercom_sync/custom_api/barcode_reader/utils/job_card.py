from typing import Any, Optional

import frappe
from frappe.exceptions import TimestampMismatchError

from ozerpan_ercom_sync.utils import timer


@timer
def complete_job(job_card: Any, qty: int) -> None:
    try:
        job_card.reload()
        for time_log in job_card.time_logs:
            if not time_log.to_time:
                time_log.to_time = frappe.utils.now()
                time_log.completed_qty = qty
                break
        save_with_retry(job_card)
    except Exception as e:
        frappe.log_error(f"Error completing job: {str(e)}")
        raise


@timer
def update_job_card_status(
    job_card: Any,
    status: str,
    employee: Optional[str] = None,
) -> None:
    job_card.status = status

    if status == "Work In Progress" and employee:
        if not job_card.actual_start_date:
            job_card.actual_start_date = frappe.utils.now()

        job_card.append(
            "time_logs",
            {
                "from_time": frappe.utils.now(),
                "employee": employee,
            },
        )

    elif status == "On Hold":
        for time_log in job_card.time_logs:
            if not time_log.to_time:  # Find the open time log
                time_log.to_time = frappe.utils.now()
                break
    save_with_retry(job_card)


@timer
def submit_job_card(job_card: Any) -> None:
    try:
        update_job_card_status(job_card, "Completed")
        job_card.submit()
    except Exception as e:
        frappe.log_error(f"Error submitting job card {job_card.name}: {str(e)}")


@timer
def is_job_fully_complete(job_card: Any) -> bool:
    total_completed = sum(log.completed_qty or 0 for log in job_card.time_logs)
    return total_completed >= job_card.for_quantity


@timer
def get_job_card(operation: str, production_item: str, barcode: str) -> Any:
    # First get all active job cards matching the basic criteria
    print("Production Item:", production_item)
    print("Barcode:", barcode)
    active_job_cards = frappe.get_all(
        "Job Card",
        filters={
            "production_item": production_item,
            "operation": operation,
            "docstatus": 0,
        },
        as_list=True,
    )

    # Try to find an active job card with the matching barcode
    if active_job_cards:
        for job_card_name in active_job_cards:
            job_card = frappe.get_doc("Job Card", job_card_name[0])

            # Check if the job card contains the barcode in its custom_barcodes child table
            if job_card.custom_barcodes:
                for custom_barcode in job_card.custom_barcodes:
                    if (
                        custom_barcode.barcode == barcode
                        and custom_barcode.status != "Completed"
                    ):
                        return job_card

    # If no active job card with matching barcode found, look for completed job cards
    completed_job_cards = frappe.get_all(
        "Job Card",
        filters={
            "production_item": production_item,
            "operation": operation,
        },
        order_by="modified desc",  # Get the most recently modified first
        as_list=True,
    )

    for job_card_name in completed_job_cards:
        job_card = frappe.get_doc("Job Card", job_card_name[0])

        # Check if the job card contains the barcode in its custom_barcodes child table
        if job_card.custom_barcodes:
            for custom_barcode in job_card.custom_barcodes:
                if custom_barcode.barcode == barcode:
                    return job_card

    # If no job card with matching barcode found, raise error
    raise frappe.ValidationError(
        f"No job card found with barcode {barcode} for {operation} - {production_item}"
    )


# When multiple users attempt to modify and save the same document simultaneously,
# a race condition can occur, causing data inconsistency. This retry mechanism
# helps prevent such issues by reloading and retrying the save on timestamp conflicts.
@timer
def save_with_retry(doc, max_retries=3):
    for attempt in range(max_retries):
        try:
            return doc.save()
        except TimestampMismatchError:
            if attempt == max_retries - 1:
                raise
            doc.reload()


@timer
def format_job_card_response(job_card_doc):
    """Format a Frappe Job Card document into a specific response structure."""
    required_job_card_fields = [
        "name",
        "work_order",
        "bom_no",
        "production_item",
        "posting_date",
        "for_quantity",
        "total_completed_qty",
        "process_loss_qty",
        "expected_start_date",
        "time_required",
        "expected_end_date",
        "actual_start_date",
        "total_time_in_mins",
        "actual_end_date",
        "operation",
        "wip_warehouse",
        "workstation",
        "hour_rate",
        "transferred_qty",
        "requested_qty",
        "status",
        "employee",
        "is_corrective_job_card",
        "remarks",
    ]

    formatted_job_card = {
        field: job_card_doc.get(field) for field in required_job_card_fields
    }

    # Format time logs
    formatted_job_card["time_logs"] = [
        {
            "idx": log.idx,
            "employee": log.employee,
            "from_time": log.from_time,
            "to_time": log.to_time,
            "time_in_mins": log.time_in_mins,
            "completed_qty": log.completed_qty,
        }
        for log in job_card_doc.time_logs
    ]

    # Format scheduled time logs
    formatted_job_card["scheduled_time_logs"] = [
        {
            "idx": log.idx,
            "from_time": log.from_time,
            "to_time": log.to_time,
            "time_in_mins": log.time_in_mins,
            "parent": log.parent,
        }
        for log in job_card_doc.scheduled_time_logs
    ]

    # Format custom barcodes
    formatted_job_card["custom_barcodes"] = [
        {
            "idx": barcode.idx,
            "model": barcode.model,
            "barcode": barcode.barcode,
            "poz_no": barcode.poz_no,
            "sanal_adet": barcode.sanal_adet,
            "status": barcode.status,
            "tesdetay_ref": barcode.tesdetay_ref,
        }
        for barcode in job_card_doc.custom_barcodes
    ]

    return formatted_job_card
