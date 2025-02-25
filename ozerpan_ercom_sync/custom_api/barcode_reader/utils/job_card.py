from typing import Any, Optional

import frappe
from frappe.exceptions import TimestampMismatchError


def complete_job(job_card: Any, qty: int) -> None:
    try:
        for time_log in job_card.time_logs:
            if not time_log.to_time:
                time_log.to_time = frappe.utils.now()
                time_log.completed_qty = qty
                break
        job_card.save()
    except Exception as e:
        frappe.log_error(f"Error completing job: {str(e)}")
        raise


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
    job_card.save()


def submit_job_card(job_card: Any) -> None:
    try:
        update_job_card_status(job_card, "Completed")
        job_card.submit()
    except Exception as e:
        frappe.log_error(f"Error submitting job card {job_card.name}: {str(e)}")


def is_job_fully_complete(job_card: Any) -> bool:
    total_completed = sum(log.completed_qty or 0 for log in job_card.time_logs)
    return total_completed >= job_card.for_quantity


def get_job_card(operation: str, production_item: str, barcode: str) -> Any:
    job_card = frappe.get_doc(
        "Job Card",
        {
            "production_item": production_item,
            "operation": operation,
            "docstatus": 0,
        },
    )
    if not job_card:
        raise frappe.ValidationError(
            f"No active job card found for {operation} - {production_item} with barcode {barcode}"
        )
    return job_card


# When multiple users attempt to modify and save the same document simultaneously,
# a race condition can occur, causing data inconsistency. This retry mechanism
# helps prevent such issues by reloading and retrying the save on timestamp conflicts.
def save_with_retry(doc, max_retries=3):
    for attempt in range(max_retries):
        try:
            return doc.save()
        except TimestampMismatchError:
            if attempt == max_retries - 1:
                raise
            doc.reload()


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
