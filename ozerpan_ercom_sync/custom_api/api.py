import os
import shutil
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TextIO, TypedDict

import frappe
from frappe import _

from ozerpan_ercom_sync.custom_api.barcode_reader.constants import BarcodeStatus
from ozerpan_ercom_sync.custom_api.barcode_reader.utils.job_card import (
    complete_job_bulk,
    get_job_card,
    save_with_retry,
    submit_job_card,
    update_job_card_status,
    update_job_card_status_bulk,
)
from ozerpan_ercom_sync.custom_api.barcode_reader.utils.tesdetay import get_tesdetay
from ozerpan_ercom_sync.custom_api.file_processor.handlers.img_collector import (
    ImgCollector,
)
from ozerpan_ercom_sync.utils import bulk_update_operation_status

from .barcode_reader.exceptions import (
    BarcodeError,
    InvalidBarcodeError,
    QualityControlError,
)
from .barcode_reader.reader import BarcodeReader
from .file_processor.processor import ExcelProcessingManager
from .glass_processor.glass_processor import GlassOperationProcessor
from .glass_processor.types import GlassOperationRequest
from .services.surme_service import (
    fetch_surme_orders,
    fetch_surme_poz_details,
)

config = frappe.conf


@dataclass
class SSHConnectionInfo:
    host: str
    user: str
    password: str


@frappe.whitelist()
def process_file_background_job():
    frappe.enqueue("ozerpan_ercom_sync.custom_api.api.process_file", queue="long")


@frappe.whitelist()
def collect():
    print("\n\n-- Collecting Images -- (START)\n")
    collector = ImgCollector()
    result = collector.collect()
    return result


@frappe.whitelist()
def revert_latest_barcode_operation(
    barcode: str,
    operation: str,
    order_no: Optional[str] = None,
    poz_no: Optional[int] = None,
    sanal_adet: Optional[str] = None,
) -> Dict[str, Any]:
    print("\n\n-- Revert Barcode Operation -- (Start)")

    # Convert poz_no to int if it's provided as string
    if poz_no is not None and isinstance(poz_no, str):
        try:
            poz_no = int(poz_no)
        except ValueError:
            return {
                "status": "error",
                "message": "Invalid poz_no parameter. Must be a valid integer.",
            }

    tesdetay = get_tesdetay(
        barcode=barcode,
        operation=operation,
        order_no=order_no,
        poz_no=poz_no,
        sanal_adet=sanal_adet,
    )

    if not tesdetay:
        raise InvalidBarcodeError("Invalid Barcode")

    # Handle multiple options case
    if isinstance(tesdetay, list):
        return {
            "status": "multiple_options",
            "message": _(
                "Multiple TesDetay entries found. Please specify order_no, poz_no, and sanal_adet to select the specific one to revert."
            ),
            "operation": operation,
            "options": tesdetay,
        }

    # Handle information-only case (already completed)
    if tesdetay.get("for_information_only"):
        return {
            "status": "error",
            "message": _(
                "This TesDetay is already completed for the specified operation and cannot be reverted."
            ),
            "tesdetay_info": tesdetay,
        }

    job_card = get_job_card(
        barcode=barcode,
        operation=operation,
        production_item=f"{tesdetay.get('siparis_no')}-{tesdetay.get('poz_no')}",
    )

    current_os = None
    for os in tesdetay.get("operation_states"):
        if os.get("operation") == operation:
            current_os = os

    if not current_os or current_os.get("status") != "In Progress":
        frappe.throw("Only items with the status of 'In Progress' can be reverted.")

    tesdetay_refs = [
        b.tesdetay_ref
        for b in job_card.get("custom_barcodes")
        if b.status == "In Progress"
    ]
    job_card_refs = [job_card.name] * len(tesdetay_refs)

    bulk_update_operation_status(
        tesdetay_refs,
        job_card_refs,
        BarcodeStatus.PENDING.value,
    )

    update_job_card_status(
        job_card=job_card,
        status="On Hold",
        reason="Cancelled",
    )

    save_with_retry(job_card)
    print("\n\n-- Revert Barcode Operation -- (End)")
    return {
        "status": "success",
        "message": _("Barcode operation reverted successfully"),
        "tesdetays": tesdetay_refs,
        "operation": operation,
        "reverted_group": {
            "siparis_no": tesdetay.get("siparis_no"),
            "poz_no": tesdetay.get("poz_no"),
            "sanal_adet": tesdetay.get("sanal_adet"),
        },
    }


