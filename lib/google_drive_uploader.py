import os
import json
import io
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload


class GoogleDriveUploader:
    """
    Upload shipping label PDFs to Google Drive for permanent storage
    """

    def __init__(self):
        # Service account credentials from environment variable
        creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not creds_json:
            raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable")

        creds_dict = json.loads(creds_json)
        self.creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        self.service = build('drive', 'v3', credentials=self.creds)

        # Get folder ID from environment
        self.folder_id = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')

    def upload_label(self, pdf_content, tracking_number, carrier, to_name, service_name=None):
        """
        Upload shipping label PDF to Google Drive

        Args:
            pdf_content (bytes): PDF bytes from shipping provider
            tracking_number (str): Tracking number for filename
            carrier (str): Carrier name (USPS, FedEx, etc)
            to_name (str): Recipient name for organization
            service_name (str, optional): Service level (Priority, Express, etc)

        Returns:
            dict: {
                'file_id': Google Drive file ID,
                'web_link': Shareable link to view/download,
                'name': Filename in Drive
            }
        """
        # Create organized filename
        date_str = datetime.now().strftime('%Y-%m-%d')
        safe_name = to_name.replace(' ', '_').replace('/', '_')[:30]  # Limit length

        service_part = f"_{service_name}" if service_name else ""
        filename = f"{date_str}_{carrier}{service_part}_{tracking_number}_{safe_name}.pdf"

        # Create file metadata
        file_metadata = {
            'name': filename,
            'description': f'Shipping label - {carrier} to {to_name}',
            'properties': {
                'tracking_number': tracking_number,
                'carrier': carrier,
                'recipient': to_name,
                'created_date': date_str
            }
        }

        # Add to folder if folder ID is provided
        if self.folder_id:
            file_metadata['parents'] = [self.folder_id]

        # Upload file
        media = MediaInMemoryUpload(
            io.BytesIO(pdf_content),
            mimetype='application/pdf',
            resumable=True
        )

        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink,webContentLink,name'
        ).execute()

        # Make file shareable (view-only for anyone with link)
        self.service.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        return {
            'file_id': file['id'],
            'web_link': file.get('webViewLink'),
            'download_link': file.get('webContentLink'),
            'name': file['name']
        }

    def create_monthly_folder(self):
        """
        Create or get folder for current month
        Returns folder ID for current month (YYYY-MM format)
        """
        folder_name = datetime.now().strftime('%Y-%m')

        # Check if folder exists
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if self.folder_id:
            query += f" and '{self.folder_id}' in parents"

        results = self.service.files().list(
            q=query,
            fields='files(id, name)',
            spaces='drive'
        ).execute()

        folders = results.get('files', [])

        if folders:
            return folders[0]['id']
        else:
            # Create new folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            if self.folder_id:
                file_metadata['parents'] = [self.folder_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

            return folder['id']

    def search_labels(self, tracking_number=None, date_from=None):
        """
        Search for labels in Drive

        Args:
            tracking_number (str, optional): Search by tracking number
            date_from (str, optional): Search labels from date (YYYY-MM-DD)

        Returns:
            list: List of matching files
        """
        query_parts = ["mimeType='application/pdf'", "trashed=false"]

        if self.folder_id:
            query_parts.append(f"'{self.folder_id}' in parents")

        if tracking_number:
            query_parts.append(f"properties has {{ key='tracking_number' and value='{tracking_number}' }}")

        if date_from:
            query_parts.append(f"createdTime >= '{date_from}T00:00:00'")

        query = " and ".join(query_parts)

        results = self.service.files().list(
            q=query,
            fields='files(id, name, webViewLink, createdTime, properties)',
            orderBy='createdTime desc',
            pageSize=50
        ).execute()

        return results.get('files', [])
