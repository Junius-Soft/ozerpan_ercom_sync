#!/usr/bin/env python3
"""
Example usage script for finish_with_previous_operations function.

This script demonstrates various ways to call the finish_with_previous_operations
function and handle its responses.
"""

import json
from typing import Any, Dict

# In a real Frappe environment, you would import like this:
# from ozerpan_ercom_sync.custom_api.api import finish_with_previous_operations


# For this example, we'll simulate the function call
def simulate_finish_with_previous_operations(*args, **kwargs):
    """Simulate the function for demonstration purposes"""
    print(f"Called finish_with_previous_operations with args: {args}, kwargs: {kwargs}")
    return {"status": "completed", "message": "Simulated success"}


def example_basic_usage():
    """Example 1: Basic quality control operation"""
    print("\n=== Example 1: Basic Usage ===")

    result = simulate_finish_with_previous_operations(
        barcode="ABC123456", employee="EMP001", operation="Kalite"
    )

    print(f"Result: {json.dumps(result, indent=2)}")

    if result["status"] == "completed":
        print("✅ Quality operation completed successfully")
        if "completed_previous_operations" in result:
            print(
                f"📋 Completed {len(result['completed_previous_operations'])} previous operations"
            )
    else:
        print(f"❌ Operation failed: {result.get('message', 'Unknown error')}")


def example_with_quality_data():
    """Example 2: Quality control with detailed inspection data"""
    print("\n=== Example 2: With Quality Data ===")

    quality_data = {
        "overall_notes": "Standard quality inspection performed",
        "criteria": [
            {
                "name": "Dimensions",
                "passed": True,
                "notes": "All measurements within tolerance",
            },
            {"name": "Surface Quality", "passed": True, "notes": "No visible defects"},
            {
                "name": "Weld Quality",
                "passed": False,
                "notes": "Minor porosity detected in corner weld",
            },
        ],
    }

    result = simulate_finish_with_previous_operations(
        barcode="DEF789012",
        employee="QC_INSPECTOR_01",
        operation="Kalite",
        quality_data=quality_data,
        order_no="ORD-2024-001",
        poz_no=3,
    )

    print(f"Quality Data: {json.dumps(quality_data, indent=2)}")
    print(f"Result: {json.dumps(result, indent=2)}")


def example_with_full_parameters():
    """Example 3: Using all available parameters"""
    print("\n=== Example 3: Full Parameters ===")

    result = simulate_finish_with_previous_operations(
        barcode="GHI345678",
        employee="EMP_QUALITY_002",
        operation="Kalite",
        quality_data={
            "overall_notes": "Final quality check before shipping",
            "criteria": [{"name": "Final Assembly", "passed": True}],
        },
        order_no="ORD-2024-002",
        poz_no=5,
        sanal_adet=10,
        tesdetay_name="TES-DETAIL-001",
    )

    print(f"Result: {json.dumps(result, indent=2)}")


def example_error_handling():
    """Example 4: Proper error handling"""
    print("\n=== Example 4: Error Handling ===")

    def process_barcode_with_error_handling(barcode: str, employee: str) -> bool:
        """Process a barcode with comprehensive error handling"""
        try:
            result = simulate_finish_with_previous_operations(
                barcode=barcode, employee=employee, operation="Kalite"
            )

            # Handle different response types
            if result["status"] == "error":
                error_type = result.get("error_type", "unknown")
                message = result.get("message", "No error message")

                if error_type == "validation":
                    print(f"❌ Validation Error: {message}")
                    return False
                elif error_type == "unfinished operations":
                    print(f"⚠️ Unfinished Operations: {message}")
                    # This shouldn't happen with finish_with_previous_operations
                    # but good to handle anyway
                    return False
                elif error_type == "system_error":
                    print(f"🔥 System Error: {message}")
                    return False
                elif error_type == "quality_operation":
                    print(f"⚠️ Quality Operation Error: {message}")
                    # Operations may have been completed, check if retry is possible
                    return False
                else:
                    print(f"❓ Unknown Error ({error_type}): {message}")
                    return False

            elif result["status"] in ["completed", "in_progress"]:
                print(f"✅ Success: {result.get('message', 'Operation completed')}")

                # Log completed previous operations if any
                if "completed_previous_operations" in result:
                    completed_ops = result["completed_previous_operations"]
                    if completed_ops:
                        print("📋 Completed previous operations:")
                        for op in completed_ops:
                            print(
                                f"   - {op['operation']} (Job: {op['job_card']}, Barcodes: {op['completed_barcodes']})"
                            )

                return True
            else:
                print(f"❓ Unexpected status: {result['status']}")
                return False

        except Exception as e:
            print(f"🔥 Unexpected exception: {str(e)}")
            return False

    # Test with different barcodes
    test_barcodes = ["VALID123", "INVALID456", "ERROR789"]

    for barcode in test_barcodes:
        print(f"\nProcessing barcode: {barcode}")
        success = process_barcode_with_error_handling(barcode, "EMP_TEST")
        print(f"Result: {'Success' if success else 'Failed'}")