@frappe.whitelist()
def process_glass_operation() -> Dict[str, Any]:
    try:
        operation_data = frappe.form_dict

        if not _is_valid_operation(operation_data):
            return _create_error_response("Invalid operation type", "validation")

        glass_item = find_glasses(operation_data)
        if not glass_item:
            return _create_error_response("No matching glass item found", "validation")

        result = GlassOperationProcessor().process(operation_data)
        return _create_success_response("Operation processed successfully", result)

    except Exception as e:
        return _handle_operation_error(e)


def _is_valid_operation(operation_data: Dict) -> bool:
    return operation_data.get("operation") == "Cam"


def find_glasses(data: GlassOperationRequest) -> Optional[Dict]:
    current_glass = _get_current_glass(data["glass_name"])
    order_no = data["glass_name"].split("-")[0]
    related_glasses = _get_related_glasses(order_no, current_glass.poz_no)

    return {"current_glass": current_glass, "related_glasses": related_glasses}


def _get_current_glass(glass_name: str) -> Any:
    glass = frappe.get_doc("CamListe", glass_name)
    if not glass:
        frappe.throw(_("Glass not found"))
    return glass


def _get_related_glasses(order_no: str, poz_no: str) -> List[Dict]:
    filters = {"order_no": order_no, "poz_no": poz_no}
    return frappe.get_all("CamListe", filters=filters, fields=["*"])


###########################


@frappe.whitelist()
def update_job_cards():
    print("\n\n-- Update Job Cards -- (Start)")
    form_data = frappe.form_dict
    target_status = form_data.status
    employee = form_data.employee
    reason = form_data.reason

    missing_job_cards = []
    messages = []

    # For bulk completion, collect all valid job cards first
    if target_status == "Completed":
        valid_job_cards_for_completion = []

        for jc_name in form_data.job_cards:
            try:
                jc_doc = frappe.get_doc("Job Card", jc_name)
            except frappe.DoesNotExistError:
                missing_job_cards.append(jc_name)
                continue

            if jc_doc.status == target_status:
                messages.append(f"Job Card is already {jc_doc.status}: {jc_doc.name}")
                continue

            if jc_doc.status == "Completed":
                messages.append(f"Job Card is already completed: {jc_doc.name}")
                continue

            if jc_doc.status != "Work In Progress":
                messages.append(
                    f"Only Work In Progress Job Cards can be completed: {jc_doc.name} - {jc_doc.status}"
                )
                continue

            valid_job_cards_for_completion.append(jc_name)

        # Complete all valid job cards in bulk to avoid overlap validation
        if valid_job_cards_for_completion:
            try:
                complete_job_bulk(
                    valid_job_cards_for_completion,
                    employee,
                )

                # Submit all job cards after bulk completion
                for jc_name in valid_job_cards_for_completion:
                    jc_doc = frappe.get_doc("Job Card", jc_name)
                    submit_job_card(jc_doc)
                    messages.append(
                        f"Job Card successfully completed: {jc_name} - {target_status}"
                    )
            except Exception as e:
                frappe.log_error(f"Error in bulk job completion: {str(e)}")
                messages.append(f"Error completing job cards in bulk: {str(e)}")

    else:
        # Handle non-completion status updates - use bulk operations for Work In Progress and On Hold
        if target_status in ["Work In Progress", "On Hold"]:
            valid_job_cards_for_status_update = []

            for jc_name in form_data.job_cards:
                try:
                    jc_doc = frappe.get_doc("Job Card", jc_name)
                except frappe.DoesNotExistError:
                    missing_job_cards.append(jc_name)
                    continue

                if jc_doc.status == target_status:
                    messages.append(f"Job Card is already {jc_doc.status}: {jc_doc.name}")
                    continue

                if jc_doc.status == "Completed":
                    messages.append(f"Job Card is already completed: {jc_doc.name}")
                    continue

                valid_job_cards_for_status_update.append(jc_name)

            # Update all valid job cards in bulk to avoid overlap validation
            if valid_job_cards_for_status_update:
                try:
                    update_job_card_status_bulk(
                        job_card_names=valid_job_cards_for_status_update,
                        status=target_status,
                        employee=employee,
                        reason=reason,
                    )

                    for jc_name in valid_job_cards_for_status_update:
                        messages.append(
                            f"Job Card status changed successfully: {jc_name} - {target_status}"
                        )
                except Exception as e:
                    frappe.log_error(f"Error in bulk status update: {str(e)}")
                    messages.append(f"Error updating job cards in bulk: {str(e)}")
        else:
            # Handle other status updates individually
            for jc_name in form_data.job_cards:
                try:
                    jc_doc = frappe.get_doc("Job Card", jc_name)
                except frappe.DoesNotExistError:
                    missing_job_cards.append(jc_name)
                    continue

                if jc_doc.status == target_status:
                    messages.append(f"Job Card is already {jc_doc.status}: {jc_doc.name}")
                    continue

                if jc_doc.status == "Completed":
                    messages.append(f"Job Card is already completed: {jc_doc.name}")
                    continue

                update_job_card_status(
                    job_card=jc_doc,
                    status=target_status,
                    employee=employee,
                    reason=reason,
                )
                messages.append(
                    f"Job Card status changed successfully: {jc_doc} - {target_status}"
                )

    response = {}
    if missing_job_cards:
        response["missing_job_cards"] = missing_job_cards

    if messages:
        response["messages"] = messages

    print("-- Update Job Cards -- (End)\n\n")

    return response


