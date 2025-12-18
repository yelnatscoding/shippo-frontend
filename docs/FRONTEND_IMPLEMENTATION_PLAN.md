# Shipping Label Tool - Frontend Implementation Plan

## Project Overview

A web-based shipping label tool that allows comparing rates across multiple providers (EasyPost, Shippo, ShipEngine, Easyship), validating addresses, and purchasing shipping labels. Built for 1-2 users with easy deployment to Vercel's free tier.

## Architecture Summary

- **Frontend**: Static HTML/CSS/JavaScript (vanilla, no framework)
- **Backend**: Python serverless functions on Vercel
- **Database**: Vercel KV (Redis) for label history or JSON file storage
- **Hosting**: Vercel (free tier, git-based deployment)
- **Authentication**: None (internal tool)

## Project Structure

```
shippo-frontend/
├── public/
│   ├── index.html          # Main application shell
│   ├── style.css           # Custom styles (minimal, uses CDN Bootstrap)
│   └── app.js              # Frontend application logic
├── api/                    # Python serverless functions
│   ├── rates.py            # POST /api/rates - Get rates from all providers
│   ├── validate.py         # POST /api/validate - Validate shipping address
│   ├── purchase.py         # POST /api/purchase - Purchase shipping label
│   ├── history.py          # GET/POST /api/history - Label history CRUD
│   └── config.py           # Shared configuration loader
├── lib/                    # Existing Python shipping code (copied from backend)
│   ├── shippo_client.py
│   ├── easypost_client.py
│   ├── shipengine_client.py
│   ├── easyship_client.py
│   ├── models.py
│   └── utils.py
├── storage/                # Local storage for development
│   └── labels.json         # Label history (dev only)
├── requirements.txt        # Python dependencies
├── vercel.json            # Vercel configuration
├── package.json           # For Vercel build process
├── .env.local             # Local environment variables (not committed)
├── .env.production        # Production env template
└── README.md              # Setup and deployment instructions
```

## Implementation Phases

### Phase 1: Project Setup and Basic Structure (Day 1)

**Tasks:**
1. Create new repository `shippo-frontend`
2. Set up Vercel project structure
3. Copy existing Python clients to `lib/` directory
4. Create `vercel.json` configuration
5. Set up environment variables in Vercel dashboard
6. Create basic HTML structure with tabs
7. Deploy skeleton to verify Vercel setup works

**Deliverables:**
- Working Vercel deployment with "Hello World" API endpoint
- Basic HTML with tab navigation
- Environment variables configured

### Phase 2: Rate Comparison Feature (Day 2-3)

**Frontend Tasks:**
1. Create address input forms (from/to addresses)
2. Create parcel dimension inputs (length, width, height, weight)
3. Add "Compare Rates" button
4. Build results display with provider grouping (accordions)
5. Add loading states and error handling
6. Implement rate selection mechanism

**Backend Tasks:**
1. Implement `/api/rates` endpoint
2. Parallel calls to all 4 providers
3. Error handling for failed providers
4. Response formatting and sorting
5. Add caching layer (5-minute TTL)

**API Endpoint:**
```python
# api/rates.py
POST /api/rates
Request Body: {
  "from_address": {
    "name": "string",
    "street1": "string",
    "city": "string",
    "state": "string",
    "zip": "string",
    "country": "US"
  },
  "to_address": { ... },
  "parcel": {
    "length": 10,
    "width": 8,
    "height": 6,
    "weight": 2
  }
}

Response: {
  "success": true,
  "data": {
    "shippo": [
      {
        "id": "rate_abc123",
        "carrier": "USPS",
        "service": "Priority Mail",
        "price": 8.45,
        "currency": "USD",
        "estimated_days": 2,
        "provider": "shippo"
      }
    ],
    "easypost": [...],
    "shipengine": [...],
    "easyship": [...]
  },
  "errors": {
    "provider_name": "Error message if provider failed"
  }
}
```

### Phase 3: Address Validation Feature (Day 4)

**Frontend Tasks:**
1. Create address validation form
2. Display validation results (original vs suggested)
3. Add "Accept Suggestion" button
4. Show validation confidence score

**Backend Tasks:**
1. Implement `/api/validate` endpoint
2. Use best provider for validation (Shippo or EasyPost)
3. Format response with suggestions

**API Endpoint:**
```python
# api/validate.py
POST /api/validate
Request Body: {
  "address": {
    "street1": "string",
    "city": "string",
    "state": "string",
    "zip": "string",
    "country": "US"
  },
  "provider": "auto"  # or specific provider
}

Response: {
  "success": true,
  "data": {
    "is_valid": true,
    "confidence": "high",
    "original": { ... },
    "suggested": {
      "street1": "123 MAIN ST",
      "city": "ANYTOWN",
      "state": "CA",
      "zip": "12345-6789"
    },
    "messages": ["Address standardized", "ZIP+4 added"]
  }
}
```

### Phase 4: Label Purchase Feature (Day 5)

