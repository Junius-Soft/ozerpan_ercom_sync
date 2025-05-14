import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open
import shutil
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from ozerpan_ercom_sync.custom_api.file_processor.utils.file_processing import (
    FileProcessingDirectories,
    FileInfo,
    FileSet,
    get_order_and_type,
    group_files_by_order,
    move_file,
    get_file_sets,
    process_file_with_error_handling
)
from ozerpan_ercom_sync.custom_api.file_processor.utils.file_set_processing import (
    get_processing_order,
    process_file_set,
    identify_file_sets,
    process_all_file_sets
)


class TestFileProcessing(FrappeTestCase):
    def setUp(self):
        # Create temporary directories for testing
        self.temp_dir = tempfile.mkdtemp()
        self.to_process = os.path.join(self.temp_dir, "to_process")
        self.processed = os.path.join(self.temp_dir, "processed")
        self.failed = os.path.join(self.temp_dir, "failed")
        
        os.makedirs(self.to_process, exist_ok=True)
        os.makedirs(self.processed, exist_ok=True)
        os.makedirs(self.failed, exist_ok=True)
        
        # Create test files
        test_files = [
            "12345_MLY3.xls",
            "12345_CAMLISTE.xls",
            "67890_OPTGENEL.xls",
            "67890_DST.xls",
            "11111_OTHER.xls"
        ]
        
        for filename in test_files:
            with open(os.path.join(self.to_process, filename), 'w') as f:
                f.write("Test content")
    
    def tearDown(self):
        # Clean up temporary directory
        shutil.rmtree(self.temp_dir)
    
    def test_file_processing_directories(self):
        """Test FileProcessingDirectories class"""
        dirs = FileProcessingDirectories(self.temp_dir)
        self.assertEqual(dirs.base_dir, self.temp_dir)
        self.assertEqual(dirs.to_process, self.to_process)
        self.assertEqual(dirs.processed, self.processed)
        self.assertEqual(dirs.failed, self.failed)
        
        # Test directory creation
        shutil.rmtree(self.processed)
        self.assertFalse(os.path.exists(self.processed))
        dirs.ensure_directories_exist()
        self.assertTrue(os.path.exists(self.processed))
    
    def test_get_order_and_type(self):
        """Test get_order_and_type function"""
        order_no, file_type = get_order_and_type("12345_MLY3.xls")
        self.assertEqual(order_no, "12345")
        self.assertEqual(file_type, "MLY3")
        
        order_no, file_type = get_order_and_type("67890_OPTGENEL.XLS")
        self.assertEqual(order_no, "67890")
        self.assertEqual(file_type, "OPTGENEL")
        
        # Test invalid filename
        with self.assertRaises(ValueError):
            get_order_and_type("invalid_filename.xls")
    
    def test_group_files_by_order(self):
        """Test group_files_by_order function"""
        grouped = group_files_by_order(self.to_process)
        
        # Check order groups
        self.assertIn("12345", grouped)
        self.assertIn("67890", grouped)
        self.assertIn("11111", grouped)
        
        # Check file types in order 12345
        self.assertIn("MLY3", grouped["12345"])
        self.assertIn("CAMLISTE", grouped["12345"])
        
        # Check file types in order 67890
        self.assertIn("OPTGENEL", grouped["67890"])
        self.assertIn("DST", grouped["67890"])
        
        # Check file type in order 11111
        self.assertIn("OTHER", grouped["11111"])
        
        # Check file info for specific file
        file_info = grouped["12345"]["MLY3"]
        self.assertEqual(file_info.filename, "12345_MLY3.xls")
        self.assertEqual(file_info.order_no, "12345")
        self.assertEqual(file_info.file_type, "MLY3")
        self.assertTrue(os.path.exists(file_info.path))
    
    @patch("ozerpan_ercom_sync.custom_api.file_processor.utils.file_processing.shutil")
    def test_move_file(self, mock_shutil):
        """Test move_file function"""
        file_info = FileInfo(
            filename="12345_MLY3.xls",
            path=os.path.join(self.to_process, "12345_MLY3.xls"),
            order_no="12345",
            file_type="MLY3"
        )
        
        # Test successful move
        move_file(file_info, self.processed)
        mock_shutil.move.assert_called_once_with(
            file_info.path, 
            os.path.join(self.processed, file_info.filename)
        )
        
        # Test move with error log
        mock_shutil.reset_mock()
        with patch("ozerpan_ercom_sync.custom_api.api.create_error_log_file") as mock_log:
            mock_log.return_value = "/tmp/error.log"
            move_file(
                file_info, 
                self.failed, 
                create_log=True,
                error_message="Test error",
                error_details={"error_type": "test"}
            )
            mock_log.assert_called_once()
            mock_shutil.move.assert_any_call(
                file_info.path, 
                os.path.join(self.failed, file_info.filename)
            )
            mock_shutil.move.assert_any_call(
                "/tmp/error.log", 
                os.path.join(self.failed, f"{file_info.filename}.log")
            )
    
    def test_get_file_sets(self):
        """Test get_file_sets function"""
        file_sets = get_file_sets()
        self.assertIn(FileSet.SET_A.value, file_sets)
        self.assertIn(FileSet.SET_B.value, file_sets)
        
        # Check file types in set_a
        self.assertIn("MLY3", file_sets[FileSet.SET_A.value])
        self.assertIn("CAMLISTE", file_sets[FileSet.SET_A.value])
        
        # Check file types in set_b
        self.assertIn("OPTGENEL", file_sets[FileSet.SET_B.value])
        self.assertIn("DST", file_sets[FileSet.SET_B.value])
    
    @patch("ozerpan_ercom_sync.custom_api.file_processor.utils.file_processing.move_file")
    def test_process_file_with_error_handling(self, mock_move):
        """Test process_file_with_error_handling function"""
        # Mock the manager
        manager = MagicMock()
        
        # Test successful processing
        file_info = FileInfo(
            filename="12345_MLY3.xls",
            path=os.path.join(self.to_process, "12345_MLY3.xls"),
            order_no="12345",
            file_type="MLY3"
        )
        
        manager.process_file.return_value = {
            "status": "success",
            "message": "File processed successfully"
        }
        
        result = process_file_with_error_handling(
            manager, file_info, self.processed, self.failed
        )
        
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["processed"])
        mock_move.assert_called_once_with(file_info, self.processed)
        
        # Test processing failure
        mock_move.reset_mock()
        manager.process_file.return_value = {
            "status": "error",
            "message": "Processing failed",
            "error_type": "validation"
        }
        
        result = process_file_with_error_handling(
            manager, file_info, self.processed, self.failed
        )
        
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["processed"])
        self.assertIn("error_details", result)
        mock_move.assert_called_once_with(
            file_info, 
            self.failed, 
            create_log=True,
            error_message="Processing failed",
            error_details={
                "error_type": "validation",
                "order_no": "12345",
                "file_type": "MLY3",
                "file_type_name": "MLY3"
            }
        )
        
        # Test exception handling
        mock_move.reset_mock()
        manager.process_file.side_effect = Exception("Test exception")
        
        result = process_file_with_error_handling(
            manager, file_info, self.processed, self.failed
        )
        
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["processed"])
        self.assertIn("error_details", result)
        self.assertEqual(result["error_message"], "Test exception")
        mock_move.assert_called_once()