###########################


@frappe.whitelist()
def get_surme_orders():
    print("\n\n\n-- Get Surme Orders -- (START)\n")
    form_data = frappe.form_dict
    orders = fetch_surme_orders(
        operation_type=form_data.operation_type,
        order_no=form_data.order_no,
    )

    print("\n-- Get Surme Orders -- (END)\n\n\n")
    return {"orders": list(orders)}


@frappe.whitelist()
def get_surme_poz_by_order_no():
    print("\n\n\n-- Get Surme Poz By Order No -- (START)\n")
    form_data = frappe.form_dict

    result = fetch_surme_poz_details(
        operation_type=form_data.operation_type,
        order_no=form_data.order_no,
    )
    print("\n-- Get Surme Poz By Order No -- (END)\n\n\n")
    return result


###########################


def move_pdf_files(to_process_dir: str) -> Dict[str, Any]:
    """
    Move PDF files from to_process directory to public/files/surme_pdf/

    Args:
        to_process_dir: The directory containing PDF files to move

    Returns:
        Dict containing status and results of the PDF moving process
    """
    print("\n\n-- Moving PDF Files -- (START)\n")

    dest_dir = config["pdf_transfer_dest_dir"]
    site_path = frappe.get_site_path()
    pdf_dest_path = site_path + dest_dir

    # Ensure destination directory exists
    os.makedirs(pdf_dest_path, exist_ok=True)

    moved_files = []
    errors = []

    try:
        # Find all PDF files in to_process directory
        for filename in os.listdir(to_process_dir):
            if filename.upper().endswith(".PDF"):
                src_path = os.path.join(to_process_dir, filename)
                dest_path = os.path.join(pdf_dest_path, filename)

                try:
                    # Move the PDF file
                    shutil.move(src_path, dest_path)
                    moved_files.append(filename)
                    print(f"Moved PDF file: {filename}")
                except Exception:
                    # Try copy and delete if move fails
                    try:
                        shutil.copy2(src_path, dest_path)
                        os.remove(src_path)
                        moved_files.append(filename)
                        print(f"Moved PDF file (via copy): {filename}")
                    except Exception as e2:
                        error_msg = f"Error moving {filename}: {str(e2)}"
                        errors.append(error_msg)
                        print(error_msg)

    except Exception as e:
        error_msg = f"Error accessing to_process directory: {str(e)}"
        errors.append(error_msg)
        print(error_msg)

    print(f"\nMoved {len(moved_files)} PDF files to {pdf_dest_path}")
    print("\n-- Moving PDF Files -- (END)\n\n")

    if errors:
        return {
            "status": "partial_success" if moved_files else "error",
            "files_moved": moved_files,
            "errors": errors,
        }
    else:
        return {
            "status": "success",
            "files_moved": moved_files,
        }


