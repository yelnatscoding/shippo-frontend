# Google Drive Integration for Label Storage

## Overview

Instead of complex storage solutions, we'll automatically upload shipping labels to Google Drive, providing permanent, free, organized storage that's accessible to your team.

## Integration Approaches

### Option 1: Service Account (Recommended for Simplicity)
**How it works:**
- Create a Google Cloud service account
- Share a Google Drive folder with the service account email
- Upload labels directly from Python serverless functions

**Pros:**
- No user authentication needed
- Works seamlessly in background
- One-time setup

**Cons:**
- Labels go to a shared folder (not individual user drives)

### Option 2: OAuth2 Flow (If you need user-specific folders)
**How it works:**
- User authenticates with Google once
- Store refresh token
- Upload to user's personal Drive

**Pros:**
- Labels in each user's Drive
- More "proper" integration

**Cons:**
- More complex setup
- Need to handle token refresh

## Implementation Plan (Service Account Approach)

### Step 1: Google Cloud Setup

1. **Create Google Cloud Project:**
   - Go to https://console.cloud.google.com
   - Create new project "shipping-labels"
   - Enable Google Drive API

2. **Create Service Account:**
   ```bash
   # In Google Cloud Console
   - Go to IAM & Admin > Service Accounts
   - Create service account "shipping-label-uploader"
   - Download JSON key file
   ```

3. **Setup Drive Folder:**
   - Create folder in your Google Drive: "Shipping Labels"
   - Share with service account email (e.g., shipping-label-uploader@project.iam.gserviceaccount.com)
   - Give "Editor" permissions

### Step 2: Python Implementation

**Install dependency:**
```txt
# requirements.txt (add this line)
google-api-python-client==2.100.0
google-auth==2.23.0
```

**Google Drive upload module:**
```python
# lib/google_drive_uploader.py
import os
import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaInMemoryUpload
import io

class GoogleDriveUploader:
    def __init__(self):
        # Service account credentials from environment variable
        creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not creds_json:
            raise ValueError("Missing Google service account credentials")

        creds_dict = json.loads(creds_json)
        self.creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        self.service = build('drive', 'v3', credentials=self.creds)

        # Get folder ID from environment
        self.folder_id = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')

    def upload_label(self, pdf_content, tracking_number, carrier, to_name):
        """
        Upload shipping label PDF to Google Drive

        Args:
            pdf_content: PDF bytes from shipping provider
            tracking_number: Tracking number for filename
            carrier: Carrier name (USPS, FedEx, etc)
            to_name: Recipient name for organization

        Returns:
            dict: {
                'file_id': Google Drive file ID,
                'web_link': Shareable link to view/download,
                'name': Filename in Drive
            }
        """
        # Create organized filename
        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = f"{date_str}_{carrier}_{tracking_number}_{to_name.replace(' ', '_')}.pdf"

        # Create file metadata
        file_metadata = {
            'name': filename,
            'parents': [self.folder_id] if self.folder_id else [],
            'description': f'Shipping label - {carrier} to {to_name}'
        }

        # Upload file
        media = MediaInMemoryUpload(
            io.BytesIO(pdf_content),
            mimetype='application/pdf',
            resumable=True
        )

        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink,name'
        ).execute()

        # Make file shareable (optional - remove if you want private)
        self.service.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        return {
            'file_id': file['id'],
            'web_link': file.get('webViewLink'),
            'name': file['name']
        }

    def create_monthly_folder(self):
        """
        Optional: Organize labels into monthly folders
        Returns folder ID for current month
        """
        folder_name = datetime.now().strftime('%Y-%m Shipping Labels')

        # Check if folder exists
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
        if self.folder_id:
            query += f" and '{self.folder_id}' in parents"

        results = self.service.files().list(
            q=query,
            fields='files(id, name)'
        ).execute()

        folders = results.get('files', [])

        if folders:
            return folders[0]['id']
        else:
            # Create new folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [self.folder_id] if self.folder_id else []
            }
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            return folder['id']
```

### Step 3: Update Purchase Endpoint

```python
# api/purchase.py
import os
import json
import requests
from lib.google_drive_uploader import GoogleDriveUploader

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # ... existing purchase logic ...

            # After purchasing label from provider
            label = client.purchase_label(rate_id, format='PDF')

            # Download PDF from provider's temporary URL
            pdf_response = requests.get(label.label_url)
            pdf_content = pdf_response.content

            # Upload to Google Drive
            try:
                uploader = GoogleDriveUploader()
                drive_result = uploader.upload_label(
                    pdf_content=pdf_content,
                    tracking_number=label.tracking_number,
                    carrier=label.carrier,
                    to_name=to_address.name
                )

                # Include Drive link in response
                response_data = {
                    'success': True,
                    'data': {
                        'tracking_number': label.tracking_number,
                        'carrier': label.carrier,
                        'service': label.service,
                        'cost': label.cost,
                        'google_drive_link': drive_result['web_link'],
                        'google_drive_file_id': drive_result['file_id'],
                        'created_at': label.created_at
                    }
                }
            except Exception as drive_error:
                # If Drive fails, still return label but with warning
                print(f"Drive upload failed: {drive_error}")
                response_data = {
                    'success': True,
                    'data': {
                        'tracking_number': label.tracking_number,
                        # ... other fields ...
                        'warning': 'Label purchased but Drive upload failed'
                    }
                }

            # Return response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

        except Exception as e:
            self.send_error(500, str(e))
```

