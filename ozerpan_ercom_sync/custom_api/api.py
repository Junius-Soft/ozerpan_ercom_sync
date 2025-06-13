import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TextIO, TypedDict

import frappe
from frappe import _

from ozerpan_ercom_sync.custom_api.barcode_reader.constants import BarcodeStatus
from ozerpan_ercom_sync.custom_api.barcode_reader.utils.job_card import (
    complete_job,
    get_job_card,
    save_with_retry,
    submit_job_card,
    update_job_card_status,
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
def collect():
    print("\n\n-- Collecting Images -- (START)\n")
    collector = ImgCollector()
    result = collector.collect()
    return result


@frappe.whitelist()
def revert_latest_barcode_operation(barcode: str, operation: str) -> None:
    print("\n\n-- Revert Barcode Operation -- (Start)")

    tesdetay = get_tesdetay(barcode=barcode, operation=operation)
    if not tesdetay:
        raise InvalidBarcodeError("Invalid Barcode")

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
        "tesdetays": tesdetay_refs,
        "operation": operation,
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

        if target_status == "Completed":
            if jc_doc.status != "Work In Progress":
                messages.append(
                    f"Only Work In Progress Job Cards can be completed: {jc_doc.name} - {jc_doc.status}"
                )
                continue
            complete_job(jc_doc, jc_doc.for_quantity)
            submit_job_card(jc_doc)
            messages.append(
                f"Job Card successfully completed: {jc_doc} - {target_status}"
            )

        elif target_status in ["Work In Progress", "On Hold"]:
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

    # Reset database connection at the start
    frappe.db.commit()

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
                    frappe.db.commit()

                    set_result = process_file_set(
                        manager,
                        order_no,
                        set_files,
                        set_name,
                        dirs.processed,
                        dirs.failed,
                    )

                    # Commit changes immediately after successful processing
                    frappe.db.commit()

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
                    frappe.db.commit()

                    processing_result = process_file_with_error_handling(
                        manager, file_info, dirs.processed, dirs.failed
                    )

                    # Commit changes immediately after processing
                    frappe.db.commit()

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
    frappe.db.commit()

    img_collector = ImgCollector()
    img_collector_result = img_collector.collect()

    return {
        "file_processing_result": processing_results,
        "img_collector_result": img_collector_result,
    }


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


@frappe.whitelist()
def read_barcode(
    barcode: str,
    employee: str,
    operation: str,
    quality_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    try:
        reader = BarcodeReader()
        result = reader.read_barcode(
            barcode=barcode,
            employee=employee,
            operation=operation,
            quality_data=quality_data,
        )
        return result
    except (QualityControlError, InvalidBarcodeError, BarcodeError) as e:
        return _handle_barcode_error(e)
    except Exception as e:
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

    # Close any hanging database connections
    try:
        frappe.db.commit()
    except:
        pass

    # Log the detailed error with traceback
    frappe.log_error(
        message=f"Error in file processing: {str(error)}\n\nTraceback:\n{error_trace}",
        title=f"File Processing Error: {error_type}",
    )

    # Make sure to close the connection even on error
    try:
        frappe.db.commit()
    except:
        pass

    # Return a detailed error response with type information
    return {
        "status": "error",
        "message": _("Error processing file: {0}").format(str(error)),
        "error_type": "system",
        "error_details": {
            "type": error_type,
            "is_file_error": isinstance(error, (IOError, OSError)),
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

    with open(log_file_path, "w") as log_file:
        _write_line(
            file=log_file,
            message=_("ERROR REPORT: {0}").format(os.path.basename(file_path)),
            prefix="!!",
            timestamp=True,
        )

        # Error information section
        _write_line(
            file=log_file,
            message=_("Error message: {0}").format(error_message),
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