@frappe.whitelist()
def process_file() -> dict[str, Any]:
    print("\n\n-- Process File -- (START)")

    # Import utilities here to avoid circular imports
    from .file_processor.utils.file_processing import (
        FileProcessingDirectories,
        group_files_by_order,
        process_file_with_error_handling,
    )
    from .file_processor.utils.file_set_processing import (
        identify_file_sets,
        process_file_set,
    )

    # Reset database connection at the start with proper timeout handling
    _reset_db_connection_with_retry()

    # Setup directories
    dirs = FileProcessingDirectories()
    dirs.ensure_directories_exist()

    # Group files by order
    grouped_files = group_files_by_order(dirs.to_process)

    # For failed files that couldn't be parsed
    for filename in os.listdir(dirs.to_process):
        # Create a list of all filenames from grouped_files
        processed_filenames = [
            f.filename for f_dict in grouped_files.values() for f in f_dict.values()
        ]

        if filename.upper().endswith(".XLS") and filename not in processed_filenames:
            # Move improperly named files to FAILED folder
            failed_path = os.path.join(dirs.failed, filename)
            src_path = os.path.join(dirs.to_process, filename)
            try:
                os.rename(src_path, failed_path)
                print(f"Moved improperly named file {filename} to failed folder")
            except Exception as e:
                print(f"Error moving file {filename}: {str(e)}")

    # Initialize the Excel processing manager
    manager = ExcelProcessingManager()

    # Initialize results
    processing_results = {
        "successful_orders": [],
        "partial_orders": [],
        "failed_orders": [],
        "details": {},
    }

    # Process each order independently
    for order_no, files_dict in grouped_files.items():
        print(f"\n Processing Order: {order_no}")

        # Initialize order results
        if order_no not in processing_results["details"]:
            processing_results["details"][order_no] = {
                "files_processed": [],
                "files_failed": [],
                "file_sets_processed": [],
            }

        try:
            # Identify which sets are present in the files
            sets_to_process = identify_file_sets(files_dict)

            # Process each file set independently
            for set_name, set_files in sets_to_process.items():
                try:
                    print(f"Processing file set {set_name} for order {order_no}")
                    # Ensure database connection is fresh before processing
                    _reset_db_connection_with_retry()

                    set_result = process_file_set(
                        manager,
                        order_no,
                        set_files,
                        set_name,
                        dirs.processed,
                        dirs.failed,
                    )

                    # Commit changes immediately after successful processing
                    _commit_with_retry()

                    # Update order results with this set's results
                    processing_results["details"][order_no]["files_processed"].extend(
                        set_result["files_processed"]
                    )
                    processing_results["details"][order_no]["files_failed"].extend(
                        set_result["files_failed"]
                    )

                    if set_result["files_processed"]:
                        processing_results["details"][order_no][
                            "file_sets_processed"
                        ].append(set_name)

                    # Continue processing other sets even if this one had failures
                except Exception as set_error:
                    print(
                        f"Error processing file set {set_name} for order {order_no}: {str(set_error)}"
                    )
                    # Continue with other sets even if this one fails

            # Process any remaining files that don't belong to specific sets
            processed_file_types = set()
            for set_files in sets_to_process.values():
                processed_file_types.update(set_files.keys())

            remaining_files = {
                file_type: file_info
                for file_type, file_info in files_dict.items()
                if file_type not in processed_file_types
            }

            # Process each remaining file independently
            for file_type, file_info in remaining_files.items():
                try:
                    print(
                        f"Processing independent file {file_info.filename} for order {order_no}"
                    )
                    # Ensure database connection is fresh before processing
                    _reset_db_connection_with_retry()

                    processing_result = process_file_with_error_handling(
                        manager, file_info, dirs.processed, dirs.failed
                    )

                    # Commit changes immediately after processing
                    _commit_with_retry()

                    if processing_result["processed"]:
                        processing_results["details"][order_no]["files_processed"].append(
                            file_info.filename
                        )
                    else:
                        processing_results["details"][order_no]["files_failed"].append(
                            file_info.filename
                        )

                except Exception as file_error:
                    print(
                        f"Error processing file {file_info.filename}: {str(file_error)}"
                    )
                    processing_results["details"][order_no]["files_failed"].append(
                        file_info.filename
                    )
                    # Continue with other files even if this one fails

            # Categorize the order based on final results
            order_results = processing_results["details"][order_no]
            if not order_results["files_failed"] and order_results["files_processed"]:
                if order_no not in processing_results["successful_orders"]:
                    processing_results["successful_orders"].append(order_no)
            elif order_results["files_processed"] and order_results["files_failed"]:
                if order_no not in processing_results["partial_orders"]:
                    processing_results["partial_orders"].append(order_no)
            else:
                if order_no not in processing_results["failed_orders"]:
                    processing_results["failed_orders"].append(order_no)

        except Exception as order_error:
            print(f"Error processing order {order_no}: {str(order_error)}")
            # Ensure order is categorized even if an exception occurs
            if processing_results["details"][order_no]["files_processed"]:
                if order_no not in processing_results["partial_orders"]:
                    processing_results["partial_orders"].append(order_no)
            else:
                if order_no not in processing_results["failed_orders"]:
                    processing_results["failed_orders"].append(order_no)

    print("\n\n-- Process File -- (END)")

    # Close database connection to avoid connection leaks
    _commit_with_retry()

    pdf_move_result = move_pdf_files(dirs.to_process)

    img_collector = ImgCollector()
    img_collector_result = img_collector.collect()

    return {
        "file_processing_result": processing_results,
        "img_collector_result": img_collector_result,
        "pdf_move_result": pdf_move_result,
    }