### Step 4: Frontend Display

```javascript
// app.js - Display Drive link after purchase
function displayPurchaseSuccess(result) {
  const successHTML = `
    <div class="alert alert-success">
      <h4>Label Purchased Successfully!</h4>
      <p><strong>Tracking:</strong> ${result.tracking_number}</p>
      <p><strong>Cost:</strong> $${result.cost}</p>
      <p><strong>Carrier:</strong> ${result.carrier} - ${result.service}</p>

      <div class="mt-3">
        ${result.google_drive_link ? `
          <a href="${result.google_drive_link}"
             target="_blank"
             class="btn btn-primary">
            <i class="bi bi-cloud-download"></i> Open in Google Drive
          </a>
        ` : `
          <button onclick="downloadLabelBackup('${result.tracking_number}')"
                  class="btn btn-secondary">
            <i class="bi bi-download"></i> Download PDF
          </button>
        `}

        <button onclick="printLabel('${result.google_drive_link || result.label_url}')"
                class="btn btn-outline-primary">
          <i class="bi bi-printer"></i> Print Label
        </button>
      </div>
    </div>
  `;

  document.getElementById('purchase-result').innerHTML = successHTML;

  // Save to history with Drive link
  saveToHistory({
    ...result,
    google_drive_link: result.google_drive_link
  });
}

// Helper to open print dialog for Drive PDF
function printLabel(url) {
  window.open(url + '?print=true', '_blank');
}
```

### Step 5: Environment Variables

```bash
# Add to Vercel environment variables

# Google Service Account JSON (entire JSON key file as string)
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}'

# Google Drive Folder ID (from folder URL)
# Example: If folder URL is https://drive.google.com/drive/folders/1ABC123xyz
# Then folder ID is: 1ABC123xyz
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
```

## Folder Organization Options

### Option A: Flat Structure (Simplest)
```
Shipping Labels/
├── 2024-11-14_USPS_9405511_John_Doe.pdf
├── 2024-11-14_FedEx_7845632_Jane_Smith.pdf
└── 2024-11-15_UPS_1Z999AA_Bob_Wilson.pdf
```

### Option B: Monthly Folders (Recommended)
```
Shipping Labels/
├── 2024-11/
│   ├── 2024-11-14_USPS_9405511_John_Doe.pdf
│   └── 2024-11-15_UPS_1Z999AA_Bob_Wilson.pdf
└── 2024-12/
    └── 2024-12-01_FedEx_7845632_Alice_Brown.pdf
```

### Option C: Carrier-Based Organization
```
Shipping Labels/
├── USPS/
│   └── 2024-11-14_9405511_John_Doe.pdf
├── FedEx/
│   └── 2024-11-15_7845632_Jane_Smith.pdf
└── UPS/
    └── 2024-11-14_1Z999AA_Bob_Wilson.pdf
```

## Benefits of Google Drive Integration

1. **Permanent Storage**: Labels never expire
2. **Team Access**: Share folder with team members
3. **Search**: Google Drive's search finds labels by tracking number
4. **Mobile Access**: View labels on phone via Drive app
5. **Automatic Backup**: Google handles backups
6. **Cost**: Free up to 15GB (thousands of labels)
7. **API Reliability**: Google Drive API is very stable

## Alternative: Google Drive Direct Link in History

If you don't want automatic upload, you can:
1. Download label locally
2. Manually upload to Drive
3. Store the Drive share link in your history

```javascript
// Add manual Drive link field to history
function addDriveLink(trackingNumber) {
  const driveLink = prompt('Paste Google Drive link for this label:');
  if (driveLink) {
    updateHistoryItem(trackingNumber, { google_drive_link: driveLink });
  }
}
```

## Security Considerations

1. **Service Account Key**: Store securely in Vercel environment
2. **Folder Permissions**: Only share with service account and team
3. **File Permissions**: Can keep private or make shareable
4. **Sensitive Data**: Labels contain addresses - consider privacy

## Setup Checklist

- [ ] Create Google Cloud project
- [ ] Enable Google Drive API
- [ ] Create service account and download JSON key
- [ ] Create "Shipping Labels" folder in Drive
- [ ] Share folder with service account email
- [ ] Add JSON key to Vercel environment variables
- [ ] Add folder ID to Vercel environment variables
- [ ] Update requirements.txt with Google libraries
- [ ] Implement GoogleDriveUploader class
- [ ] Update purchase endpoint to upload labels
- [ ] Test upload functionality
- [ ] Update frontend to display Drive links

This integration provides reliable, permanent label storage with zero ongoing costs!