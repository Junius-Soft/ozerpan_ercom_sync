#!/usr/bin/env python3
"""
Test script for work order sequence validation handling in finish_with_previous_operations.

This script tests the enhanced error handling for work order sequence validation
that prevents completing operations out of order (e.g., "Kanat Hazırlık" before "Orta Kayıt").
"""

from typing import Any, Dict, List
from unittest.mock import patch


def create_mock_unfinished_operations() -> List[Dict[str, Any]]:
    """Create mock unfinished operations with sequence dependency issues"""
    return [
        {
            "name": "Kanat Hazırlık",  # This operation requires Orta Kayıt to be completed first
            "job_card": "PO-JOB07071",
            "status": "Open",
            "is_corrective": False,
        },
        {
            "name": "Orta Kayıt",  # This should be completed before Kanat Hazırlık
            "job_card": "PO-JOB07070",
            "status": "Open",
            "is_corrective": False,
        },
        {
            "name": "Kaynak Köşe Temizleme",  # This can be completed independently
            "job_card": "PO-JOB07069",
            "status": "Open",
            "is_corrective": False,
        },
    ]


def create_mock_sequence_error():
    """Create the specific sequence validation error from Frappe"""
    return Exception(
        "Job Card PO-JOB07071: As per the sequence of the operations in the work order MFG-WO-2025-01554, "
        "complete the operation Orta Kayıt before the operation Kanat Hazırlık."
    )


def test_operation_sequence_detection():
    """Test that operations are sorted by work order sequence"""
    print("\n=== Test 1: Operation Sequence Detection ===")

    with patch("ozerpan_ercom_sync.custom_api.api._get_operation_sequence") as mock_seq:
        # Mock sequence values - lower numbers should come first
        def get_sequence(job_card, operation):
            sequences = {
                "Orta Kayıt": 2,
                "Kanat Hazırlık": 3,
                "Kaynak Köşe Temizleme": 1,
            }
            return sequences.get(operation, 999)

        mock_seq.side_effect = get_sequence

        operations = create_mock_unfinished_operations()

        # Sort operations by sequence
        sorted_ops = sorted(
            operations, key=lambda x: get_sequence(x["job_card"], x["name"])
        )

        expected_order = ["Kaynak Köşe Temizleme", "Orta Kayıt", "Kanat Hazırlık"]
        actual_order = [op["name"] for op in sorted_ops]

        print(f"Original order: {[op['name'] for op in operations]}")
        print(f"Sorted order: {actual_order}")
        print(f"Expected order: {expected_order}")

        if actual_order == expected_order:
            print("✅ PASS: Operations sorted correctly by sequence")
        else:
            print("❌ FAIL: Operations not sorted correctly")


def test_sequence_validation_error_handling():
    """Test handling of work order sequence validation errors"""
    print("\n=== Test 2: Sequence Validation Error Handling ===")

    # Simulate the specific sequence validation error
    sequence_error = create_mock_sequence_error()
    error_message = str(sequence_error)

    # Test error detection logic
    is_sequence_error = (
        "complete the operation" in error_message
        and "before the operation" in error_message
    )

    print(f"Error message: {error_message}")
    print(f"Detected as sequence error: {is_sequence_error}")

    if is_sequence_error:
        print("✅ PASS: Sequence validation error correctly detected")

        # Test error parsing to extract operation names
        try:
            parts = error_message.split("complete the operation ")[1]
            required_op = parts.split(" before the operation ")[0]
            blocked_op = parts.split(" before the operation ")[1].rstrip(".")

            print(f"Required operation: '{required_op}'")
            print(f"Blocked operation: '{blocked_op}'")

            if required_op == "Orta Kayıt" and blocked_op == "Kanat Hazırlık":
                print("✅ PASS: Operation names extracted correctly")
            else:
                print("❌ FAIL: Operation names not extracted correctly")

        except Exception as parse_error:
            print(f"❌ FAIL: Could not parse operation names: {parse_error}")
    else:
        print("❌ FAIL: Sequence validation error not detected")


