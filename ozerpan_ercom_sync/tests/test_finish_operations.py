import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the app path to sys.path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from ozerpan_ercom_sync.custom_api.api import finish_with_previous_operations
from ozerpan_ercom_sync.custom_api.barcode_reader.constants import BarcodeStatus


class TestFinishWithPreviousOperations(unittest.TestCase):
    """Test cases for finish_with_previous_operations function"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_barcode = "TEST123456"
        self.mock_employee = "EMP001"
        self.mock_operation = "Kalite"
        self.mock_quality_data = {"overall_notes": "Test quality check"}

    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    def test_invalid_operation_parameter(self, mock_read_barcode):
        """Test that invalid operation parameter returns error"""
        result = finish_with_previous_operations(
            barcode=self.mock_barcode,
            employee=self.mock_employee,
            operation="InvalidOperation",
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "validation")
        self.assertIn("Invalid operation parameter", result["message"])
        mock_read_barcode.assert_not_called()

    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    def test_no_unfinished_operations(self, mock_read_barcode):
        """Test when there are no unfinished operations"""
        expected_result = {"status": "success", "message": "Quality check completed"}
        mock_read_barcode.return_value = expected_result

        result = finish_with_previous_operations(
            barcode=self.mock_barcode,
            employee=self.mock_employee,
            operation=self.mock_operation,
            quality_data=self.mock_quality_data,
        )

        self.assertEqual(result, expected_result)
        mock_read_barcode.assert_called_once()

    @patch("ozerpan_ercom_sync.custom_api.api.frappe")
    @patch("ozerpan_ercom_sync.custom_api.api.bulk_update_operation_status")
    @patch("ozerpan_ercom_sync.custom_api.api.complete_job")
    @patch("ozerpan_ercom_sync.custom_api.api.is_job_fully_complete")
    @patch("ozerpan_ercom_sync.custom_api.api.submit_job_card")
    @patch("ozerpan_ercom_sync.custom_api.api.update_job_card_status")
    @patch("ozerpan_ercom_sync.custom_api.api.save_with_retry")
    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    def test_complete_unfinished_operations_success(
        self,
        mock_read_barcode,
        mock_save_with_retry,
        mock_update_job_card_status,
        mock_submit_job_card,
        mock_is_job_fully_complete,
        mock_complete_job,
        mock_bulk_update_operation_status,
        mock_frappe,
    ):
        """Test successfully completing unfinished operations"""

        # Mock unfinished operations response
        unfinished_ops_result = {
            "status": "error",
            "error_type": "unfinished operations",
            "unfinished_operations": [
                {
                    "name": "Kaynak",
                    "job_card": "JOB-001",
                    "status": "Work In Progress",
                    "is_corrective": False,
                }
            ],
        }

        # Mock successful quality operation result
        success_result = {"status": "completed", "message": "Quality check completed"}

        # Set up read_barcode to return unfinished operations first, then success
        mock_read_barcode.side_effect = [unfinished_ops_result, success_result]

        # Mock job card document
        mock_job_card = Mock()
        mock_job_card.name = "JOB-001"
        mock_job_card.docstatus = 0  # Draft
        mock_job_card.custom_barcodes = [
            Mock(
                barcode="TEST123456",
                tesdetay_ref="TES-001",
                status=BarcodeStatus.IN_PROGRESS.value,
            ),
            Mock(
                barcode="TEST123457",
                tesdetay_ref="TES-002",
                status=BarcodeStatus.PENDING.value,
            ),
        ]

        mock_frappe.get_doc.return_value = mock_job_card
        mock_is_job_fully_complete.return_value = True

        result = finish_with_previous_operations(
            barcode=self.mock_barcode,
            employee=self.mock_employee,
            operation=self.mock_operation,
            quality_data=self.mock_quality_data,
        )

        # Verify the result
        self.assertEqual(result["status"], "completed")
        self.assertIn("completed_previous_operations", result)
        self.assertEqual(len(result["completed_previous_operations"]), 1)

        # Verify function calls
        mock_frappe.get_doc.assert_called_with("Job Card", "JOB-001")
        mock_bulk_update_operation_status.assert_called_once()
        mock_complete_job.assert_called_once_with(mock_job_card, 1)
        mock_is_job_fully_complete.assert_called_once_with(mock_job_card)
        mock_submit_job_card.assert_called_once_with(mock_job_card)
        mock_save_with_retry.assert_called_once_with(doc=mock_job_card)
        mock_frappe.db.commit.assert_called_once()

    @patch("ozerpan_ercom_sync.custom_api.api.frappe")
    @patch("ozerpan_ercom_sync.custom_api.api.bulk_update_operation_status")
    @patch("ozerpan_ercom_sync.custom_api.api.complete_job")
    @patch("ozerpan_ercom_sync.custom_api.api.is_job_fully_complete")
    @patch("ozerpan_ercom_sync.custom_api.api.submit_job_card")
    @patch("ozerpan_ercom_sync.custom_api.api.update_job_card_status")
    @patch("ozerpan_ercom_sync.custom_api.api.save_with_retry")
    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    def test_complete_operations_job_not_fully_complete(
        self,
        mock_read_barcode,
        mock_save_with_retry,
        mock_update_job_card_status,
        mock_submit_job_card,
        mock_is_job_fully_complete,
        mock_complete_job,
        mock_bulk_update_operation_status,
        mock_frappe,
    ):
        """Test completing operations when job is not fully complete"""

        # Mock unfinished operations response
        unfinished_ops_result = {
            "status": "error",
            "error_type": "unfinished operations",
            "unfinished_operations": [
                {
                    "name": "Kaynak",
                    "job_card": "JOB-001",
                    "status": "Work In Progress",
                    "is_corrective": False,
                }
            ],
        }

        success_result = {"status": "completed", "message": "Quality check completed"}
        mock_read_barcode.side_effect = [unfinished_ops_result, success_result]

        # Mock job card
        mock_job_card = Mock()
        mock_job_card.name = "JOB-001"
        mock_job_card.docstatus = 0
        mock_job_card.custom_barcodes = [
            Mock(
                barcode="TEST123456",
                tesdetay_ref="TES-001",
                status=BarcodeStatus.IN_PROGRESS.value,
            )
        ]

        mock_frappe.get_doc.return_value = mock_job_card
        mock_is_job_fully_complete.return_value = False  # Job not fully complete

        result = finish_with_previous_operations(
            barcode=self.mock_barcode,
            employee=self.mock_employee,
            operation=self.mock_operation,
        )

        # Verify job card was set to "On Hold" instead of submitted
        mock_update_job_card_status.assert_called_with(mock_job_card, "On Hold")
        mock_submit_job_card.assert_not_called()

    @patch("ozerpan_ercom_sync.custom_api.api.frappe")
    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    def test_missing_job_card_handling(self, mock_read_barcode, mock_frappe):
        """Test handling of missing job cards"""

        unfinished_ops_result = {
            "status": "error",
            "error_type": "unfinished operations",
            "unfinished_operations": [
                {
                    "name": "Kaynak",
                    "job_card": "MISSING-JOB",
                    "status": "Missing",
                    "is_corrective": False,
                }
            ],
        }

        success_result = {"status": "completed", "message": "Quality check completed"}
        mock_read_barcode.side_effect = [unfinished_ops_result, success_result]

        result = finish_with_previous_operations(
            barcode=self.mock_barcode,
            employee=self.mock_employee,
            operation=self.mock_operation,
        )

        # Should still succeed even with missing job cards
        self.assertEqual(result["status"], "completed")
        self.assertIn("completed_previous_operations", result)
        # Should be empty since missing job card was skipped
        self.assertEqual(len(result["completed_previous_operations"]), 0)

    @patch("ozerpan_ercom_sync.custom_api.api.frappe")
    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    def test_already_submitted_job_card(self, mock_read_barcode, mock_frappe):
        """Test handling of already submitted job cards"""

        unfinished_ops_result = {
            "status": "error",
            "error_type": "unfinished operations",
            "unfinished_operations": [
                {
                    "name": "Kaynak",
                    "job_card": "JOB-001",
                    "status": "Completed",
                    "is_corrective": False,
                }
            ],
        }

        success_result = {"status": "completed", "message": "Quality check completed"}
        mock_read_barcode.side_effect = [unfinished_ops_result, success_result]

        # Mock already submitted job card
        mock_job_card = Mock()
        mock_job_card.name = "JOB-001"
        mock_job_card.docstatus = 1  # Submitted
        mock_frappe.get_doc.return_value = mock_job_card

        result = finish_with_previous_operations(
            barcode=self.mock_barcode,
            employee=self.mock_employee,
            operation=self.mock_operation,
        )

        # Should succeed and skip the already submitted job card
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["completed_previous_operations"]), 0)

    @patch("ozerpan_ercom_sync.custom_api.api.frappe")
    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    def test_exception_handling(self, mock_read_barcode, mock_frappe):
        """Test exception handling during operation completion"""

        # Mock read_barcode to raise an exception
        mock_read_barcode.side_effect = Exception("Database connection failed")

        result = finish_with_previous_operations(
            barcode=self.mock_barcode,
            employee=self.mock_employee,
            operation=self.mock_operation,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "system_error")
        self.assertIn("Failed to complete previous operations", result["message"])
        mock_frappe.db.rollback.assert_called_once()

    @patch("ozerpan_ercom_sync.custom_api.api.frappe")
    @patch("ozerpan_ercom_sync.custom_api.api.read_barcode")
    def test_quality_operation_fails_after_completion(
        self, mock_read_barcode, mock_frappe
    ):
        """Test when quality operation fails after completing previous operations"""

        unfinished_ops_result = {
            "status": "error",
            "error_type": "unfinished operations",
            "unfinished_operations": [
                {
                    "name": "Kaynak",
                    "job_card": "JOB-001",
                    "status": "Work In Progress",
                    "is_corrective": False,
                }
            ],
        }

        # First call returns unfinished operations, second call raises exception
        mock_read_barcode.side_effect = [
            unfinished_ops_result,
            Exception("Quality operation failed"),
        ]

        # Mock empty job card to complete quickly
        mock_job_card = Mock()
        mock_job_card.name = "JOB-001"
        mock_job_card.docstatus = 0
        mock_job_card.custom_barcodes = []  # No barcodes to process
        mock_frappe.get_doc.return_value = mock_job_card

        result = finish_with_previous_operations(
            barcode=self.mock_barcode,
            employee=self.mock_employee,
            operation=self.mock_operation,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "quality_operation")
        self.assertIn("Previous operations completed successfully", result["message"])


if __name__ == "__main__":
    unittest.main()