def _reset_db_connection_with_retry(max_retries: int = 3, retry_delay: float = 1.0):
    """Reset database connection with retry mechanism for lock timeout issues"""
    import time

    for attempt in range(max_retries):
        try:
            # Close any existing connections
            frappe.db.close()
            # Reconnect with fresh connection
            frappe.connect()
            frappe.db.commit()
            return
        except Exception as e:
            error_msg = str(e).lower()
            if "lock wait timeout" in error_msg or "deadlock" in error_msg:
                if attempt < max_retries - 1:
                    print(
                        f"Database lock detected, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    print(
                        f"Failed to reset database connection after {max_retries} attempts: {str(e)}"
                    )
                    raise
            else:
                print(f"Database connection reset failed: {str(e)}")
                raise


def _commit_with_retry(max_retries: int = 3, retry_delay: float = 1.0):
    """Commit database transaction with retry mechanism for lock timeout issues"""
    import time

    for attempt in range(max_retries):
        try:
            frappe.db.commit()
            return
        except Exception as e:
            error_msg = str(e).lower()
            if "lock wait timeout" in error_msg or "deadlock" in error_msg:
                if attempt < max_retries - 1:
                    print(
                        f"Database lock detected during commit, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})"
                    )
                    try:
                        frappe.db.rollback()
                    except:
                        pass
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    print(f"Failed to commit after {max_retries} attempts: {str(e)}")
                    try:
                        frappe.db.rollback()
                    except:
                        pass
                    raise
            else:
                print(f"Database commit failed: {str(e)}")
                raise


def _handle_database_lock_error(error: Exception, context: str = "") -> bool:
    """Check if error is a database lock issue and handle appropriately"""
    error_msg = str(error).lower()
    if any(
        keyword in error_msg
        for keyword in ["lock wait timeout", "deadlock", "try restarting transaction"]
    ):
        print(f"Database lock detected in {context}: {str(error)}")
        try:
            frappe.db.rollback()
        except:
            pass
        return True
    return False


