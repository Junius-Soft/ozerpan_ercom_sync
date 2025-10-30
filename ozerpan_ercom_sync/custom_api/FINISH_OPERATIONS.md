# Finish With Previous Operations Documentation

## Overview

The `finish_with_previous_operations` function automatically completes all unfinished operations before proceeding with a quality control operation. This function is designed to handle cases where a quality inspection cannot proceed due to incomplete previous manufacturing operations.

## Function Signature

```python
def finish_with_previous_operations(
    barcode,
    employee,
    operation,
    quality_data=None,
    order_no=None,
    poz_no=None,
    sanal_adet=None,
    tesdetay_name=None,
):
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `barcode` | string | Yes | The barcode identifier for the item being processed |
| `employee` | string | Yes | Employee ID performing the operation |
| `operation` | string | Yes | Operation type (must be 'Kalite' for quality control) |
| `quality_data` | dict | No | Quality inspection data including criteria and notes |
| `order_no` | string | No | Order number for the item |
| `poz_no` | int/string | No | Position number in the order |
| `sanal_adet` | int | No | Virtual quantity identifier |
| `tesdetay_name` | string | No | TesDetay document name |

## Return Values

The function returns a dictionary with the following possible structures:

### Success Response
```json
{
    "status": "completed",
    "message": "Quality check completed",
    "completed_previous_operations": [
        {
            "job_card": "JOB-001",
            "operation": "Kaynak",
            "completed_barcodes": 5
        }
    ]
}
```

### Error Response
```json
{
    "status": "error",
    "error_type": "validation|system_error|quality_operation",
    "message": "Error description"
}
```

## How It Works

### 1. Initial Validation
- Validates that the operation parameter is 'Kalite' (quality control)
- Returns validation error if operation type is invalid

### 2. First Barcode Read Attempt
- Calls `read_barcode()` to attempt the quality operation
- If successful (no unfinished operations), returns the result immediately
- If fails with "unfinished operations" error, proceeds to completion logic

### 3. Automatic Operation Completion
For each unfinished operation found:

1. **Job Card Retrieval**: Gets the Job Card document
2. **Status Validation**: Skips if job card is missing or already submitted
3. **Barcode Processing**: Finds all pending/in-progress barcodes in the job card
4. **Status Update**: Updates all barcodes to "Completed" status using bulk operations
5. **Job Completion**: Marks the job as complete and updates job card status
6. **Submission**: Submits the job card if all operations are complete, otherwise sets to "On Hold"

### 4. Retry Quality Operation
- After completing all unfinished operations, attempts the quality operation again
- Includes completion information in the response
- Handles any failures during the retry

## Implementation Details

### Database Operations
- Uses `bulk_update_operation_status()` for efficient barcode status updates
- Commits changes after completing all operations
- Includes rollback on errors to maintain data consistency

### Job Card Status Management
- Calls `complete_job()` to mark job completion
- Uses `is_job_fully_complete()` to determine if job card should be submitted
- Updates job card status to "On Hold" for partial completions

### Error Handling
- Gracefully handles missing job cards
- Skips already submitted job cards
- Continues processing even if individual operations fail
- Provides detailed error messages and logs

## Usage Examples

### Basic Quality Control with Auto-Completion
```python
result = finish_with_previous_operations(
    barcode="ABC123456",
    employee="EMP001",
    operation="Kalite",
    quality_data={
        "overall_notes": "Standard quality check",
        "criteria": [
            {"name": "Dimensions", "passed": True},
            {"name": "Surface Quality", "passed": True}
        ]
    }
)
```

### With Order Information
```python
result = finish_with_previous_operations(
    barcode="ABC123456",
    employee="EMP001", 
    operation="Kalite",
    order_no="ORD-2024-001",
    poz_no=1,
    sanal_adet=5
)
```

## Error Scenarios

### 1. Invalid Operation Type
```python
# Returns validation error
result = finish_with_previous_operations(
    barcode="ABC123456",
    employee="EMP001",
    operation="InvalidOp"  # Must be 'Kalite'
)
```

### 2. Missing Job Cards
- Function logs warning and continues with other operations
- Does not fail the entire process

### 3. Already Submitted Job Cards
- Function logs info message and skips processing
- Continues with remaining operations

### 4. Quality Operation Failure After Completion
- Returns error but indicates that previous operations were completed successfully
- Allows manual retry of quality operation

## Logging and Debugging

The function includes comprehensive logging:

- `[INFO]` - Normal operation progress
- `[WARNING]` - Recoverable issues (missing job cards, etc.)
- `[ERROR]` - Serious errors that affect processing
- `[DEBUG]` - Detailed information for troubleshooting

## Related Functions

- `read_barcode()` - Core barcode processing function
- `bulk_update_operation_status()` - Efficient status updates
- `complete_job()` - Job completion logic
- `is_job_fully_complete()` - Job completion validation
- `submit_job_card()` - Job card submission
- `update_job_card_status()` - Status management

## Best Practices

1. **Always use 'Kalite' as operation type** - This function is specifically designed for quality control
2. **Provide quality_data when available** - Improves traceability and documentation
3. **Handle return values properly** - Check status and error_type for appropriate response handling
4. **Monitor logs** - Use logging information for troubleshooting and process optimization

## Performance Considerations

- Uses bulk operations for efficient database updates
- Processes operations sequentially to maintain data consistency
- Commits changes after completing all operations to minimize transaction time
- Includes retry logic with database connection management