import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the app path to sys.path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from ozerpan_ercom_sync.custom_api.api import (
    finish_with_previous_operations,
    read_barcode,
)
from ozerpan_ercom_sync.custom_api.barcode_reader.exceptions import QualityControlError


class TestQualityValidation(unittest.TestCase):
    """Test cases for enhanced quality control validation"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_barcode = "TEST123456"
        self.mock_employee = "QC001"
        self.mock_operation = "Kalite"
        self.mock_quality_data = {
            "overall_notes": "Quality inspection test",
            "criteria": [{"name": "Dimensions", "passed": True}],
        }

    @patch("ozerpan_ercom_sync.custom_api.api.BarcodeReader")
    def test_quality_blocked_incomplete_operations(self, mock_barcode_reader):
        """Test quality control blocked when prerequisite operations are not completed"""

        # Mock barcode reader to raise QualityControlError for unfinished operations
        mock_reader_instance = Mock()
        mock_barcode_reader.return_value = mock_reader_instance

        # Simulate unfinished operations - some operations not completed
        unfinished_operations = [
            {
                "name": "Kaynak",
                "job_card": "JOB-001",
                "status": "Work In Progress",
                "is_corrective": False,
                "docstatus": 0,  # Not submitted
                "operation_status": "In Progress",
            },
            {
                "name": "Kanat Hazırlık",
                "job_card": "JOB-002",
                "status": "Open",
                "is_corrective": False,
                "docstatus": 0,  # Not submitted
                "operation_status": "Pending",
            },
        ]

        mock_reader_instance.read_barcode.side_effect = QualityControlError(
            "Quality control cannot start - the following operations must be completed AND submitted first:\n\n"
            + "• Kaynak: Job card not submitted (Status: Work In Progress)\n"
            + "• Kanat Hazırlık: Operation not completed (Status: Open)\n\n"
            + "Please complete and submit all manufacturing operations before starting quality control.",
            "unfinished operations",
            {"unfinished_operations": unfinished_operations},
        )

        # Call read_barcode directly (not finish_with_previous_operations)
        with patch("ozerpan_ercom_sync.custom_api.api.frappe"):
            result = read_barcode(
                barcode=self.mock_barcode,
                employee=self.mock_employee,
                operation=self.mock_operation,
                quality_data=self.mock_quality_data,
            )

        # Verify quality control was blocked
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "unfinished operations")
        self.assertIn("must be completed AND submitted first", result["message"])
        self.assertIn("unfinished_operations", result)

        # Verify unfinished operations details
        unfinished = result["unfinished_operations"]
        self.assertEqual(len(unfinished), 2)

        # Check first operation (not submitted)
        kaynak_op = next(op for op in unfinished if op["name"] == "Kaynak")
        self.assertEqual(kaynak_op["docstatus"], 0)
        self.assertEqual(kaynak_op["status"], "Work In Progress")

        # Check second operation (not completed)
        kanat_op = next(op for op in unfinished if op["name"] == "Kanat Hazırlık")
        self.assertEqual(kanat_op["docstatus"], 0)
        self.assertEqual(kanat_op["status"], "Open")

    @patch("ozerpan_ercom_sync.custom_api.api.BarcodeReader")
    def test_quality_blocked_completed_but_not_submitted(self, mock_barcode_reader):
        """Test quality control blocked when operations completed but not submitted"""

        mock_reader_instance = Mock()
        mock_barcode_reader.return_value = mock_reader_instance

        # Operations are completed but not submitted
        unfinished_operations = [
            {
                "name": "Kaynak",
                "job_card": "JOB-001",
                "status": "Completed (Not Submitted)",
                "is_corrective": False,
                "docstatus": 0,  # Not submitted - this is the issue!
                "operation_status": "Completed",
            }
        ]

        mock_reader_instance.read_barcode.side_effect = QualityControlError(
            "Quality control cannot start - the following operations must be completed AND submitted first:\n\n"
            + "• Kaynak: Job card not submitted (Status: Completed (Not Submitted))\n\n"
            + "Please complete and submit all manufacturing operations before starting quality control.",
            "unfinished operations",
            {"unfinished_operations": unfinished_operations},
        )

        with patch("ozerpan_ercom_sync.custom_api.api.frappe"):
            result = read_barcode(
                barcode=self.mock_barcode,
                employee=self.mock_employee,
                operation=self.mock_operation,
            )

        # Verify quality control was blocked due to non-submission
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "unfinished operations")
        self.assertIn("Job card not submitted", result["message"])

        unfinished = result["unfinished_operations"]
        self.assertEqual(len(unfinished), 1)
        self.assertEqual(unfinished[0]["docstatus"], 0)
        self.assertEqual(unfinished[0]["operation_status"], "Completed")

    @patch("ozerpan_ercom_sync.custom_api.api.BarcodeReader")
    def test_quality_allowed_all_operations_submitted(self, mock_barcode_reader):
        """Test quality control allowed when all operations are completed and submitted"""

        mock_reader_instance = Mock()
        mock_barcode_reader.return_value = mock_reader_instance

        # All operations properly completed and submitted - no blocking
        mock_reader_instance.read_barcode.return_value = {
            "status": "in_progress",
            "message": "Quality inspection started",
            "in_progress_barcodes": [self.mock_barcode],
        }

        with patch("ozerpan_ercom_sync.custom_api.api.frappe"):
            result = read_barcode(
                barcode=self.mock_barcode,
                employee=self.mock_employee,
                operation=self.mock_operation,
                quality_data=self.mock_quality_data,
            )

        # Verify quality control was allowed to proceed
        self.assertEqual(result["status"], "in_progress")
        self.assertIn("Quality inspection started", result["message"])
        self.assertIn("in_progress_barcodes", result)

    @patch("ozerpan_ercom_sync.custom_api.api.BarcodeReader")
    def test_quality_blocked_missing_job_cards(self, mock_barcode_reader):
        """Test quality control blocked when job cards are missing"""

        mock_reader_instance = Mock()
        mock_barcode_reader.return_value = mock_reader_instance

        unfinished_operations = [
            {
                "name": "Kaynak",
                "job_card": "MISSING-JOB-001",
                "status": "Missing",
                "is_corrective": False,
                "docstatus": 0,
                "operation_status": "Pending",
            }
        ]

        mock_reader_instance.read_barcode.side_effect = QualityControlError(
            "Quality control cannot start - the following operations must be completed AND submitted first:\n\n"
            + "• Kaynak: Job card missing\n\n"
            + "Please complete and submit all manufacturing operations before starting quality control.",
            "unfinished operations",
            {"unfinished_operations": unfinished_operations},
        )

        with patch("ozerpan_ercom_sync.custom_api.api.frappe"):
            result = read_barcode(
                barcode=self.mock_barcode,
                employee=self.mock_employee,
                operation=self.mock_operation,
            )

        # Verify quality control blocked due to missing job card
        self.assertEqual(result["status"], "error")
        self.assertIn("Job card missing", result["message"])

        unfinished = result["unfinished_operations"]
        self.assertEqual(unfinished[0]["status"], "Missing")

    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    @patch("ozerpan_ercom_sync.custom_api.api.frappe")
    def test_finish_with_previous_operations_skips_submitted(
        self, mock_frappe, mock_read_barcode
    ):
        """Test that finish_with_previous_operations skips already submitted job cards"""

        # Mock unfinished operations with mixed submission states
        unfinished_ops_result = {
            "status": "error",
            "error_type": "unfinished operations",
            "unfinished_operations": [
                {
                    "name": "Kaynak",
                    "job_card": "JOB-001",
                    "status": "Completed",
                    "is_corrective": False,
                    "docstatus": 1,  # Already submitted
                    "operation_status": "Completed",
                },
                {
                    "name": "Kanat Hazırlık",
                    "job_card": "JOB-002",
                    "status": "Completed (Not Submitted)",
                    "is_corrective": False,
                    "docstatus": 0,  # Not submitted
                    "operation_status": "Completed",
                },
            ],
        }

        success_result = {"status": "completed", "message": "Quality check completed"}
        mock_read_barcode.side_effect = [unfinished_ops_result, success_result]

        # Mock job cards
        submitted_job_card = Mock()
        submitted_job_card.name = "JOB-001"
        submitted_job_card.docstatus = 1  # Already submitted

        not_submitted_job_card = Mock()
        not_submitted_job_card.name = "JOB-002"
        not_submitted_job_card.docstatus = 0  # Not submitted
        not_submitted_job_card.status = "Completed"
        not_submitted_job_card.for_quantity = 10
        not_submitted_job_card.total_completed_qty = 10
        not_submitted_job_card.time_logs = [Mock(completed_qty=10)]
        not_submitted_job_card.custom_barcodes = []

        def mock_get_doc(doctype, name):
            if name == "JOB-001":
                return submitted_job_card
            elif name == "JOB-002":
                return not_submitted_job_card

        mock_frappe.get_doc.side_effect = mock_get_doc

        with patch(
            "ozerpan_ercom_sync.custom_api.api._complete_job_with_time_logs"
        ) as mock_complete:
            with patch(
                "ozerpan_ercom_sync.custom_api.api.submit_job_card"
            ) as mock_submit:
                with patch(
                    "ozerpan_ercom_sync.custom_api.api.save_with_retry"
                ) as mock_save:
                    result = finish_with_previous_operations(
                        barcode=self.mock_barcode,
                        employee=self.mock_employee,
                        operation=self.mock_operation,
                    )

        # Verify that only the non-submitted job card was processed
        self.assertEqual(result["status"], "completed")

        completed_ops = result.get("completed_previous_operations", [])
        self.assertEqual(len(completed_ops), 1)  # Only one operation should be processed

        # Should only process JOB-002 (not submitted), skip JOB-001 (already submitted)
        processed_job = completed_ops[0]["job_card"]
        self.assertEqual(processed_job, "JOB-002")

        # Verify functions were called for the non-submitted job card
        mock_complete.assert_called_once()
        mock_submit.assert_called_once()

    def test_enhanced_error_message_format(self):
        """Test that error messages provide clear guidance"""

        # Test various error message formats
        test_cases = [
            {
                "operations": [{"name": "Kaynak", "status": "Missing", "docstatus": 0}],
                "expected_fragment": "Job card missing",
            },
            {
                "operations": [
                    {
                        "name": "Kanat Hazırlık",
                        "status": "Completed (Not Submitted)",
                        "docstatus": 0,
                    }
                ],
                "expected_fragment": "Job card not submitted",
            },
            {
                "operations": [
                    {"name": "Orta Kayıt", "status": "Work In Progress", "docstatus": 0}
                ],
                "expected_fragment": "Operation not completed",
            },
        ]

        for test_case in test_cases:
            operations = test_case["operations"]
            expected_fragment = test_case["expected_fragment"]

            # Simulate error message generation logic
            error_details = []
            for op in operations:
                if op.get("status") == "Missing":
                    error_details.append(f"• {op['name']}: Job card missing")
                elif op.get("docstatus", 0) != 1:
                    error_details.append(
                        f"• {op['name']}: Job card not submitted (Status: {op['status']})"
                    )
                else:
                    error_details.append(
                        f"• {op['name']}: Operation not completed (Status: {op['status']})"
                    )

            message = (
                "Quality control cannot start - the following operations must be completed AND submitted first:\n\n"
                + "\n".join(error_details)
            )

            self.assertIn(expected_fragment, message)
            self.assertIn("must be completed AND submitted first", message)

    def test_docstatus_validation_logic(self):
        """Test the docstatus validation logic directly"""

        # Test cases for different job card states
        test_cases = [
            {
                "name": "Draft job card",
                "docstatus": 0,
                "operation_status": "Completed",
                "should_block": True,
                "reason": "Not submitted",
            },
            {
                "name": "Submitted job card",
                "docstatus": 1,
                "operation_status": "Completed",
                "should_block": False,
                "reason": "Properly submitted",
            },
            {
                "name": "Cancelled job card",
                "docstatus": 2,
                "operation_status": "Completed",
                "should_block": True,
                "reason": "Cancelled",
            },
            {
                "name": "Incomplete operation",
                "docstatus": 0,
                "operation_status": "Pending",
                "should_block": True,
                "reason": "Not completed",
            },
        ]

        for test_case in test_cases:
            # Simulate validation logic
            operation_completed = test_case["operation_status"] == "Completed"
            job_card_submitted = test_case["docstatus"] == 1

            should_allow_quality = operation_completed and job_card_submitted
            should_block = not should_allow_quality

            self.assertEqual(
                should_block,
                test_case["should_block"],
                f"Failed for {test_case['name']}: {test_case['reason']}",
            )


if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2)