def process_file_set(
    manager: ExcelProcessingManager,
    order_no: str,
    set_name: str,
    files_dict: dict[str, any],
    file_types: list[str],
    to_process: str,
    processed: str,
    failed: str,
) -> dict[str, any]:
    """
    Process a set of files that belong together.

    This function has been deprecated. Use the new utility modules instead:
    - from .file_processor.utils.file_set_processing import process_file_set

    For maintaining backward compatibility, this function remains but delegates to the new implementation.
    """
    from .file_processor.utils.file_processing import FileInfo
    from .file_processor.utils.file_set_processing import (
        process_file_set as new_process_file_set,
    )

    # Convert old format to new format
    file_info_dict = {}
    for file_type, file_data in files_dict.items():
        if file_type in file_types:
            file_info_dict[file_type] = FileInfo(
                filename=file_data["filename"],
                path=file_data["path"],
                order_no=order_no,
                file_type=file_type,
            )

    # Call the new implementation
    result = new_process_file_set(
        manager, order_no, file_info_dict, set_name, processed, failed
    )

    # Convert new format to old format
    return {"processed": result["files_processed"], "failed": result["files_failed"]}


@frappe.whitelist()
def process_excel_file(file_url: str) -> Dict[str, Any]:
    """
    Method for single file processing through Frappe's file upload.
    Processes the file independently and updates related sales orders immediately.
    """
    if not file_url:
        return _create_error_response("No file URL provided", "Validation")

    try:
        # Reset database connection at the start
        frappe.db.commit()

        # Get file details
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        site_path = frappe.get_site_path()
        full_path = site_path + file_url

        # Log processing start
        print(f"\n\n-- Processing Single File: {file_doc.file_name} -- (START)")

        # Process the file
        manager = ExcelProcessingManager()
        result = manager.process_file(file_url=full_path, filename=file_doc.file_name)

        # Log processing completion
        processing_status = "Success" if result.get("status") == "success" else "Failed"
        print(f"-- Processing Single File: {file_doc.file_name} -- ({processing_status})")

        # Move file to appropriate directory based on result
        if file_doc.is_private and result.get("status") == "success":
            # Move to processed directory logic could be added here
            pass

        # Commit any pending changes and close connection
        frappe.db.commit()

        return result

    except frappe.DoesNotExistError:
        error_msg = f"File not found: {file_url}"
        frappe.log_error(error_msg, "Excel Processing Error")
        return _create_error_response(error_msg, "NotFound")

    except (IOError, OSError) as e:
        error_msg = f"File system error: {str(e)}"
        frappe.log_error(error_msg, "Excel Processing Error")
        return _create_error_response(error_msg, "FileSystemError")

    except Exception as e:
        return _handle_file_processing_error(e)


class BarcodeRequest(TypedDict):
    barcode: str
    employee: str
    operation: str
    quality_data: Optional[Dict[str, Any]]
    order_no: Optional[str]
    poz_no: Optional[int]


@frappe.whitelist()
def read_barcode(
    barcode,
    employee,
    operation,
    quality_data=None,
    order_no=None,
    poz_no=None,
    sanal_adet=None,
):
    try:
        # Convert poz_no to int if it's provided as string
        if poz_no is not None and isinstance(poz_no, str):
            try:
                poz_no = int(poz_no)
            except ValueError:
                return _create_error_response(
                    "Invalid poz_no parameter. Must be a valid integer.", "validation"
                )

        reader = BarcodeReader()
        result = reader.read_barcode(
            barcode=barcode,
            employee=employee,
            operation=operation,
            quality_data=quality_data,
            order_no=order_no,
            poz_no=poz_no,
            sanal_adet=sanal_adet,
        )
        return result
    except (QualityControlError, InvalidBarcodeError, BarcodeError) as e:
        frappe.db.rollback()
        return _handle_barcode_error(e)
    except Exception as e:
        frappe.db.rollback()
        return _handle_system_error(e)


def _create_error_response(message: str, error_type: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "message": _(message),
        "error_type": error_type,
    }


def _create_success_response(message: str, data: Any = None) -> Dict[str, Any]:
    response = {
        "status": "success",
        "message": _(message),
    }
    if data:
        response["data"] = data
    return response


def _handle_operation_error(error: Exception) -> Dict[str, Any]:
    """Handle errors from glass operation processing"""
    frappe.log_error(
        f"Error processing glass operation: {str(error)}", "Glass Operation Error"
    )
    return {"status": "error", "message": str(error), "error_type": "system"}


