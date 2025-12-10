import json
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from ozerpan_ercom_sync.custom_api.barcode_reader.models.quality_data import QualityData
from ozerpan_ercom_sync.custom_api.glass_processor.utils import get_job_card

# Removed unused imports - using SQL-based functions instead
from .types import GlassOperationRequest


class GlassOperationProcessor:
    def process(self, operation_data: GlassOperationRequest) -> Dict[str, any]:
        print("\n\n\n-- Process Glass --\n\n\n")
        raw_quality_data = operation_data.quality_data
        glass_name = operation_data.glass_name
        quality_data = QualityData(**raw_quality_data) if raw_quality_data else None
        
        # Validate glass_name exists first
        if not frappe.db.exists("CamListe", glass_name):
            frappe.throw(_("Cam bulunamadı: {0}").format(glass_name))
        
        job_card = get_job_card(glass_name)
        current_glass = self._get_current_glass(job_card, glass_name)
        
        # Check if glass was found in job card
        if not current_glass:
            # Try to find glass using SQL as fallback
            current_glass = self._get_current_glass_fallback(glass_name, job_card.name)
            if not current_glass:
                frappe.throw(_("Cam, Job Card'da bulunamadı. Glass Name: {0}, Job Card: {1}").format(
                    glass_name, job_card.name
                ))
        
        related_glasses = self._get_related_glasses(job_card, current_glass)
        employee = operation_data["employee"]

        # Get status safely (handle both dict and object)
        glass_status = current_glass.get("status") if isinstance(current_glass, dict) else getattr(current_glass, "status", None)
        glass_ref = current_glass.get("glass_ref") if isinstance(current_glass, dict) else getattr(current_glass, "glass_ref", None)

        if glass_status == "Completed" and not quality_data:
            return {
                "status": "error",
                "message": _("This item is already completed"),
                "item": current_glass,
            }

        if glass_status == "Pending" or glass_status == "In Correction":
            return self._handle_pending_item(
                job_card, current_glass, related_glasses, employee
            )
        elif quality_data:
            return self._handle_quality_control(
                job_card, current_glass, related_glasses, quality_data, employee
            )
        else:
            frappe.throw(_("Geçersiz cam durumu: {0}. Cam: {1}").format(glass_status or "None", glass_ref or glass_name))

    def _handle_quality_control(
        self,
        job_card: Any,
        current_glass: Dict,
        related_glasses: List[Dict],
        quality_data: QualityData,
        employee: str,
    ):
        print("--- Handle Quality Control --")

        # Get status safely
        glass_status = current_glass.get("status") if isinstance(current_glass, dict) else getattr(current_glass, "status", None)
        
        if glass_status != "Completed":
            return {
                "status": "Error",
                "message": _("The item must be completed before quality control."),
                "glass_item": current_glass,
            }

        if quality_data.has_failures():
            return self._handle_quality_failure(
                job_card, current_glass, quality_data, employee
            )

        glass_quality_data = current_glass.quality_data

        return {
            "status": "success",
            "message": _("Quality control completed"),
            "job_card": job_card.name,
            "quality_data": json.loads(glass_quality_data)
            if glass_quality_data
            else None,
        }

    def _handle_quality_failure(
        self,
        job_card: Dict[str, Any],
        current_glass: Dict[str, Any],
        quality_data: QualityData,
        employee: str,
    ) -> Dict[str, Any]:
        print("\n\n\n-- Handle Quality Failure --")
        correction_job = self._create_correction_job(
            job_card, current_glass, quality_data
        )

        # Get quality data directly from database
        glass_quality_data = frappe.db.get_value("CamListe", current_glass.glass_ref, "quality_data")
        # Removed job_card.save() - not needed as we're using SQL updates

        return {
            "status": "failed",
            "quality_status": "failed",
            "correction_job": correction_job.name,
            "quality_data": json.loads(glass_quality_data)
            if glass_quality_data
            else None,
        }

    def _create_correction_job(
        self,
        quality_job_card: Dict[str, Any],
        current_glass: Dict[str, Any],
        quality_data: Dict[str, Any],
    ) -> Dict[str, any]:
        try:
            print("\n\n\n-- Create Correction Job --")

            # Optimize: Update glass status before creating correction job to avoid extra save
            # Use direct SQL for better performance
            if quality_data:
                frappe.db.set_value(
                    "CamListe", 
                    current_glass.glass_ref, 
                    "quality_data", 
                    json.dumps(quality_data.__dict__)
                )

            correction_job = frappe.new_doc("Job Card")
            correction_job.update(
                {
                    "work_order": quality_job_card.work_order,
                    "operation": quality_job_card.operation,
                    "production_item": quality_job_card.production_item,
                    "for_quantity": 1,
                    "is_corrective_job_card": 1,
                    "for_job_card": quality_job_card.name,
                    "workstation": quality_job_card.workstation,
                    "workstation_type": quality_job_card.workstation_type,
                    "wip_warehouse": quality_job_card.wip_warehouse,
                    "custom_target_sanal_adet": current_glass.sanal_adet,
                    "custom_quality_job_card": quality_job_card.name,
                    "remarks": quality_data.overall_notes,
                }
            )
            glasses = [
                {
                    "glass_ref": current_glass.get("glass_ref"),
                    "order_no": current_glass.get("order_no"),
                    "stock_code": current_glass.get("stock_code"),
                    "poz_no": current_glass.get("poz_no"),
                    "sanal_adet": current_glass.get("sanal_adet"),
                    "status": "Pending",
                    "quality_data": current_glass.get("quality_data"),
                }
            ]

            correction_job.set("custom_glasses", glasses)
            correction_job.insert()
            
            # Update glass job card status after correction job is created
            frappe.db.sql("""
                UPDATE `tabCamListe Job Card`
                SET status = 'In Correction'
                WHERE parent = %s AND job_card_ref = %s
            """, (current_glass.glass_ref, quality_job_card.name))
            frappe.db.commit()
            
            return correction_job
        except Exception as e:
            frappe.log_error(f"Error creating correction job: {str(e)}")
            frappe.throw(_("Failed to create correction job"))

    def _handle_pending_item(
        self,
        job_card: Any,
        current_glass: Dict,
        related_glasses: List[Dict],
        employee: str,
    ) -> Dict[str, Any]:
        print("--- Handle Pending Item ---")

        # Optimize: Use SQL for status updates instead of document save
        if job_card.status != "Work In Progress":
            self._update_job_card_status_sql(job_card.name, "Work In Progress", employee)

        # Update glass status directly with SQL
        self._batch_update_glass_status([current_glass.glass_ref], job_card.name, "Completed")
        
        # Check completion status using SQL query (faster than loading all glasses)
        if self._is_sanal_adet_group_complete_sql(job_card.name, current_glass.sanal_adet):
            # Complete job using SQL
            self._complete_job_sql(job_card.name, 1)
            
            # Check if fully complete using SQL
            if self._is_job_fully_complete_sql(job_card.name):
                self._submit_job_card_sql(job_card.name)
            else:
                self._update_job_card_status_sql(job_card.name, "On Hold", None)
        else:
            self._update_job_card_status_sql(job_card.name, "On Hold", None)

        # Get quality data directly from database
        glass_quality_data = frappe.db.get_value("CamListe", current_glass.glass_ref, "quality_data")

        return {
            "status": "completed",
            "job_card": job_card.name,
            "glass": current_glass.glass_ref,
            "quality_data": json.loads(glass_quality_data)
            if glass_quality_data
            else None,
        }

    def _handle_in_progress_item(
        self,
        job_card: Any,
        current_glass: Dict,
    ) -> Dict[str, Any]:
        print("\n\n\n-- Handle In Progress --")

        # Update glass status directly with SQL
        self._batch_update_glass_status([current_glass.glass_ref], job_card.name, "Completed")
        
        # Check completion status using SQL query
        if self._is_sanal_adet_group_complete_sql(job_card.name, current_glass.sanal_adet):
            # Complete job using SQL
            self._complete_job_sql(job_card.name, 1)
            
            # Check if fully complete using SQL
            if self._is_job_fully_complete_sql(job_card.name):
                self._submit_job_card_sql(job_card.name)
            else:
                self._update_job_card_status_sql(job_card.name, "On Hold", None)
        else:
            self._update_job_card_status_sql(job_card.name, "On Hold", None)

        # Get quality data directly from database
        glass_quality_data = frappe.db.get_value("CamListe", current_glass.glass_ref, "quality_data")

        return {
            "status": "completed",
            "job_card": job_card.name,
            "glass": current_glass.glass_ref,
            "quality_data": json.loads(glass_quality_data)
            if glass_quality_data
            else None,
        }

    def _complete_glasses(self, job_card: Any, glasses: List[Dict]):
        # Optimize: Batch update glass statuses using SQL only - no document save needed
        glass_refs_to_update = [glass.glass_ref for glass in glasses]
        
        if glass_refs_to_update:
            self._batch_update_glass_status(glass_refs_to_update, job_card.name, "Completed")
        # Removed save_with_retry - SQL updates don't need document save

    def update_glass_job_card_status(
        self,
        glass_ref: str,
        job_card_name: str,
        status: Optional[str] = None,
        quality_data: Optional[QualityData] = None,
    ) -> None:
        # Optimize: Use direct SQL update for better performance
        if status:
            frappe.db.sql("""
                UPDATE `tabCamListe Job Card`
                SET status = %s
                WHERE parent = %s AND job_card_ref = %s
            """, (status, glass_ref, job_card_name))
            frappe.db.commit()
        
        if quality_data:
            frappe.db.set_value("CamListe", glass_ref, "quality_data", json.dumps(quality_data.__dict__))
            frappe.db.commit()
    
    def _batch_update_glass_status(
        self,
        glass_refs: List[str],
        job_card_name: str,
        status: str,
    ) -> None:
        """Optimized batch update for multiple glass statuses"""
        if not glass_refs:
            return
        
        # Use SQL for efficient batch update
        frappe.db.sql("""
            UPDATE `tabCamListe Job Card`
            SET status = %s
            WHERE parent IN %s AND job_card_ref = %s
        """, (status, tuple(glass_refs), job_card_name))
        frappe.db.commit()

    def _is_sanal_adet_group_complete(self, job_card: any, glass: Dict) -> bool:
        # Optimize: Use SQL query instead of iterating through all glasses
        return self._is_sanal_adet_group_complete_sql(job_card.name, glass.sanal_adet)

    def _get_related_glasses(self, job_card: Any, current_glass: Dict) -> List[Dict]:
        return [g for g in job_card.custom_glasses]

    def _get_current_glass(self, job_card: any, glass_name: str) -> Dict:
        """Get current glass from job card's custom_glasses child table"""
        if not hasattr(job_card, 'custom_glasses') or not job_card.custom_glasses:
            return None
        
        # Try exact match first
        glass = next(
            (g for g in job_card.custom_glasses if g.glass_ref == glass_name),
            None,
        )
        
        # If not found, try case-insensitive match (for tablet compatibility)
        if not glass:
            glass = next(
                (g for g in job_card.custom_glasses 
                 if g.glass_ref and g.glass_ref.lower() == glass_name.lower()),
                None,
            )
        
        return glass
    
    def _get_current_glass_fallback(self, glass_name: str, job_card_name: str) -> Optional[Dict]:
        """Fallback method to get glass data using SQL if not found in job card"""
        try:
            # Get glass data directly from database
            glass_data = frappe.db.sql("""
                SELECT 
                    jcg.glass_ref,
                    jcg.glass_operation_ref,
                    jcg.sanal_adet,
                    jcg.status,
                    cl.order_no,
                    cl.poz_no,
                    cl.stok_kodu as stock_code,
                    cl.quality_data
                FROM `tabOzerpan Job Card Glass` jcg
                INNER JOIN `tabCamListe` cl ON cl.name = jcg.glass_ref
                WHERE jcg.parent = %s 
                AND (jcg.glass_ref = %s OR jcg.glass_ref LIKE %s)
                LIMIT 1
            """, (job_card_name, glass_name, f"%{glass_name}%"), as_dict=True)
            
            if glass_data:
                return glass_data[0]
        except Exception as e:
            frappe.log_error(f"Error in _get_current_glass_fallback: {str(e)}")
        
        return None
    
    def _update_job_card_status_sql(self, job_card_name: str, status: str, employee: Optional[str] = None) -> None:
        """Optimized SQL-based job card status update"""
        current_time = frappe.utils.now()
        
        if status == "Work In Progress" and employee:
            # Check if actual_start_date exists
            actual_start_date = frappe.db.get_value("Job Card", job_card_name, "actual_start_date")
            
            if not actual_start_date:
                frappe.db.sql("""
                    UPDATE `tabJob Card`
                    SET status = %s, actual_start_date = %s, modified = %s
                    WHERE name = %s
                """, (status, current_time, current_time, job_card_name))
            else:
                frappe.db.sql("""
                    UPDATE `tabJob Card`
                    SET status = %s, modified = %s
                    WHERE name = %s
                """, (status, current_time, job_card_name))
            
            # Add time log entry
            max_idx = frappe.db.sql("""
                SELECT COALESCE(MAX(idx), 0) + 1 as next_idx
                FROM `tabJob Card Time Log`
                WHERE parent = %s
            """, (job_card_name,), as_dict=True)
            
            next_idx = max_idx[0].next_idx if max_idx else 1
            
            frappe.db.sql("""
                INSERT INTO `tabJob Card Time Log` 
                (name, parent, parenttype, parentfield, idx, from_time, employee, creation, modified, docstatus)
                VALUES (%s, %s, 'Job Card', 'time_logs', %s, %s, %s, %s, %s, 0)
            """, (
                frappe.generate_hash(),
                job_card_name,
                next_idx,
                current_time,
                employee,
                current_time,
                current_time,
            ))
        else:
            # For other statuses, just update status
            frappe.db.sql("""
                UPDATE `tabJob Card`
                SET status = %s, modified = %s
                WHERE name = %s
            """, (status, current_time, job_card_name))
        
        frappe.db.commit()
    
    def _complete_job_sql(self, job_card_name: str, qty: int) -> None:
        """Optimized SQL-based job completion"""
        current_time = frappe.utils.now()
        
        # Find open time log
        open_log = frappe.db.sql("""
            SELECT name FROM `tabJob Card Time Log`
            WHERE parent = %s AND to_time IS NULL
            ORDER BY idx DESC LIMIT 1
        """, (job_card_name,), as_dict=True)
        
        if open_log:
            frappe.db.sql("""
                UPDATE `tabJob Card Time Log`
                SET to_time = %s, completed_qty = %s, modified = %s
                WHERE name = %s
            """, (current_time, qty, current_time, open_log[0].name))
        
        frappe.db.commit()
    
    def _is_job_fully_complete_sql(self, job_card_name: str) -> bool:
        """Check job completion using SQL"""
        result = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(completed_qty), 0) as total_completed,
                (SELECT for_quantity FROM `tabJob Card` WHERE name = %s) as for_quantity
            FROM `tabJob Card Time Log`
            WHERE parent = %s AND completed_qty IS NOT NULL
        """, (job_card_name, job_card_name), as_dict=True)
        
        if result and result[0]:
            return result[0].total_completed >= (result[0].for_quantity or 0)
        return False
    
    def _is_sanal_adet_group_complete_sql(self, job_card_name: str, sanal_adet: str) -> bool:
        """Check sanal_adet group completion using SQL"""
        result = frappe.db.sql("""
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed
            FROM `tabOzerpan Job Card Glass`
            WHERE parent = %s AND sanal_adet = %s
        """, (job_card_name, sanal_adet), as_dict=True)
        
        if result and result[0]:
            return result[0].total > 0 and result[0].completed == result[0].total
        return False
    
    def _submit_job_card_sql(self, job_card_name: str) -> None:
        """Optimized SQL-based job card submission"""
        current_time = frappe.utils.now()
        
        # Update status to Completed
        frappe.db.sql("""
            UPDATE `tabJob Card`
            SET status = 'Completed', actual_end_date = %s, modified = %s
            WHERE name = %s
        """, (current_time, current_time, job_card_name))
        
        # Submit using document (required for Frappe workflow)
        try:
            job_card = frappe.get_doc("Job Card", job_card_name)
            job_card.submit()
        except Exception as e:
            frappe.log_error(f"Error submitting job card {job_card_name}: {str(e)}")
            raise
        
        frappe.db.commit()
