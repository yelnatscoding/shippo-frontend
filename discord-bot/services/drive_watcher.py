"""Google Drive watcher service"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging

logger = logging.getLogger(__name__)


class DriveWatcher:
    """Watch Google Drive folders for changes"""

    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    def __init__(self):
        creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")

        try:
            creds_dict = json.loads(creds_json) if creds_json else {}
        except json.JSONDecodeError:
            creds_dict = {}

        if not creds_dict or not creds_dict.get("type"):
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not configured or invalid")

        credentials = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=self.SCOPES
        )
        self.service = build("drive", "v3", credentials=credentials)
        self.file_cache: Dict[str, Dict] = {}  # file_id -> file metadata
        self.initialized_folders: set = set()  # folders that have been seeded
        logger.info("Drive watcher initialized")

    @staticmethod
    def _parse_modified_time(mod_time) -> Optional[datetime]:
        """Normalize modifiedTime to datetime for reliable comparison"""
        if mod_time is None:
            return None
        if isinstance(mod_time, datetime):
            return mod_time.replace(microsecond=0)
        if isinstance(mod_time, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    return datetime.strptime(mod_time, fmt).replace(microsecond=0)
                except ValueError:
                    continue
        return None

    def seed_cache_from_db(self, db_files: List[Dict]):
        """Seed the in-memory cache from database records to avoid duplicate notifications on restart"""
        for f in db_files:
            file_id = f.get("file_id")
            if file_id:
                self.file_cache[file_id] = {
                    "id": file_id,
                    "name": f.get("name"),
                    "mimeType": f.get("mime_type"),
                    "modifiedTime": f.get("modified_time"),
                    "webViewLink": f.get("web_view_link"),
                    "folder_id": f.get("folder_id"),
                    "folder_name": f.get("folder_name"),
                }
        logger.info(f"Seeded drive cache with {len(db_files)} files from database")

    def get_folder_files(self, folder_id: str) -> List[Dict[str, Any]]:
        """Get all files in a folder"""
        files = []
        page_token = None

        try:
            while True:
                response = self.service.files().list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)",
                    pageToken=page_token
                ).execute()

                files.extend(response.get("files", []))
                page_token = response.get("nextPageToken")

                if not page_token:
                    break
        except Exception as e:
            logger.error(f"Error getting folder files: {e}")

        return files

    def check_for_changes(
        self,
        folder_id: str,
        folder_name: str,
        notify_on: List[str],
        file_types: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Check folder for changes since last check.
        Returns dict with 'created', 'modified', 'deleted' lists.
        On first check for a folder, silently populates cache without reporting changes.
        """
        changes = {"created": [], "modified": [], "deleted": []}

        current_files = self.get_folder_files(folder_id)
        current_ids = {f["id"] for f in current_files}
        cached_ids = {fid for fid, meta in self.file_cache.items() if meta.get("folder_id") == folder_id}

        # First time seeing this folder - populate cache silently
        first_run = folder_id not in self.initialized_folders
        if first_run:
            self.initialized_folders.add(folder_id)

        # Filter by file types if specified
        filtered_files = current_files
        if file_types:
            extensions = [f".{ft.lower().lstrip('.')}" for ft in file_types]
            filtered_files = [
                f for f in current_files
                if any(f.get("name", "").lower().endswith(ext) for ext in extensions)
            ]

        for file in filtered_files:
            file["folder_id"] = folder_id
            file["folder_name"] = folder_name
            file_id = file["id"]

            if file_id not in self.file_cache:
                # New file - only notify if not first run
                if not first_run and "created" in notify_on:
                    changes["created"].append(file)
                self.file_cache[file_id] = file

            else:
                # Check if modified (normalize timestamps for reliable comparison)
                cached = self.file_cache[file_id]
                new_time = self._parse_modified_time(file.get("modifiedTime"))
                old_time = self._parse_modified_time(cached.get("modifiedTime"))
                if new_time != old_time:
                    if not first_run and "modified" in notify_on:
                        changes["modified"].append(file)
                    self.file_cache[file_id] = file

        # Check for deleted files (only if not first run)
        if not first_run and "deleted" in notify_on:
            for fid in cached_ids - current_ids:
                if fid in self.file_cache:
                    changes["deleted"].append(self.file_cache[fid])
                    del self.file_cache[fid]

        if first_run:
            logger.info(f"Initial scan for '{folder_name}': cached {len(filtered_files)} files")

        return changes

    def get_file_link(self, file_id: str) -> Optional[str]:
        """Get web view link for a file"""
        try:
            file = self.service.files().get(
                fileId=file_id, fields="webViewLink"
            ).execute()
            return file.get("webViewLink")
        except Exception as e:
            logger.error(f"Error getting file link: {e}")
            return None