def _handle_file_processing_error(error: Exception) -> Dict[str, Any]:
    """Handle errors from file processing with enhanced details"""
    import traceback

    error_type = type(error).__name__
    error_trace = traceback.format_exc()

    # Check if it's a database lock error
    is_lock_error = _handle_database_lock_error(error, "file processing")

    # Close any hanging database connections with retry for lock errors
    if is_lock_error:
        try:
            _reset_db_connection_with_retry()
        except:
            pass
    else:
        try:
            frappe.db.commit()
        except:
            pass

    # Truncate error message if too long to prevent log truncation issues
    error_message = str(error)
    if len(error_message) > 500:  # Reasonable limit to prevent truncation
        error_message = error_message[:500] + "... (truncated)"

    # Log the detailed error with traceback
    log_title = f"File Processing Error: {error_type}"
    if len(log_title) > 100:
        log_title = log_title[:100] + "..."

    frappe.log_error(
        message=f"Error in file processing: {error_message}\n\nTraceback:\n{error_trace}",
        title=log_title,
    )

    # Make sure to close the connection even on error
    try:
        if is_lock_error:
            _commit_with_retry()
        else:
            frappe.db.commit()
    except:
        pass

    # Return a detailed error response with type information
    return {
        "status": "error",
        "message": _("Error processing file: {0}").format(error_message),
        "error_type": "database_lock" if is_lock_error else "system",
        "error_details": {
            "type": error_type,
            "is_file_error": isinstance(error, (IOError, OSError)),
            "is_lock_error": is_lock_error,
        },
    }


def _handle_barcode_error(error: Exception) -> Dict[str, Any]:
    """Handle specific barcode-related errors"""
    if isinstance(error, QualityControlError):
        return {
            "status": "error",
            "message": str(error.message),
            "error_type": error.error_type,
            **(error.data or {}),
        }
    elif isinstance(error, InvalidBarcodeError):
        return {"status": "error", "message": str(error), "error_type": "invalid_barcode"}
    elif isinstance(error, BarcodeError):
        return {
            "status": "error",
            "message": str(error),
            "error_type": "barcode_operation",
        }
    return _handle_system_error(error)


def _handle_system_error(error: Exception) -> Dict[str, Any]:
    """Handle general system errors"""
    frappe.log_error(f"Error reading barcode: {str(error)}", "Barcode Reader Error")
    return {"status": "error", "message": str(error), "error_type": "system"}