**Frontend Tasks:**
1. Display selected rate details
2. Add purchase confirmation dialog
3. Show purchase progress
4. Display label download link
5. Add "Download Label" button

**Backend Tasks:**
1. Implement `/api/purchase` endpoint
2. Purchase label from selected provider
3. Download PDF from provider
4. Store in Vercel Blob storage
5. Save to history

**API Endpoint:**
```python
# api/purchase.py
POST /api/purchase
Request Body: {
  "rate_id": "rate_abc123",
  "provider": "shippo",
  "format": "PDF"
}

Response: {
  "success": true,
  "data": {
    "tracking_number": "9405511206217459652862",
    "label_url": "/api/labels/download/label_123.pdf",
    "carrier": "USPS",
    "service": "Priority Mail",
    "cost": 8.45,
    "created_at": "2024-11-14T10:30:00Z"
  }
}
```

### Phase 5: Label History & Storage (Day 6)

**Frontend Tasks:**
1. Add history tab/section
2. Create history table (sortable, searchable)
3. Add re-download capability
4. Export to CSV functionality

**Backend Tasks:**
1. Implement `/api/history` endpoints (GET, POST)
2. Set up Vercel KV for persistence
3. Store: tracking, cost, date, provider, addresses
4. Implement history cleanup (>90 days)

**Storage Schema:**
```javascript
// Vercel KV structure
{
  "label:tracking:9405511206217459652862": {
    "id": "label_123",
    "tracking_number": "9405511206217459652862",
    "carrier": "USPS",
    "service": "Priority Mail",
    "cost": 8.45,
    "provider": "shippo",
    "created_at": "2024-11-14T10:30:00Z",
    "from_address": { ... },
    "to_address": { ... },
    "label_url": "blob_url_here"
  }
}
```

### Phase 6: UI Polish & Error Handling (Day 7)

**Tasks:**
1. Add comprehensive error handling
2. Implement retry logic for failed API calls
3. Add tooltips and help text
4. Mobile responsive design
5. Loading skeletons
6. Success/error toast notifications
7. Keyboard shortcuts (Tab navigation)
8. Print-friendly label display

### Phase 7: Testing & Documentation (Day 8)

**Tasks:**
1. Manual testing of all workflows
2. Create user documentation
3. API documentation
4. Deployment guide
5. Environment setup instructions
6. Troubleshooting guide

## Technical Implementation Details

### Frontend Technologies

**Core:**
- Vanilla JavaScript (ES6+)
- HTML5 semantic markup
- CSS3 with CSS Variables for theming

**Libraries (via CDN):**
- Bootstrap 5.3 (UI components)
- Axios (HTTP client)
- DayJS (date formatting)
- FileSaver.js (label downloads)

**Code Organization:**
```javascript
// app.js structure
const ShippingApp = {
  config: {
    apiUrl: '/api',
    providers: ['shippo', 'easypost', 'shipengine', 'easyship']
  },

  state: {
    currentTab: 'rates',
    selectedRate: null,
    ratesCache: {},
    history: []
  },

  init() {
    this.bindEvents();
    this.loadHistory();
    this.restoreFormData();
  },

  // Tab management
  tabs: {
    switch(tabName) { ... },
    show(tabName) { ... }
  },

  // API calls
  api: {
    getRates(fromAddr, toAddr, parcel) { ... },
    validateAddress(address) { ... },
    purchaseLabel(rateId, provider) { ... },
    getHistory() { ... }
  },

  // UI updates
  ui: {
    showLoading() { ... },
    hideLoading() { ... },
    showError(message) { ... },
    renderRates(rates) { ... }
  }
};
```

### Backend Implementation

**Serverless Function Template:**
```python
# api/rates.py
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))

from shippo_client import ShippoClient
from easypost_client import EasyPostClient
from models import Address, Parcel

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # CORS headers
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-type', 'application/json')

            # Parse request
            content_length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(content_length))

            # Validate input
            from_addr = Address(**body['from_address'])
            to_addr = Address(**body['to_address'])
            parcel = Parcel(**body['parcel'])

            # Get rates from all providers in parallel
            results = {}
            errors = {}

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(self._get_shippo_rates, from_addr, to_addr, parcel): 'shippo',
                    executor.submit(self._get_easypost_rates, from_addr, to_addr, parcel): 'easypost',
                    # ... other providers
                }

                for future in as_completed(futures):
                    provider = futures[future]
                    try:
                        results[provider] = future.result()
                    except Exception as e:
                        errors[provider] = str(e)

            # Return response
            self.end_headers()
            response = {
                'success': True,
                'data': results,
                'errors': errors
            }
            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            self.send_error(500, str(e))

    def _get_shippo_rates(self, from_addr, to_addr, parcel):
        client = ShippoClient(
            api_key=os.environ['SHIPPO_API_KEY'],
            test_mode=os.environ.get('SHIPPO_TEST_MODE', 'true') == 'true'
        )
        rates = client.get_rates(from_addr, to_addr, parcel)
        return [r.dict() for r in rates]
```

### Environment Variables

