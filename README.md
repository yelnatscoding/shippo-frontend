# Shipping Label Tool - Frontend

A web-based shipping label comparison and purchase tool that integrates with multiple shipping providers (Shippo, EasyPost, ShipEngine, Easyship) and automatically stores labels in Google Drive.

## Features

- **Compare Rates**: Get shipping rates from all providers simultaneously
- **Validate Addresses**: Ensure accurate delivery addresses before purchasing
- **Purchase Labels**: Buy shipping labels with one click
- **Google Drive Integration**: Automatically upload labels to Google Drive for permanent storage
- **Label History**: Track all purchased labels with searchable history
- **Package Presets**: Quick selection for common box sizes
- **Ship Again**: Copy previous shipment details with one click

## Tech Stack

- **Frontend**: Vanilla JavaScript, Bootstrap 5, Axios
- **Backend**: Python serverless functions on Vercel
- **Storage**: Google Drive (labels), JSON file (metadata)
- **APIs**: Shippo, EasyPost, ShipEngine, Easyship

## Prerequisites

1. **Vercel Account**: Sign up at [vercel.com](https://vercel.com)
2. **Shipping Provider API Keys**: Get test/production keys from:
   - [Shippo](https://goshippo.com)
   - [EasyPost](https://easypost.com)
   - [ShipEngine](https://shipengine.com)
   - [Easyship](https://easyship.com)
3. **Google Cloud Account**: For Google Drive integration

## Installation

### 1. Clone the Repository

```bash
cd /home/stan/Desktop/code/shippo-shipping-tool/shippo-frontend
```

### 2. Install Vercel CLI

```bash
npm install -g vercel
```

### 3. Set Up Google Drive (Optional but Recommended)

#### Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project "shipping-labels"
3. Enable Google Drive API

#### Create Service Account

1. Go to IAM & Admin > Service Accounts
2. Create service account "shipping-label-uploader"
3. Download JSON key file
4. Copy the entire JSON content (you'll need it for environment variables)

#### Setup Drive Folder

1. Create folder in your Google Drive: "Shipping Labels"
2. Share with service account email (e.g., `shipping-label-uploader@project-id.iam.gserviceaccount.com`)
3. Give "Editor" permissions
4. Copy the folder ID from the URL:
   - URL: `https://drive.google.com/drive/folders/1ABC123xyz`
   - Folder ID: `1ABC123xyz`

### 4. Set Up Environment Variables

Create a `.env.local` file for local development:

```bash
cp .env.example .env.local
```

Edit `.env.local` with your actual API keys:

```bash
# Shipping Provider API Keys
EASYPOST_API_KEY=EZTEST_your_test_key_here
EASYPOST_TEST_MODE=true
SHIPPO_API_KEY=shippo_test_your_key_here
SHIPPO_TEST_MODE=true
SHIPENGINE_API_KEY=TEST_your_key_here
EASYSHIP_API_KEY=your_easyship_key_here

# Google Drive Integration (paste entire JSON key)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...","private_key":"..."}
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here

# Configuration
DEFAULT_LABEL_FORMAT=PDF
RATE_CACHE_TTL=300
```

## Local Development

### Run Development Server

```bash
vercel dev
```

The app will be available at `http://localhost:3000`

### Test the Application

1. **Compare Rates**:
   - Enter a destination address
   - Select package size (or use presets)
   - Click "Compare Rates"
   - View rates from all providers

2. **Validate Address**:
   - Go to "Validate Address" tab
   - Enter address details
   - Click "Validate Address"
   - Accept suggested corrections if any

3. **Purchase Label**:
   - After comparing rates, click "Purchase" on a rate
   - Label will be purchased and uploaded to Google Drive
   - Download link provided immediately

4. **View History**:
   - Go to "Label History" tab
   - See all purchased labels
   - Click "Ship Again" to copy details

## Deployment to Vercel

### 1. Link to Vercel

```bash
vercel link
```

Follow the prompts to create or link a Vercel project.

### 2. Set Production Environment Variables

You need to set environment variables in Vercel dashboard:

```bash
# Or use CLI
vercel env add SHIPPO_API_KEY production
vercel env add EASYPOST_API_KEY production
vercel env add SHIPENGINE_API_KEY production
vercel env add EASYSHIP_API_KEY production
vercel env add GOOGLE_SERVICE_ACCOUNT_JSON production
vercel env add GOOGLE_DRIVE_FOLDER_ID production
vercel env add DEFAULT_LABEL_FORMAT production
```

**Important**: For `GOOGLE_SERVICE_ACCOUNT_JSON`, paste the entire JSON key file content as a single line.

### 3. Deploy

```bash
# Preview deployment
vercel

# Production deployment
vercel --prod
```

### 4. Access Your App

After deployment, Vercel will provide a URL like:
- `https://shippo-frontend-username.vercel.app`

You can also add a custom domain in Vercel dashboard.

## Project Structure

```
shippo-frontend/
├── public/
│   ├── index.html          # Main HTML file
│   ├── style.css           # Custom styles
│   └── app.js              # Frontend JavaScript
├── api/
│   ├── rates.py            # Get rates endpoint
│   ├── validate.py         # Validate address endpoint
│   ├── purchase.py         # Purchase label endpoint
│   ├── history.py          # Label history endpoint
│   └── config.py           # Shared configuration
├── lib/
│   ├── google_drive_uploader.py  # Google Drive integration
│   ├── shippo_client.py    # Shippo API client
│   ├── easypost_client.py  # EasyPost API client
│   ├── shipengine_client.py # ShipEngine API client
│   ├── easyship_client.py  # Easyship API client
│   ├── models.py           # Pydantic data models
│   └── utils.py            # Utility functions
├── storage/
│   └── labels.json         # Label history storage
├── docs/
│   ├── FRONTEND_IMPLEMENTATION_PLAN.md
│   ├── IMPLEMENTATION_PLAN_ADDENDUM.md
│   └── GOOGLE_DRIVE_INTEGRATION.md
├── vercel.json            # Vercel configuration
├── requirements.txt       # Python dependencies
├── package.json          # Node.js configuration
└── README.md            # This file
```

## API Endpoints

### POST /api/rates

Get shipping rates from all providers.

**Request:**
```json
{
  "from_address": { ... },
  "to_address": { ... },
  "parcel": {
    "length": 10,
    "width": 8,
    "height": 6,
    "weight": 2
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "shippo": [ ... ],
    "easypost": [ ... ],
    "shipengine": [ ... ],
    "easyship": [ ... ]
  },
  "errors": {}
}
```

### POST /api/validate

Validate shipping address.

**Request:**
```json
{
  "address": {
    "street1": "123 Main St",
    "city": "San Francisco",
    "state": "CA",
    "zip": "94102"
  }
}
```

### POST /api/purchase

Purchase shipping label.

**Request:**
```json
{
  "rate_id": "rate_abc123",
  "provider": "shippo",
  "format": "PDF",
  "from_address": { ... },
  "to_address": { ... }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "tracking_number": "9405511206...",
    "carrier": "USPS",
    "cost": 8.45,
    "google_drive_link": "https://drive.google.com/...",
    ...
  }
}
```

### GET /api/history

Get label purchase history.

### POST /api/history

Save label to history.

## Troubleshooting

### Issue: "No rates found"

**Solutions:**
- Check that API keys are set correctly
- Verify addresses are valid US addresses
- Ensure package dimensions are reasonable
- Check Vercel function logs for errors

### Issue: "Google Drive upload failed"

**Solutions:**
- Verify service account JSON is correct
- Check that Drive folder is shared with service account
- Ensure folder ID is correct
- Check Vercel logs for specific error

### Issue: "Function timeout"

**Solutions:**
- This means providers are taking too long
- Check provider status pages
- Try again (providers may be slow)
- Reduce number of providers in code if needed

### Issue: "CORS errors in local development"

**Solutions:**
- Make sure you're using `vercel dev` (not a regular Python server)
- Check that CORS headers are set in API endpoints
- Clear browser cache

## Support

For issues or questions:
1. Check the implementation plan docs in `docs/`
2. Review Vercel function logs in dashboard
3. Check provider status pages
4. Review browser console for errors

## License

MIT License - feel free to modify and use as needed.

## Acknowledgments

- Built with Vercel serverless functions
- Integrated with Shippo, EasyPost, ShipEngine, and Easyship APIs
- Google Drive for permanent label storage
