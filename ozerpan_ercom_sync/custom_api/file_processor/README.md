# File Processing System

This directory contains the file processing system for the Ozerpan Ercom Sync application. The system handles the processing of various Excel files for order processing.

## Overview

The file processing system reads Excel files from a designated directory, processes them according to specific rules, and moves them to either a "processed" or "failed" directory based on the outcome.

### Directory Structure

```
/files/xls_import/
  ├── to_process/    # Files waiting to be processed
  ├── processed/     # Successfully processed files
  └── failed/        # Files that failed processing (with error logs)
```

## File Sets and Processing Rules

Files are grouped into "sets" based on their type, and each set has specific processing rules:

### Set A (MLY3, CAMLISTE)
- If one of them appears, process it anyway
- If both appear, process MLY3 first

### Set B (OPTGENEL, DST)
- If both appear, process OPTGENEL first

## Architecture

The file processing system follows a modular design:

- `processor.py`: Contains the `ExcelProcessingManager` class that manages file processing
- `utils/file_processing.py`: Utilities for basic file operations
- `utils/file_set_processing.py`: Utilities for processing file sets according to rules
- `handlers/`: Directory containing concrete processor implementations
- `models/`: Data models used in file processing

## Key Components

### ExcelProcessingManager

The manager class that orchestrates the file processing. It registers processor classes and routes files to the appropriate processor based on file type.

### FileInfo

A dataclass that contains information about a file to be processed:
- `filename`: Name of the file
- `path`: Path to the file
- `order_no`: Order number extracted from the filename
- `file_type`: Type of file extracted from the filename

### FileProcessingDirectories

A class that manages the directories used for file processing:
- `base_dir`: Base directory for file processing
- `to_process`: Directory for files waiting to be processed
- `processed`: Directory for successfully processed files
- `failed`: Directory for failed files

## Usage

### Processing Files

The main entry point for file processing is the `process_file()` function in `api.py`. This function:
1. Scans the `to_process` directory for files
2. Groups files by order number
3. For each order, processes files according to the set rules
4. Moves files to the appropriate directory based on the processing result

### Adding New File Types

To add support for a new file type:

1. Add the file type to the `ExcelFileType` enum in `constants.py`
2. Create a new processor class that implements the `ExcelProcessorInterface`
3. Register the processor in the `_register_processors()` method of `ExcelProcessingManager`

## Example

For an order with files `12345_MLY3.xls` and `12345_CAMLISTE.xls`:

1. Files are grouped by order number (`12345`)
2. System identifies that both files belong to Set A
3. MLY3 file is processed first according to Set A rules
4. CAMLISTE file is processed after MLY3
5. Files are moved to the appropriate directory based on processing results

## Error Handling

When a file fails processing:
1. An error log is created with details about the failure
2. Both the file and error log are moved to the `failed` directory
3. Processing continues with the next file