def create_error_log_file(
    file_path: str,
    error_message: str,
    details: Dict = None,
    include_system_info: bool = True,
) -> str:
    """
    Create a log file with detailed error information for a failed file

    Args:
        file_path: Path to the file that failed processing
        error_message: Main error message describing the failure
        details: Dictionary of additional error details
        include_system_info: Whether to include system information in the log

    Returns:
        Path to the created log file
    """
    log_file_path = f"{file_path}.log"

    # Clean up nested error messages to prevent truncation issues
    clean_error_message = _clean_error_message(error_message)

    with open(log_file_path, "w", encoding="utf-8") as log_file:
        _write_line(
            file=log_file,
            message=_("ERROR REPORT: {0}").format(os.path.basename(file_path)),
            prefix="!!",
            timestamp=True,
        )

        # Error information section
        _write_line(
            file=log_file,
            message=_("Error message: {0}").format(clean_error_message),
            before=1,
            prefix="ERROR:",
        )

        if details:
            _write_line(
                file=log_file, message=_("Additional details:"), prefix="INFO:", before=1
            )
            for key, value in details.items():
                if key == "missing_items":
                    _write_line(
                        file=log_file,
                        message=_("Missing items:"),
                        before=1,
                        prefix="MISSING:",
                    )
                    if isinstance(value, list):
                        # Handle list of missing item dictionaries
                        for item in value:
                            if isinstance(item, dict):
                                item_type = item.get("type", "Unknown")
                                stock_code = item.get("stock_code", "Unknown")
                                order_no = item.get("order_no", "Unknown")
                                poz_no = item.get("poz_no", "Unknown")
                                msg = _("- {0} | Order: {1}, Poz: {2}").format(
                                    stock_code, order_no, poz_no
                                )
                                _write_line(
                                    file=log_file,
                                    message=msg,
                                    prefix="ITEM:",
                                    timestamp=False,
                                )
                            else:
                                _write_line(
                                    file=log_file,
                                    message=f"- {item}",
                                    prefix="ITEM:",
                                    timestamp=False,
                                )
                    elif isinstance(value, dict):
                        # Handle dictionary of item types to items
                        for item_type, items in value.items():
                            _write_line(
                                file=log_file,
                                message=f"- {item_type}",
                                prefix="TYPE:",
                                timestamp=False,
                            )
                            if isinstance(items, list):
                                for item in items:
                                    _write_line(
                                        file=log_file,
                                        message=f" * {item}",
                                        prefix="ITEM:",
                                        timestamp=False,
                                    )
                            else:
                                _write_line(
                                    file=log_file,
                                    message=f" * {item}",
                                    prefix="ITEM:",
                                    timestamp=False,
                                )
                    else:
                        _write_line(
                            file=log_file,
                            message=f"- {value}",
                            prefix="DATA:",
                            timestamp=False,
                        )
                else:
                    _write_line(
                        file=log_file,
                        message=f"- {key}: {value}",
                        prefix="INFO:",
                        timestamp=False,
                    )

        # Add system information if requested
        if include_system_info:
            import platform
            import socket

            _write_line(
                file=log_file,
                message=_("System Information:"),
                before=1,
                prefix="SYS:",
                timestamp=True,
            )
            _write_line(
                file=log_file,
                message=f"Hostname: {socket.gethostname()}",
                prefix="SYS:",
                timestamp=False,
            )
            _write_line(
                file=log_file,
                message=f"Platform: {platform.platform()}",
                prefix="SYS:",
                timestamp=False,
            )
            _write_line(
                file=log_file,
                message=f"Python: {platform.python_version()}",
                prefix="SYS:",
                timestamp=False,
            )
            _write_line(
                file=log_file,
                message=f"Frappe Version: {frappe.__version__}",
                prefix="SYS:",
                timestamp=False,
            )

    return log_file_path


def _clean_error_message(error_message: str) -> str:
    """Clean up nested error messages to prevent truncation and improve readability"""
    if not error_message:
        return error_message

    # Handle nested error messages with "will get truncated" pattern
    if "will get truncated" in error_message:
        # Extract the core error message before truncation warnings
        parts = error_message.split("will get truncated")
        if parts:
            core_message = parts[0].strip()
            # Remove trailing punctuation that might be incomplete
            core_message = core_message.rstrip(", )")
            return core_message

    # Handle deeply nested error messages
    if error_message.count("Error processing") > 2:
        # Extract the innermost error message
        lines = error_message.split("Error processing")
        if len(lines) > 1:
            # Take the last meaningful part
            innermost = lines[-1]
            if ":" in innermost:
                innermost = innermost.split(":", 1)[-1].strip()
            return f"Error processing: {innermost}"

    # Handle document modification errors specifically
    if (
        "Döküman siz açtıktan sonra değiştirildi" in error_message
        or "document was modified" in error_message.lower()
    ):
        return "Document was modified by another process. Please refresh and try again."

    # Limit message length to prevent truncation
    if len(error_message) > 1000:
        return error_message[:1000] + "... (message truncated for readability)"

    return error_message


def _write_line(
    file: TextIO,
    message: str,
    before: int = 0,
    after: int = 0,
    prefix: str = "",
    timestamp: bool = True,
):
    """
    Write a line to the error log file with enhanced formatting.

    Args:
        file: The file object to write to
        message: The message to write
        before: Number of blank lines to insert before the message
        after: Number of blank lines to insert after the message
        prefix: Optional prefix to add to the message (e.g., "ERROR:", "INFO:")
        timestamp: Whether to include a timestamp
    """
    file.write("\n" * before)

    # Add timestamp if requested
    if timestamp:
        from datetime import datetime

        timestamp_str = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        file.write(timestamp_str)

    # Add prefix if provided
    if prefix:
        file.write(f"{prefix} ")

    # Write the actual message
    file.write(message)
    file.write("\n" * (after + 1))