**Required in Vercel Dashboard:**
```bash
# Shipping Provider API Keys
EASYPOST_API_KEY=EZTEST_...
EASYPOST_TEST_MODE=true
SHIPPO_API_KEY=shippo_test_...
SHIPPO_TEST_MODE=true
SHIPENGINE_API_KEY=TEST_...
EASYSHIP_API_KEY=...

# Storage (optional)
VERCEL_KV_URL=...
VERCEL_KV_REST_API_URL=...
VERCEL_KV_REST_API_TOKEN=...
VERCEL_KV_REST_API_READ_ONLY_TOKEN=...

# Configuration
DEFAULT_LABEL_FORMAT=PDF
RATE_CACHE_TTL=300
```

### Vercel Configuration

**vercel.json:**
```json
{
  "functions": {
    "api/*.py": {
      "runtime": "python3.9",
      "maxDuration": 10
    }
  },
  "rewrites": [
    {
      "source": "/",
      "destination": "/public/index.html"
    }
  ],
  "env": {
    "PYTHONPATH": "/var/task/lib"
  }
}
```

**package.json:**
```json
{
  "name": "shippo-frontend",
  "version": "1.0.0",
  "scripts": {
    "dev": "vercel dev",
    "deploy": "vercel --prod"
  },
  "devDependencies": {
    "vercel": "^32.0.0"
  }
}
```

## Deployment Process

1. **Initial Setup:**
```bash
# Clone and setup
git clone <your-repo>
cd shippo-frontend

# Copy Python libs from original project
cp -r ../shippo-shipping-tool/shippo_tool/*.py lib/

# Install Vercel CLI
npm install -g vercel

# Login to Vercel
vercel login
```

2. **Configure Environment:**
```bash
# Create .env.local for development
cp .env.production .env.local
# Edit .env.local with your test API keys

# Link to Vercel project
vercel link

# Set production environment variables
vercel env add SHIPPO_API_KEY production
vercel env add EASYPOST_API_KEY production
# ... etc
```

3. **Deploy:**
```bash
# Development deployment
vercel

# Production deployment
vercel --prod
```

## Development Workflow

1. **Local Development:**
```bash
# Run Vercel dev server (includes serverless functions)
vercel dev
# Opens at http://localhost:3000
```

2. **Testing Providers:**
```bash
# Test individual endpoints
curl -X POST http://localhost:3000/api/rates \
  -H "Content-Type: application/json" \
  -d '{
    "from_address": {...},
    "to_address": {...},
    "parcel": {...}
  }'
```

3. **Debugging:**
- Check Vercel Functions logs in dashboard
- Use `console.log` in Python (appears in Vercel logs)
- Browser DevTools for frontend debugging

## Success Metrics

- [ ] All 4 providers return rates successfully
- [ ] Address validation works for US addresses
- [ ] Labels can be purchased and downloaded
- [ ] History persists between sessions
- [ ] Page loads in <2 seconds
- [ ] API responses in <5 seconds
- [ ] Works on mobile devices
- [ ] No exposed API keys in frontend

## Future Enhancements (Post-MVP)

1. **Batch Processing**
   - Upload CSV of addresses
   - Bulk rate comparison
   - Batch label generation

2. **Advanced Features**
   - Saved address book
   - Shipment tracking dashboard
   - Cost analytics and reporting
   - Email notifications for tracking

3. **Integration Options**
   - Webhook for tracking updates
   - CSV/Excel export
   - QuickBooks integration
   - Slack notifications

4. **Security (if needed later)**
   - Basic auth with shared password
   - API key management UI
   - Audit logging

## Risk Mitigation

**Risk**: Vercel 10-second timeout
- **Mitigation**: Implement provider timeout at 8 seconds, return partial results

**Risk**: API key exposure
- **Mitigation**: All keys in environment variables, never in frontend code

**Risk**: Rate limit from providers
- **Mitigation**: Implement caching layer, rate limiting on our endpoints

**Risk**: Label URL expiration
- **Mitigation**: Store labels in Vercel Blob storage for permanent access

## Support & Maintenance

- Monitor Vercel dashboard for errors
- Check provider status pages for outages
- Update Python dependencies quarterly
- Backup label history monthly
- Review API usage to stay within free tiers

---

## Quick Start Checklist

- [ ] Create GitHub repository
- [ ] Sign up for Vercel account
- [ ] Get API keys from all providers
- [ ] Copy Python code to lib/
- [ ] Deploy skeleton to Vercel
- [ ] Implement Phase 1 (Basic Structure)
- [ ] Implement Phase 2 (Rate Comparison)
- [ ] Implement Phase 3 (Address Validation)
- [ ] Implement Phase 4 (Label Purchase)
- [ ] Implement Phase 5 (History)
- [ ] Implement Phase 6 (Polish)
- [ ] Implement Phase 7 (Testing)
- [ ] Deploy to production
- [ ] Share URL with team member

---

This plan provides a complete roadmap for building your shipping label tool with approximately 8 days of focused development work.