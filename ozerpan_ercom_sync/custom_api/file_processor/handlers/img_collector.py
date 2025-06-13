import os
import stat
from dataclasses import dataclass
from typing import Any, Dict, List

import frappe
import paramiko
from frappe import _


@dataclass
class SSHConnectionInfo:
    host: str
    user: str
    password: str


class ImgCollector:
    """Class for collecting images from remote PCs via SSH/SFTP."""

    def __init__(self):
        """Initialize the ImgCollector with configuration from frappe.conf."""
        self.config = frappe.conf
        self.remote_path: str = self.config["img_transfer_remote_dir"]
        self.local_dir: str = self.config["img_transfer_local_dir"]

        # Convert dict config to SSHConnectionInfo objects
        pc_list_config = self.config["img_collection_pc_list"]
        self.pc_list: List[SSHConnectionInfo] = [
            SSHConnectionInfo(host=pc["host"], user=pc["user"], password=pc["password"])
            for pc in pc_list_config
        ]

        # Set up local path
        site_path = frappe.get_site_path()
        self.local_path = site_path + self.local_dir

    def collect(self) -> Dict[str, Any]:
        """
        Collect images from all configured remote PCs.

        Returns:
            Dict containing status and results of the collection process.
        """
        print("\n\n-- Collecting Images -- (START)\n")

        # Ensure local directory exists
        os.makedirs(self.local_path, exist_ok=True)

        all_transferred_files = []
        errors = []

        for pc in self.pc_list:
            try:
                result = self._collect_from_pc(pc)
                if result["status"] == "success":
                    all_transferred_files.extend(result["files_transferred"])
                else:
                    errors.append(f"PC {pc.host}: {result['message']}")
            except Exception as e:
                error_msg = f"PC {pc.host}: {str(e)}"
                errors.append(error_msg)
                frappe.log_error(frappe.get_traceback(), _("Image Transfer Failed"))

        print("\n-- Collecting Images -- (END)\n\n")

        if errors:
            return {
                "status": "partial_success" if all_transferred_files else "error",
                "files_transferred": all_transferred_files,
                "errors": errors,
            }
        else:
            return {"status": "success", "files_transferred": all_transferred_files}

    def _collect_from_pc(self, pc: SSHConnectionInfo) -> Dict[str, Any]:
        """
        Collect images from a single remote PC.

        Args:
            pc: SSHConnectionInfo containing PC connection information

        Returns:
            Dict containing status and results for this specific PC.
        """
        source_host = pc.host
        username = pc.user
        password = pc.password

        print(f"Connecting to {source_host}...")

        try:
            # SSH Connection
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(source_host, username=username, password=password)

            # SCP - Download Files
            sftp = ssh.open_sftp()
            file_list = sftp.listdir(self.remote_path)

            transferred_files = []
            for item in file_list:
                remote_file = self.remote_path + item

                # Check if item is a regular file (not a directory)
                try:
                    file_stat = sftp.stat(remote_file)
                    if stat.S_ISREG(file_stat.st_mode):  # Only transfer regular files
                        local_file = os.path.join(self.local_path, item)
                        sftp.get(remote_file, local_file)
                        transferred_files.append(item)
                        # sftp.remove(remote_file)  # delete after transfer
                    else:
                        print(f"Skipping directory/non-file: {item}")
                except Exception as e:
                    print(f"Error checking {item}: {str(e)}")
                    continue

            print(
                f"Files from {source_host}:{self.remote_path} transferred to: {self.local_path}"
            )

            sftp.close()
            ssh.close()

            return {"status": "success", "files_transferred": transferred_files}

        except Exception as e:
            return {"status": "error", "message": str(e)}


def collect():
    """
    Legacy function for backward compatibility.
    Creates an ImgCollector instance and calls collect method.
    """
    collector = ImgCollector()
    return collector.collect()
