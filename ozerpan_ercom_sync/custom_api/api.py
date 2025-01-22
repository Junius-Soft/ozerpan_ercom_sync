import frappe
from frappe import _


@frappe.whitelist()
def read_barcode(barcode: str, employee: str, operation: str):
    print("\n\n\n-- Read Barcode --")
    td = frappe.get_doc("TesDetay", {"barkod": barcode})
    production_item_name = f"{td.siparis_no}-{td.poz_no}"
    job_card = get_job_card_by_operation_and_production_item(
        operation, production_item_name
    )
    current_barcode = find_barcode_in_job_card(job_card, barcode)
    related_barcodes = get_related_barcodes(job_card, current_barcode)

    if current_barcode.status == "Completed":
        frappe.throw(_("This barcode is already completed"))

    elif current_barcode.status == "In Progress":
        handle_in_progress_scan(job_card, current_barcode, related_barcodes, employee)

    else:
        handle_pending_scan(job_card, current_barcode, related_barcodes, employee)
    print("\n\n\n")


def handle_in_progress_scan(job_card, current_barcode, related_barcodes, employee):
    complete_barcodes(job_card, related_barcodes)

    if is_sanal_adet_group_complete(job_card, current_barcode.sanal_adet):
        complete_job(job_card, 1)

        if is_job_fully_complete(job_card):
            submit_job_card(job_card)
        else:
            set_job_card_on_hold(job_card)
    else:
        set_job_card_on_hold(job_card)


def handle_pending_scan(job_card, current_barcode, related_barcodes, employee):
    in_progress_operations = get_in_progress_operations(current_barcode.tesdetay_ref)

    if in_progress_operations:
        handle_other_job_cards_completion(in_progress_operations)

    in_progress_barcodes = get_in_progress_barcodes(job_card)
    if in_progress_barcodes:
        complete_barcodes(job_card, in_progress_barcodes)
        if is_sanal_adet_group_complete(job_card, in_progress_barcodes[0].sanal_adet):
            complete_job(job_card, 1)
        else:
            set_job_card_on_hold(job_card)

    set_barcodes_in_progress(job_card, related_barcodes)
    set_job_card_in_progress(job_card, employee)


#### HELPERS ####


def get_in_progress_barcodes(job_card):
    """
    Get all barcodes with "In Progress" status from job card
    """
    return [b for b in job_card.custom_barcodes if b.status == "In Progress"]


def handle_other_job_cards_completion(in_progress_operations):
    """
    Handle completion of in-progress operations in other job cards
    """
    for job_card, operation_state in in_progress_operations:
        related_barcode = next(
            (
                b
                for b in job_card.custom_barcodes
                if b.tesdetay_ref == operation_state.parent
            ),
            None,
        )

        if related_barcode:
            related_barcodes = [
                b
                for b in job_card.custom_barcodes
                if b.model == related_barcode.model
                and int(b.sanal_adet) == int(related_barcode.sanal_adet)
            ]

            complete_barcodes(job_card, related_barcodes)

            if is_sanal_adet_group_complete(job_card, related_barcode.sanal_adet):
                complete_job(job_card, 1)

                if is_job_fully_complete(job_card):
                    submit_job_card(job_card)
                else:
                    set_job_card_on_hold(job_card)
            else:
                set_job_card_on_hold(job_card)


def get_in_progress_operations(tesdetay_ref):
    """
    Get all in-progress operations from TesDetay's operation_states
    Return list of tuples containing (job_card, operation_state)
    """
    tesdetay = frappe.get_doc("TesDetay", tesdetay_ref)
    in_progress_ops = []

    for op_state in tesdetay.operation_states:
        if op_state.status == "In Progress":
            try:
                job_card = frappe.get_doc("Job Card", op_state.job_card_ref)
                in_progress_ops.append((job_card, op_state))
            except frappe.DoesNotExistError:
                continue

    return in_progress_ops