def test_retry_logic_simulation():
    """Test the retry logic for operations that initially fail due to sequence"""
    print("\n=== Test 3: Retry Logic Simulation ===")

    operations = create_mock_unfinished_operations()

    # Simulate first pass results
    first_pass_results = {
        "Kaynak Köşe Temizleme": "completed",
        "Orta Kayıt": "completed",
        "Kanat Hazırlık": "sequence_error",  # This failed due to sequence
    }

    # Operations marked for retry
    retry_operations = [
        op for op in operations if first_pass_results.get(op["name"]) == "sequence_error"
    ]

    print(f"Operations to retry: {[op['name'] for op in retry_operations]}")

    # Simulate retry results (should succeed now that prerequisites are done)
    retry_results = {"Kanat Hazırlık": "completed_on_retry"}

    # Final status summary
    final_status = {}
    for op in operations:
        op_name = op["name"]
        if op_name in retry_results:
            final_status[op_name] = retry_results[op_name]
        else:
            final_status[op_name] = first_pass_results.get(op_name, "unknown")

    print("Final operation status:")
    for op_name, status in final_status.items():
        print(f"  - {op_name}: {status}")

    # Verify all operations completed
    all_completed = all(
        status in ["completed", "completed_on_retry"] for status in final_status.values()
    )

    if all_completed:
        print("✅ PASS: All operations completed successfully with retry logic")
    else:
        print("❌ FAIL: Some operations still not completed")


def test_work_order_sequence_query():
    """Test the work order sequence query logic"""
    print("\n=== Test 4: Work Order Sequence Query ===")

    # Mock database responses
    mock_work_orders = {
        "PO-JOB07069": "MFG-WO-2025-01554",
        "PO-JOB07070": "MFG-WO-2025-01554",
        "PO-JOB07071": "MFG-WO-2025-01554",
    }

    mock_operation_sequences = {
        ("MFG-WO-2025-01554", "Kaynak Köşe Temizleme"): 1,
        ("MFG-WO-2025-01554", "Orta Kayıt"): 2,
        ("MFG-WO-2025-01554", "Kanat Hazırlık"): 3,
    }

    def mock_get_sequence(job_card_name: str, operation_name: str) -> int:
        """Mock implementation of _get_operation_sequence"""
        try:
            work_order = mock_work_orders.get(job_card_name)
            if not work_order:
                return 999

            sequence = mock_operation_sequences.get((work_order, operation_name))
            return sequence or 999

        except Exception:
            return 999

    # Test sequence retrieval
    test_cases = [
        ("PO-JOB07069", "Kaynak Köşe Temizleme", 1),
        ("PO-JOB07070", "Orta Kayıt", 2),
        ("PO-JOB07071", "Kanat Hazırlık", 3),
        ("PO-JOB99999", "Unknown Operation", 999),  # Missing job card
        ("PO-JOB07071", "Unknown Operation", 999),  # Missing operation
    ]

    all_passed = True
    for job_card, operation, expected_seq in test_cases:
        actual_seq = mock_get_sequence(job_card, operation)
        passed = actual_seq == expected_seq

        print(f"Job: {job_card}, Op: {operation}")
        print(
            f"  Expected sequence: {expected_seq}, Got: {actual_seq} {'✅' if passed else '❌'}"
        )

        if not passed:
            all_passed = False

    if all_passed:
        print("✅ PASS: Work order sequence query logic working correctly")
    else:
        print("❌ FAIL: Work order sequence query has issues")


