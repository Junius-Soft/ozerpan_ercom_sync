from typing import Any, Optional

import frappe
from frappe import _
from frappe.exceptions import TimestampMismatchError


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


def update_job_card_status(
    job_card: Any,
    status: str,
    employee: Optional[str] = None,
    reason: Optional[str] = None,
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
                time_log.custom_reason = reason
                break
    save_with_retry(job_card)


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
    # First get all active job cards matching the basic criteria
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
def save_with_retry(doc, max_retries=3):
    for attempt in range(max_retries):
        try:
            return doc.save()
        except TimestampMismatchError:
            if attempt == max_retries - 1:
                raise
            doc.reload()


def complete_job_bulk(job_card_names: list, qty: int, employee: str) -> None:
    """
    Complete multiple job cards simultaneously using direct SQL updates
    to bypass the overlap validation that prevents the same employee
    from working on multiple workstations.
    """
    try:
        from datetime import datetime

        current_time = frappe.utils.now()

        # Update time logs for all job cards in bulk
        for job_card_name in job_card_names:
            # Find the open time log (without to_time) for each job card

            for_quantity, total_completed_qty = frappe.db.get_value(
                "Job Card",
                job_card_name,
                ["for_quantity", "total_completed_qty"],
            )
            if qty + total_completed_qty > for_quantity:
                frappe.throw(_("Quantity should be less than Qty To Manufacture"))

            open_time_logs = frappe.db.sql(
                """
                SELECT name, from_time FROM `tabJob Card Time Log`
                WHERE parent = %s AND to_time IS NULL
                ORDER BY idx DESC
                LIMIT 1
            """,
                (job_card_name,),
                as_dict=True,
            )

            if open_time_logs:
                time_log_name = open_time_logs[0].name
                from_time = open_time_logs[0].from_time

                # Calculate time_in_mins
                # Convert from_time to datetime if it's a string
                if isinstance(from_time, str):
                    try:
                        from_time_dt = frappe.utils.get_datetime(from_time)
                    except Exception:
                        from_time_dt = datetime.fromisoformat(
                            from_time.replace("Z", "+00:00")
                        )
                else:
                    from_time_dt = from_time

                # Convert current_time to datetime if it's a string
                if isinstance(current_time, str):
                    try:
                        to_time_dt = frappe.utils.get_datetime(current_time)
                    except Exception:
                        to_time_dt = datetime.fromisoformat(
                            current_time.replace("Z", "+00:00")
                        )
                else:
                    to_time_dt = current_time

                # Calculate time difference in minutes
                time_diff = to_time_dt - from_time_dt
                time_in_mins = max(0, int(time_diff.total_seconds() / 60))

                # Update the time log directly
                frappe.db.sql(
                    """
                    UPDATE `tabJob Card Time Log`
                    SET to_time = %s, completed_qty = %s, time_in_mins = %s, modified = %s
                    WHERE name = %s
                """,
                    (current_time, qty, time_in_mins, current_time, time_log_name),
                )

                # Calculate total time in minutes for the job card
                total_time_result = frappe.db.sql(
                    """
                    SELECT SUM(time_in_mins) as total_time
                    FROM `tabJob Card Time Log`
                    WHERE parent = %s
                """,
                    (job_card_name,),
                    as_dict=True,
                )

                total_time_in_mins = (
                    total_time_result[0].total_time
                    if total_time_result and total_time_result[0].total_time
                    else 0
                )

                # Calculate total completed quantity for the job card
                total_qty_result = frappe.db.sql(
                    """
                    SELECT SUM(completed_qty) as total_completed
                    FROM `tabJob Card Time Log`
                    WHERE parent = %s AND completed_qty IS NOT NULL
                """,
                    (job_card_name,),
                    as_dict=True,
                )

                total_completed_qty = (
                    total_qty_result[0].total_completed
                    if total_qty_result and total_qty_result[0].total_completed
                    else 0
                )

                # Update job card status to Completed with total time, completed qty, and actual end date
                frappe.db.sql(
                    """
                    UPDATE `tabJob Card`
                    SET status = 'Completed', total_time_in_mins = %s, total_completed_qty = %s, actual_end_date = %s, modified = %s
                    WHERE name = %s
                """,
                    (
                        total_time_in_mins,
                        total_completed_qty,
                        current_time,
                        current_time,
                        job_card_name,
                    ),
                )

        # Commit the changes
        frappe.db.commit()

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error completing jobs in bulk: {str(e)}")
        raise


def update_job_card_status_bulk(
    job_card_names: list, status: str, employee: str = None, reason: str = None
) -> None:
    """
    Update multiple job cards status simultaneously using direct SQL updates
    to bypass the overlap validation that prevents the same employee
    from working on multiple workstations.
    """
    try:
        current_time = frappe.utils.now()

        for job_card_name in job_card_names:
            if status == "Work In Progress" and employee:
                # Check if job card already has actual_start_date
                job_card_data = frappe.db.get_value(
                    "Job Card", job_card_name, ["actual_start_date"], as_dict=True
                )

                # Update job card status and actual_start_date if needed
                if not job_card_data.actual_start_date:
                    frappe.db.sql(
                        """
                        UPDATE `tabJob Card`
                        SET status = %s, actual_start_date = %s, modified = %s
                        WHERE name = %s
                    """,
                        (status, current_time, current_time, job_card_name),
                    )
                else:
                    frappe.db.sql(
                        """
                        UPDATE `tabJob Card`
                        SET status = %s, modified = %s
                        WHERE name = %s
                    """,
                        (status, current_time, job_card_name),
                    )

                # Get the next idx value for the time log
                max_idx_result = frappe.db.sql(
                    """
                    SELECT COALESCE(MAX(idx), 0) + 1 as next_idx
                    FROM `tabJob Card Time Log`
                    WHERE parent = %s
                """,
                    (job_card_name,),
                    as_dict=True,
                )

                next_idx = max_idx_result[0].next_idx if max_idx_result else 1

                # Add new time log entry
                frappe.db.sql(
                    """
                    INSERT INTO `tabJob Card Time Log` (name, parent, parenttype, parentfield, idx, from_time, employee, creation, modified, docstatus)
                    VALUES (%s, %s, 'Job Card', 'time_logs', %s, %s, %s, %s, %s, 0)
                """,
                    (
                        frappe.generate_hash(),
                        job_card_name,
                        next_idx,
                        current_time,
                        employee,
                        current_time,
                        current_time,
                    ),
                )

            elif status == "On Hold":
                # Find the open time log (without to_time) and close it
                open_time_logs = frappe.db.sql(
                    """
                    SELECT name, from_time FROM `tabJob Card Time Log`
                    WHERE parent = %s AND to_time IS NULL
                    ORDER BY idx DESC
                    LIMIT 1
                """,
                    (job_card_name,),
                    as_dict=True,
                )

                if open_time_logs:
                    time_log_name = open_time_logs[0].name
                    from_time = open_time_logs[0].from_time

                    # Calculate time_in_mins
                    from datetime import datetime

                    # Convert from_time to datetime if it's a string
                    if isinstance(from_time, str):
                        try:
                            from_time_dt = frappe.utils.get_datetime(from_time)
                        except Exception:
                            from_time_dt = datetime.fromisoformat(
                                from_time.replace("Z", "+00:00")
                            )
                    else:
                        from_time_dt = from_time

                    # Convert current_time to datetime if it's a string
                    if isinstance(current_time, str):
                        try:
                            to_time_dt = frappe.utils.get_datetime(current_time)
                        except Exception:
                            to_time_dt = datetime.fromisoformat(
                                current_time.replace("Z", "+00:00")
                            )
                    else:
                        to_time_dt = current_time

                    # Calculate time difference in minutes
                    time_diff = to_time_dt - from_time_dt
                    time_in_mins = max(0, int(time_diff.total_seconds() / 60))

                    # Update the time log to close it
                    frappe.db.sql(
                        """
                        UPDATE `tabJob Card Time Log`
                        SET to_time = %s, time_in_mins = %s, custom_reason = %s, modified = %s
                        WHERE name = %s
                    """,
                        (current_time, time_in_mins, reason, current_time, time_log_name),
                    )

                # Calculate total time in minutes for the job card
                total_time_result = frappe.db.sql(
                    """
                    SELECT SUM(time_in_mins) as total_time
                    FROM `tabJob Card Time Log`
                    WHERE parent = %s
                """,
                    (job_card_name,),
                    as_dict=True,
                )

                total_time_in_mins = (
                    total_time_result[0].total_time
                    if total_time_result and total_time_result[0].total_time
                    else 0
                )

                # Update job card status and total time
                frappe.db.sql(
                    """
                    UPDATE `tabJob Card`
                    SET status = %s, total_time_in_mins = %s, modified = %s
                    WHERE name = %s
                """,
                    (status, total_time_in_mins, current_time, job_card_name),
                )

            else:
                # For other statuses, just update the status
                frappe.db.sql(
                    """
                    UPDATE `tabJob Card`
                    SET status = %s, modified = %s
                    WHERE name = %s
                """,
                    (status, current_time, job_card_name),
                )

        # Commit the changes
        frappe.db.commit()

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error updating job card status in bulk: {str(e)}")
        raise


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
