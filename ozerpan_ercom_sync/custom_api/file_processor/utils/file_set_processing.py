import os
import logging
from typing import Dict, List, Tuple, Any, Optional

from .file_processing import (
    FileInfo, 
    FileSet, 
    get_file_sets,
    process_file_with_error_handling
)

def get_processing_order(files_dict: Dict[str, FileInfo], file_set: str) -> List[str]:
    """
    Determine the processing order for files in a set based on the specific rules.
    
    Args:
        files_dict: Dictionary of file types to FileInfo objects
        file_set: The set identifier (e.g., 'set_a', 'set_b')
    
    Returns:
        List of file types in the order they should be processed
    """
    file_sets = get_file_sets()
    set_file_types = file_sets.get(file_set, [])
    
    # Filter to only include file types that are actually present
    available_types = [ft for ft in set_file_types if ft in files_dict]
    
    if not available_types:
        return []
    
    # Apply specific ordering rules based on the file set
    if file_set == FileSet.SET_A.value:
        # For set_a: If both appear, process MLY3 first, otherwise process whatever is available
        if "MLY3" in available_types and "CAMLISTE" in available_types:
            # Both are present, put MLY3 first
            available_types.remove("MLY3")
            return ["MLY3"] + available_types
        # Otherwise return as is (will process whatever is available)
        return available_types
        
    elif file_set == FileSet.SET_B.value:
        # For set_b: If both appear, process OPTGENEL first
        if "OPTGENEL" in available_types and "DST" in available_types:
            # Both are present, put OPTGENEL first
            available_types.remove("OPTGENEL")
            return ["OPTGENEL"] + available_types
        # Otherwise return as is
        return available_types
        
    # Default case: return available types as is
    return available_types


def process_file_set(
    manager: Any,
    order_no: str,
    files_dict: Dict[str, FileInfo],
    file_set: str,
    processed_dir: str,
    failed_dir: str
) -> Dict[str, Any]:
    """
    Process a set of files according to the specified rules.
    
    Args:
        manager: The ExcelProcessingManager instance
        order_no: The order number
        files_dict: Dictionary of file types to FileInfo objects
        file_set: The set identifier (e.g., 'set_a', 'set_b')
        processed_dir: Directory path for successfully processed files
        failed_dir: Directory path for failed files
    
    Returns:
        Dictionary with processing results
    """
    result = {
        "files_processed": [],
        "files_failed": [],
        "file_set": file_set,
    }
    
    # Get the processing order for this file set
    processing_order = get_processing_order(files_dict, file_set)
    
    if not processing_order:
        logging.info(f"No files to process for order {order_no} in set {file_set}")
        return result
    
    # Process files in the determined order
    for file_type in processing_order:
        if file_type not in files_dict:
            continue
            
        file_info = files_dict[file_type]
        processing_result = process_file_with_error_handling(
            manager, 
            file_info, 
            processed_dir, 
            failed_dir
        )
        
        if processing_result["processed"]:
            result["files_processed"].append(file_info.filename)
        else:
            result["files_failed"].append(file_info.filename)
    
    return result


def identify_file_sets(files_dict: Dict[str, FileInfo]) -> Dict[str, Dict[str, FileInfo]]:
    """
    Group files into their respective sets.
    
    Args:
        files_dict: Dictionary of file types to FileInfo objects
    
    Returns:
        Dictionary with set names as keys and dictionaries of file types to FileInfo objects as values
    """
    file_sets = get_file_sets()
    result = {}
    
    # Initialize sets with empty dictionaries
    for set_name in file_sets:
        result[set_name] = {}
    
    # Assign files to their respective sets
    for file_type, file_info in files_dict.items():
        for set_name, set_file_types in file_sets.items():
            if file_type in set_file_types:
                result[set_name][file_type] = file_info
                break
    
    # Remove empty sets
    return {k: v for k, v in result.items() if v}


def process_all_file_sets(
    manager: Any,
    order_no: str,
    files_dict: Dict[str, FileInfo],
    processed_dir: str,
    failed_dir: str
) -> Dict[str, Any]:
    """
    Process all file sets for a given order.
    
    Args:
        manager: The ExcelProcessingManager instance
        order_no: The order number
        files_dict: Dictionary of file types to FileInfo objects
        processed_dir: Directory path for successfully processed files
        failed_dir: Directory path for failed files
    
    Returns:
        Dictionary with processing results
    """
    result = {
        "files_processed": [],
        "files_failed": [],
        "file_sets_processed": [],
    }
    
    # Identify which sets are present in the files
    sets_to_process = identify_file_sets(files_dict)
    
    if not sets_to_process:
        logging.info(f"No file sets to process for order {order_no}")
        
        # Process any remaining files that don't belong to specific sets
        for file_type, file_info in files_dict.items():
            processing_result = process_file_with_error_handling(
                manager, 
                file_info, 
                processed_dir, 
                failed_dir
            )
            
            if processing_result["processed"]:
                result["files_processed"].append(file_info.filename)
            else:
                result["files_failed"].append(file_info.filename)
        
        return result
    
    # Process each file set
    for set_name, set_files in sets_to_process.items():
        set_result = process_file_set(
            manager,
            order_no,
            set_files,
            set_name,
            processed_dir,
            failed_dir
        )
        
        result["files_processed"].extend(set_result["files_processed"])
        result["files_failed"].extend(set_result["files_failed"])
        
        if set_result["files_processed"]:
            result["file_sets_processed"].append(set_name)
    
    # Process any remaining files that don't belong to specific sets
    processed_file_types = set()
    for set_files in sets_to_process.values():
        processed_file_types.update(set_files.keys())
    
    remaining_files = {
        file_type: file_info for file_type, file_info in files_dict.items()
        if file_type not in processed_file_types
    }
    
    for file_type, file_info in remaining_files.items():
        processing_result = process_file_with_error_handling(
            manager, 
            file_info, 
            processed_dir, 
            failed_dir
        )
        
        if processing_result["processed"]:
            result["files_processed"].append(file_info.filename)
        else:
            result["files_failed"].append(file_info.filename)
    
    return result