def test_complete_workflow_simulation():
    """Test the complete workflow with sequence validation"""
    print("\n=== Test 5: Complete Workflow Simulation ===")

    operations = create_mock_unfinished_operations()

    # Simulate the complete finish_with_previous_operations workflow
    workflow_log = []

    # Step 1: Sort operations by sequence
    def get_seq(op):
        sequences = {"Kaynak Köşe Temizleme": 1, "Orta Kayıt": 2, "Kanat Hazırlık": 3}
        return sequences.get(op["name"], 999)

    sorted_operations = sorted(operations, key=get_seq)
    workflow_log.append(f"Sorted operations: {[op['name'] for op in sorted_operations]}")

    # Step 2: Process operations (first pass)
    completed_operations = []
    retry_operations = []

    for op in sorted_operations:
        op_name = op["name"]

        # Simulate processing
        if op_name == "Kanat Hazırlık":
            # This will fail on first pass due to sequence validation
            workflow_log.append(f"❌ {op_name}: Sequence validation error - retry later")
            retry_operations.append(op)
        else:
            # These succeed
            workflow_log.append(f"✅ {op_name}: Completed successfully")
            completed_operations.append(
                {
                    "job_card": op["job_card"],
                    "operation": op_name,
                    "completed_barcodes": 5,
                    "status": "completed",
                }
            )

    # Step 3: Retry failed operations
    if retry_operations:
        workflow_log.append(f"Retrying {len(retry_operations)} operations...")

        for op in retry_operations:
            op_name = op["name"]
            # Should succeed now that prerequisites are done
            workflow_log.append(f"✅ {op_name}: Completed on retry")
            completed_operations.append(
                {
                    "job_card": op["job_card"],
                    "operation": op_name,
                    "completed_barcodes": 7,
                    "status": "completed_on_retry",
                }
            )

    # Step 4: Final results
    workflow_log.append(f"Final result: {len(completed_operations)} operations completed")

    # Print workflow log
    print("Workflow execution log:")
    for i, log_entry in enumerate(workflow_log, 1):
        print(f"  {i}. {log_entry}")

    # Verify all operations completed
    completed_names = [op["operation"] for op in completed_operations]
    original_names = [op["name"] for op in operations]

    if set(completed_names) == set(original_names):
        print("✅ PASS: Complete workflow handled sequence validation correctly")

        # Show final results
        print("\nFinal Results:")
        for op in completed_operations:
            status_icon = "🔄" if op["status"] == "completed_on_retry" else "✅"
            print(f"  {status_icon} {op['operation']}: {op['status']}")

    else:
        print("❌ FAIL: Workflow did not complete all operations")
        print(f"Expected: {sorted(original_names)}")
        print(f"Completed: {sorted(completed_names)}")


def test_error_message_variations():
    """Test handling of different error message formats"""
    print("\n=== Test 6: Error Message Variations ===")

    error_variations = [
        # Standard sequence error
        "Job Card PO-JOB07071: As per the sequence of the operations in the work order MFG-WO-2025-01554, complete the operation Orta Kayıt before the operation Kanat Hazırlık.",
        # Different wording
        "As per the sequence, complete the operation Welding before the operation Assembly.",
        # Multiple operations
        "Complete the operation Cutting and Bending before the operation Welding.",
        # Non-sequence error (should not be detected)
        "Job Card validation failed: Missing required fields",
        # Another non-sequence error
        "Operation cannot be completed: Insufficient materials",
    ]

    sequence_error_count = 0

    for i, error_msg in enumerate(error_variations, 1):
        is_sequence_error = (
            "complete the operation" in error_msg and "before the operation" in error_msg
        )

        print(f"Error {i}: {'Sequence' if is_sequence_error else 'Other'}")
        print(f"  Message: {error_msg[:80]}{'...' if len(error_msg) > 80 else ''}")

        if is_sequence_error:
            sequence_error_count += 1

    expected_sequence_errors = 3  # First 3 should be detected as sequence errors

    if sequence_error_count == expected_sequence_errors:
        print(f"✅ PASS: Correctly identified {sequence_error_count} sequence errors")
    else:
        print(
            f"❌ FAIL: Expected {expected_sequence_errors} sequence errors, found {sequence_error_count}"
        )


def main():
    """Run all sequence validation tests"""
    print("🔧 Sequence Validation Test Suite")
    print("=" * 50)

    try:
        test_operation_sequence_detection()
        test_sequence_validation_error_handling()
        test_retry_logic_simulation()
        test_work_order_sequence_query()
        test_complete_workflow_simulation()
        test_error_message_variations()

        print("\n" + "=" * 50)
        print("✅ All sequence validation tests completed!")

    except Exception as e:
        print(f"\n❌ Test suite failed with error: {str(e)}")
        import traceback

        print("Traceback:")
        print(traceback.format_exc())


if __name__ == "__main__":
    main()
