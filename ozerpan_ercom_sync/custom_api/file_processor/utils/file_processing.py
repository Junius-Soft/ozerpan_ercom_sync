import logging
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe import _

# Configure logging for connection issues
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

config = frappe.conf

# Maximum number of connection errors before giving up
MAX_DB_RETRIES = 3


# Constants
class FileSet(Enum):
    SET_A = "set_a"
    SET_B = "set_b"


@dataclass
class FileInfo:
    """Information about a file to be processed"""

    filename: str
    path: str
    order_no: str
    file_type: str


class FileProcessingDirectories:
    """Manages the directories for file processing"""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            self.base_dir = config["file_upload_base_dir"]
        else:
            self.base_dir = base_dir
        self.to_process = os.path.join(self.base_dir, config["xls_to_process_dir"])
        self.processed = os.path.join(self.base_dir, config["xls_success_dir"])
        self.failed = os.path.join(self.base_dir, config["xls_failed_dir"])

    def ensure_directories_exist(self) -> None:
        """Ensure all required directories exist"""
        for dir_path in [self.to_process, self.processed, self.failed]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)


def get_order_and_type(filename: str) -> Tuple[str, str]:
    """Extract order number and file type from filename"""
    name = filename.upper().replace(".XLS", "")
    parts = name.split("_")
    if len(parts) < 2:
        raise ValueError(f"Invalid filename format: {filename}")
    return parts[0], parts[1]


def group_files_by_order(directory_path: str) -> Dict[str, Dict[str, FileInfo]]:
    """
    Group files in the directory by their order number.
    Returns a dictionary with order numbers as keys and another dictionary
    with file types as keys and file info as values.
    """
    # Import frappe here to avoid circular imports
    import frappe

    # Ensure database connection is fresh
    try:
        frappe.db.commit()
    except Exception as e:
        logging.warning(f"Database commit warning in group_files_by_order: {str(e)}")

    grouped = {}

    for filename in os.listdir(directory_path):
        if filename.upper().endswith(".XLS"):
            file_path = os.path.join(directory_path, filename)
            try:
                order_no, file_type = get_order_and_type(filename)

                if order_no not in grouped:
                    grouped[order_no] = {}

                grouped[order_no][file_type] = FileInfo(
                    filename=filename,
                    path=file_path,
                    order_no=order_no,
                    file_type=file_type,
                )
            except Exception as e:
                # Log the error but don't stop processing
                logging.error(f"Error parsing file {filename}: {str(e)}")

    return grouped


def move_file(
    file_info: FileInfo,
    destination_dir: str,
    create_log: bool = False,
    error_message: str = None,
    error_details: Dict[str, Any] = None,
) -> Optional[str]:
    """
    Move a file to the destination directory.
    Optionally create an error log file with the given message and details.
    Returns the path to the log file if created.

    Note: This function handles file system operations but doesn't affect database state.
    """
    dest_file_path = os.path.join(destination_dir, file_info.filename)

    # Move the file
    try:
        shutil.move(file_info.path, dest_file_path)
    except Exception as e:
        logging.error(f"Error moving file {file_info.filename}: {str(e)}")
        # Try copy and delete if move fails
        try:
            shutil.copy2(file_info.path, dest_file_path)
            os.remove(file_info.path)
        except Exception as e2:
            logging.error(f"Error copying file {file_info.filename}: {str(e2)}")
            return None

    # Create log file if requested
    if create_log and error_message:
        from ozerpan_ercom_sync.custom_api.api import create_error_log_file

        log_path = create_error_log_file(
            file_info.path, error_message, error_details or {}
        )

        # Move the log file to the destination directory
        log_dest_path = os.path.join(destination_dir, f"{file_info.filename}.log")
        try:
            shutil.move(log_path, log_dest_path)
            return log_dest_path
        except Exception as e:
            logging.error(f"Error moving log file for {file_info.filename}: {str(e)}")
            return None

    return None


def get_file_sets() -> Dict[str, List[str]]:
    """Return the defined file sets"""
    return {
        FileSet.SET_A.value: ["MLY3", "CAMLISTE", "FIYAT"],
        FileSet.SET_B.value: ["OPTGENEL", "DST"],
    }


def process_file_with_error_handling(
    manager, file_info: FileInfo, processed_dir: str, failed_dir: str
) -> Dict[str, Any]:
    """
    Process a file with error handling.
    Returns a dictionary with the result status and any error details.
    """
    # Ensure database connection is fresh before processing
    import frappe

    try:
        frappe.db.commit()
    except Exception as e:
        logging.error(
            f"Database connection error before processing {file_info.filename}: {str(e)}"
        )

    result = {
        "status": "error",
        "processed": False,
        "error_details": None,
        "error_message": None,
    }

    try:
        processing_result = manager.process_file(
            file_url=file_info.path, filename=file_info.filename
        )

        # Commit after successful processing
        try:
            frappe.db.commit()
        except Exception as e:
            logging.warning(
                f"Database commit warning after processing {file_info.filename}: {str(e)}"
            )

        if processing_result["status"] == "success":
            # Move to processed directory
            move_file(file_info, processed_dir)
            result["status"] = "success"
            result["processed"] = True

            # Final commit for success case
            try:
                frappe.db.commit()
            except Exception as e:
                logging.warning(
                    f"Database commit warning after success {file_info.filename}: {str(e)}"
                )

            return result
        else:
            # Processing failed
            error_details = {
                "error_type": processing_result.get("error_type", "unknown"),
                "order_no": file_info.order_no,
                "file_type": file_info.file_type,
                "file_type_name": processing_result.get("file_type", file_info.file_type),
            }

            # Add missing items to error details if present
            if (
                processing_result.get("error_type") == "missing_items"
                and "missing_items" in processing_result
            ):
                error_details["missing_items"] = processing_result["missing_items"]
                error_message = _("Processing failed due to missing required items")
            else:
                error_message = processing_result.get("message", "Unknown error")

            # Move to failed directory and create log
            move_file(
                file_info,
                failed_dir,
                create_log=True,
                error_message=error_message,
                error_details=error_details,
            )

            # Commit after failure case is handled
            try:
                frappe.db.commit()
            except Exception as e:
                logging.warning(
                    f"Database commit warning after failure {file_info.filename}: {str(e)}"
                )

            result["error_details"] = error_details
            result["error_message"] = error_message
            return result

    except Exception as e:
        # Exception occurred during processing
        error_details = {
            "error_type": "exception",
            "order_no": file_info.order_no,
            "file_type": file_info.file_type,
            "exception_type": type(e).__name__,
        }

        # Try to recover database connection on error
        try:
            frappe.db.rollback()
        except Exception as db_error:
            logging.error(
                f"Database rollback error after exception for {file_info.filename}: {str(db_error)}"
            )

        # Move to failed directory and create log
        move_file(
            file_info,
            failed_dir,
            create_log=True,
            error_message=str(e),
            error_details=error_details,
        )

        # Final commit for exception case
        try:
            frappe.db.commit()
        except Exception as db_error:
            logging.error(
                f"Database commit error after exception for {file_info.filename}: {str(db_error)}"
            )

        result["error_details"] = error_details
        result["error_message"] = str(e)
        logging.error(f"Error processing file {file_info.filename}: {str(e)}")
        return result