def example_batch_processing():
    """Example 5: Batch processing multiple barcodes"""
    print("\n=== Example 5: Batch Processing ===")

    barcodes_to_process = [
        {"barcode": "BATCH001", "employee": "QC_001", "order_no": "ORD-001"},
        {"barcode": "BATCH002", "employee": "QC_001", "order_no": "ORD-001"},
        {"barcode": "BATCH003", "employee": "QC_002", "order_no": "ORD-002"},
    ]

    results = []

    for item in barcodes_to_process:
        print(f"\nProcessing: {item['barcode']}")

        result = simulate_finish_with_previous_operations(
            barcode=item["barcode"],
            employee=item["employee"],
            operation="Kalite",
            order_no=item.get("order_no"),
            quality_data={
                "overall_notes": f"Batch quality check for {item['barcode']}",
                "criteria": [{"name": "Standard Check", "passed": True}],
            },
        )

        results.append(
            {
                "barcode": item["barcode"],
                "success": result["status"] in ["completed", "in_progress"],
                "result": result,
            }
        )

        if result["status"] == "completed":
            print(f"✅ {item['barcode']}: Completed")
        else:
            print(f"❌ {item['barcode']}: {result.get('message', 'Failed')}")

    # Summary
    successful = sum(1 for r in results if r["success"])
    total = len(results)
    print(f"\n📊 Batch Summary: {successful}/{total} successful")


def example_invalid_operation():
    """Example 6: Demonstrate validation error for invalid operation"""
    print("\n=== Example 6: Invalid Operation ===")

    # This should return a validation error since operation must be "Kalite"
    result = simulate_finish_with_previous_operations(
        barcode="TEST123",
        employee="EMP001",
        operation="Kaynak",  # Invalid - should be "Kalite"
    )

    print(f"Result: {json.dumps(result, indent=2)}")

    if result["status"] == "error" and result.get("error_type") == "validation":
        print("✅ Validation error caught as expected")
    else:
        print("❌ Expected validation error not received")


def main():
    """Run all examples"""
    print("🔧 Finish With Previous Operations - Usage Examples")
    print("=" * 60)

    try:
        example_basic_usage()
        example_with_quality_data()
        example_with_full_parameters()
        example_error_handling()
        example_batch_processing()
        example_invalid_operation()

        print("\n" + "=" * 60)
        print("✅ All examples completed successfully!")

    except Exception as e:
        print(f"\n❌ Error running examples: {str(e)}")


if __name__ == "__main__":
    main()


# Additional utility functions that might be helpful


def create_quality_data_template() -> Dict[str, Any]:
    """Create a template for quality data"""
    return {
        "overall_notes": "",
        "criteria": [
            {"name": "Dimensions", "passed": True, "notes": ""},
            {"name": "Surface Quality", "passed": True, "notes": ""},
            {"name": "Assembly", "passed": True, "notes": ""},
        ],
    }


def validate_quality_data(quality_data: Dict[str, Any]) -> bool:
    """Validate quality data structure"""
    if not isinstance(quality_data, dict):
        return False

    if "criteria" not in quality_data:
        return False

    if not isinstance(quality_data["criteria"], list):
        return False

    for criterion in quality_data["criteria"]:
        if not isinstance(criterion, dict):
            return False
        if "name" not in criterion or "passed" not in criterion:
            return False

    return True


def format_response_for_display(result: Dict[str, Any]) -> str:
    """Format the API response for user-friendly display"""
    if result["status"] == "completed":
        display = "✅ COMPLETED\n"
        display += f"Message: {result.get('message', 'N/A')}\n"

        if "completed_previous_operations" in result:
            ops = result["completed_previous_operations"]
            if ops:
                display += f"Previous operations completed: {len(ops)}\n"
                for op in ops:
                    display += (
                        f"  - {op['operation']}: {op['completed_barcodes']} barcodes\n"
                    )

    elif result["status"] == "error":
        display = "❌ ERROR\n"
        display += f"Type: {result.get('error_type', 'Unknown')}\n"
        display += f"Message: {result.get('message', 'No message')}\n"

    else:
        display = f"ℹ️ {result['status'].upper()}\n"
        display += f"Message: {result.get('message', 'N/A')}\n"

    return display
