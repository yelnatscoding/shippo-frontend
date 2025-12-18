# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Multi-carrier shipping tool with Python CLI backend and Vercel serverless web frontend. Compares rates and creates labels across Shippo, EasyPost, ShipEngine, and Easyship APIs.

## Architecture

```
shippo-shipping-tool/
├── shippo_tool/           # Python CLI package
│   ├── cli.py             # Click-based CLI commands
│   ├── models.py          # Pydantic data models
│   ├── *_client.py        # Provider API wrappers
│   └── config.py          # YAML config loader
├── shippo-frontend/       # Vercel web app
│   ├── api/               # Python serverless functions
│   ├── lib/               # Shared Python libraries
│   ├── public/            # Static assets (HTML/JS/CSS)
│   └── storage/           # Label history JSON
├── tests/                 # pytest test suite
├── labels/                # Generated shipping labels
└── config.yaml            # User configuration
```

## Tech Stack

- **Backend:** Python 3.12, Click, Rich, Pydantic v2, PyYAML
- **Frontend:** Vanilla JS, Bootstrap 5, Axios
- **APIs:** Shippo SDK v3, EasyPost SDK v9.4, ShipEngine SDK v1, Easyship
- **Deployment:** Vercel (Python serverless functions)
- **Storage:** Google Drive API (optional), local JSON

## Common Commands

```bash
# CLI usage
python -m shippo_tool rates --from-zip 91761 --to-zip 78263 --weight 13 --length 44 --width 29 --height 26
python -m shippo_tool create-label --rate-id <id> --output ./labels/
python -m shippo_tool validate --street "123 Main St" --city "Austin" --state TX --zip 78701

# Frontend development
cd shippo-frontend && vercel dev --listen 3000

# Testing
pytest tests/

# Deploy
cd shippo-frontend && vercel --prod
```

## Key Patterns

### Multi-Provider Abstraction
Each provider (Shippo, EasyPost, ShipEngine, Easyship) has a dedicated client class in `shippo_tool/*_client.py` and `shippo-frontend/lib/*_client.py`. All return standardized `Rate` and `ShippingLabel` Pydantic models.

### Parallel Rate Fetching
`shippo-frontend/api/rates.py` uses `ThreadPoolExecutor` to query all providers concurrently (up to 8 workers).

### Configuration Hierarchy
1. Environment variables (`.env`)
2. Config file (`config.yaml`)
3. CLI flags (override all)

## Data Models (Pydantic)

Core models in `shippo_tool/models.py` and `shippo-frontend/lib/models.py`:
- `Address`: name, street1, city, state, zip, country, phone, email
- `Parcel`: length, width, height, weight, distance_unit, mass_unit
- `Rate`: provider, carrier, service, amount, estimated_days
- `ShippingLabel`: tracking_number, label_url, carrier, cost

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/rates` | POST | Get rates from all providers |
| `/api/purchase` | POST | Purchase shipping label |
| `/api/validate` | POST | Validate address |
| `/api/history` | GET/POST | Label purchase history |

## Environment Variables

**IMPORTANT:** Never commit `.env` files. Required keys:
- `EASYPOST_API_KEY` - Test keys start with `EZTEST`, live with `EZAK`
- `SHIPPO_API_KEY` - Test keys start with `shippo_test_`
- `SHIPENGINE_API_KEY` - Test keys start with `TEST_`
- `EASYSHIP_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (optional) - For Google Drive integration
- `GOOGLE_DRIVE_FOLDER_ID` (optional)

## Testing

```bash
# Default test route: CA (91761) to TX (78263), 13 lbs, 44x29x26 inches
# Expected: 15-25 options, $12-$150 range, 3-20 days delivery
pytest tests/ -v
```

## Code Style

- Python: Type hints required, Pydantic for validation
- JS: Vanilla JS, no frameworks, use Bootstrap components
- All API responses return JSON with consistent error format
- Use Rich library for CLI output (tables, panels, spinners)

## Gotchas

- Vercel Python functions require `lib/` files included via `vercel.json`
- EasyPost requires `shipment_id` for label purchase (stored in Rate model)
- Signature confirmation surcharges vary by carrier (USPS $3.50, UPS $4.25, FedEx $4.00)
- Rate caching default: 300 seconds (configurable via `RATE_CACHE_TTL`)