def set_job_card_on_hold(job_card):
    """Set Job Card status to 'On Hold'"""
    job_card.status = "On Hold"
    for time_log in job_card.time_logs:
        if not time_log.to_time:  # Find the open time log
            time_log.to_time = frappe.utils.now()
            break
    job_card.save()


def complete_barcodes(job_card, barcodes):
    """
    Set status of specified barcodes 'Completed' and update corresponding TesDetay records
    """
    for barcode in barcodes:
        barcode.status = "Completed"

        tesdetay = frappe.get_doc("TesDetay", barcode.tesdetay_ref)
        for op_state in tesdetay.operation_states:
            if op_state.job_card_ref == job_card.name:
                op_state.status = "Completed"
                tesdetay.save()
                break

    job_card.save()


def submit_job_card(job_card):
    """Complete and Submit the job card."""
    try:
        job_card.status = "Completed"
        job_card.actual_end_date = frappe.utils.now()

        # if hasattr(job_card, "transferred_qty"):
        #     job_card.transferred_qty = job_card.for_quantity

        # job_card.save(ignore_permissions=True)

        # job_card.docstatus = 1
        job_card.save(ignore_permissions=True)
        job_card.submit()
    except Exception as e:
        frappe.log_error(f"Error submitting job card {job_card.name}: {str(e)}")
        raise


def set_barcodes_in_progress(job_card, related_barcodes):
    """
    Set status of all related barcodes to "In Progress" and update TesDetay records
    """
    for barcode in related_barcodes:
        barcode.status = "In Progress"
        tesdetay = frappe.get_doc("TesDetay", barcode.tesdetay_ref)
        for op_state in tesdetay.operation_states:
            if op_state.job_card_ref == job_card.name:
                op_state.status = "In Progress"
                tesdetay.save()
                break
    job_card.save()


def set_job_card_in_progress(job_card, employee):
    """Set Job Card status to Work In Progress and add start time."""
    job_card.status = "Work In Progress"

    if not job_card.actual_start_date:
        job_card.actual_start_date = frappe.utils.now()

    job_card.append(
        "time_logs",
        {
            "from_time": frappe.utils.now(),
            "employee": employee,
        },
    )

    job_card.save()


def complete_job(job_card, qty):
    """Complete job with proper error handling."""
    try:
        for time_log in job_card.time_logs:
            if not time_log.to_time:  # Find the open time log
                time_log.to_time = frappe.utils.now()
                time_log.completed_qty = qty
                break
        job_card.save()
    except Exception as e:
        frappe.log_error(f"Error completing job: {str(e)}")
        raise


def is_sanal_adet_group_complete(job_card, sanal_adet):
    """Check if all barcodes in sanal_adet group are completed."""
    related_barcodes = [
        b for b in job_card.custom_barcodes if int(b.sanal_adet) == int(sanal_adet)
    ]

    return all(b.status == "Completed" for b in related_barcodes)


def is_job_fully_complete(job_card):
    """Check if job card has reached its total required quantity."""
    total_completed = sum(log.completed_qty for log in job_card.time_logs)
    return total_completed >= job_card.for_quantity


def get_job_card_by_operation_and_production_item(operation, production_item):
    """Get the relevant Job Card based on the operation and production_item"""
    return frappe.get_doc(
        "Job Card", {"production_item": production_item, "operation": operation}
    )


def find_barcode_in_job_card(job_card, barcode):
    """Find specific barcode in job card's custom_barcodes table."""
    return next((b for b in job_card.custom_barcodes if b.barcode == barcode), None)


def get_related_barcodes(job_card, current_barcode):
    """Get barcodes with same model and sanal_adet."""
    return [
        b
        for b in job_card.custom_barcodes
        if b.model == current_barcode.model
        and int(b.sanal_adet) == int(current_barcode.sanal_adet)
    ]


# Open
# Work In Progress
# Material Transferred
# On Hold
# Submitted
# Cancelled
# Completed