class TestFileSetProcessing(FrappeTestCase):
    def setUp(self):
        # Create mock file dictionaries for testing
        self.set_a_files = {
            "MLY3": FileInfo(
                filename="12345_MLY3.xls",
                path="/path/to/12345_MLY3.xls",
                order_no="12345",
                file_type="MLY3"
            ),
            "CAMLISTE": FileInfo(
                filename="12345_CAMLISTE.xls",
                path="/path/to/12345_CAMLISTE.xls",
                order_no="12345",
                file_type="CAMLISTE"
            )
        }
        
        self.set_b_files = {
            "OPTGENEL": FileInfo(
                filename="67890_OPTGENEL.xls",
                path="/path/to/67890_OPTGENEL.xls",
                order_no="67890",
                file_type="OPTGENEL"
            ),
            "DST": FileInfo(
                filename="67890_DST.xls",
                path="/path/to/67890_DST.xls",
                order_no="67890",
                file_type="DST"
            )
        }
        
        self.mixed_files = {
            "MLY3": self.set_a_files["MLY3"],
            "DST": self.set_b_files["DST"],
            "OTHER": FileInfo(
                filename="12345_OTHER.xls",
                path="/path/to/12345_OTHER.xls",
                order_no="12345",
                file_type="OTHER"
            )
        }
    
    def test_get_processing_order(self):
        """Test get_processing_order function"""
        # Test set_a with both files
        order = get_processing_order(self.set_a_files, FileSet.SET_A.value)
        self.assertEqual(order[0], "MLY3")
        self.assertIn("CAMLISTE", order)
        
        # Test set_a with only MLY3
        order = get_processing_order({"MLY3": self.set_a_files["MLY3"]}, FileSet.SET_A.value)
        self.assertEqual(order, ["MLY3"])
        
        # Test set_b with both files
        order = get_processing_order(self.set_b_files, FileSet.SET_B.value)
        self.assertEqual(order[0], "OPTGENEL")
        self.assertIn("DST", order)
        
        # Test set_b with only DST
        order = get_processing_order({"DST": self.set_b_files["DST"]}, FileSet.SET_B.value)
        self.assertEqual(order, ["DST"])
        
        # Test empty file dictionary
        order = get_processing_order({}, FileSet.SET_A.value)
        self.assertEqual(order, [])
    
    def test_identify_file_sets(self):
        """Test identify_file_sets function"""
        # Test with files from both sets
        sets = identify_file_sets({**self.set_a_files, **self.set_b_files})
        self.assertIn(FileSet.SET_A.value, sets)
        self.assertIn(FileSet.SET_B.value, sets)
        
        # Check files in set_a
        self.assertIn("MLY3", sets[FileSet.SET_A.value])
        self.assertIn("CAMLISTE", sets[FileSet.SET_A.value])
        
        # Check files in set_b
        self.assertIn("OPTGENEL", sets[FileSet.SET_B.value])
        self.assertIn("DST", sets[FileSet.SET_B.value])
        
        # Test with only set_a files
        sets = identify_file_sets(self.set_a_files)
        self.assertIn(FileSet.SET_A.value, sets)
        self.assertNotIn(FileSet.SET_B.value, sets)
        
        # Test with mixed files and another type
        sets = identify_file_sets(self.mixed_files)
        self.assertIn(FileSet.SET_A.value, sets)
        self.assertIn(FileSet.SET_B.value, sets)
        self.assertEqual(len(sets[FileSet.SET_A.value]), 1)
        self.assertEqual(len(sets[FileSet.SET_B.value]), 1)
    
    @patch("ozerpan_ercom_sync.custom_api.file_processor.utils.file_set_processing.process_file_with_error_handling")
    def test_process_file_set(self, mock_process):
        """Test process_file_set function"""
        # Mock successful processing
        mock_process.return_value = {
            "status": "success",
            "processed": True,
            "error_details": None,
            "error_message": None
        }
        
        # Test processing set_a
        result = process_file_set(
            MagicMock(),
            "12345",
            self.set_a_files,
            FileSet.SET_A.value,
            "/processed",
            "/failed"
        )
        
        self.assertEqual(len(result["files_processed"]), 2)
        self.assertEqual(len(result["files_failed"]), 0)
        self.assertEqual(result["file_set"], FileSet.SET_A.value)
        
        # Verify MLY3 was processed first
        mock_process.assert_any_call(
            mock_process.call_args_list[0][0][0],
            self.set_a_files["MLY3"],
            "/processed",
            "/failed"
        )
        
        # Test processing with failures
        mock_process.reset_mock()
        mock_process.side_effect = [
            {
                "status": "success",
                "processed": True,
                "error_details": None,
                "error_message": None
            },
            {
                "status": "error",
                "processed": False,
                "error_details": {"error_type": "validation"},
                "error_message": "Validation failed"
            }
        ]
        
        result = process_file_set(
            MagicMock(),
            "12345",
            self.set_a_files,
            FileSet.SET_A.value,
            "/processed",
            "/failed"
        )
        
        self.assertEqual(len(result["files_processed"]), 1)
        self.assertEqual(len(result["files_failed"]), 1)
    
    @patch("ozerpan_ercom_sync.custom_api.file_processor.utils.file_set_processing.identify_file_sets")
    @patch("ozerpan_ercom_sync.custom_api.file_processor.utils.file_set_processing.process_file_set")
    @patch("ozerpan_ercom_sync.custom_api.file_processor.utils.file_set_processing.process_file_with_error_handling")
    def test_process_all_file_sets(self, mock_process, mock_set_process, mock_identify):
        """Test process_all_file_sets function"""
        # Setup mocks
        mock_identify.return_value = {
            FileSet.SET_A.value: self.set_a_files,
            FileSet.SET_B.value: self.set_b_files
        }
        
        mock_set_process.side_effect = [
            {
                "files_processed": ["12345_MLY3.xls", "12345_CAMLISTE.xls"],
                "files_failed": [],
                "file_set": FileSet.SET_A.value
            },
            {
                "files_processed": ["67890_OPTGENEL.xls"],
                "files_failed": ["67890_DST.xls"],
                "file_set": FileSet.SET_B.value
            }
        ]
        
        # Test processing all file sets
        result = process_all_file_sets(
            MagicMock(),
            "12345",
            {**self.set_a_files, **self.set_b_files, **{"OTHER": self.mixed_files["OTHER"]}},
            "/processed",
            "/failed"
        )
        
        self.assertEqual(len(result["files_processed"]), 3)
        self.assertEqual(len(result["files_failed"]), 1)
        self.assertEqual(len(result["file_sets_processed"]), 2)
        
        # Verify processing of files not in any set
        self.assertEqual(mock_process.call_count, 1)
        mock_process.assert_called_with(
            mock_process.call_args[0][0],
            self.mixed_files["OTHER"],
            "/processed",
            "/failed"
        )


if __name__ == "__main__":
    unittest.main()