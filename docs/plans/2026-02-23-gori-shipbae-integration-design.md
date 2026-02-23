# Gori/ShipBae API Integration Design

## Overview

Integrate Gori Company's shipping API (ShipBae) as a fifth provider in the multi-carrier shipping tool. Gori offers 100+ carriers with proprietary Zone Skipping Optimization and exclusive USPS rates.

**API Base:** `https://api.goricompany.com/v2`
**Auth:** OAuth 2.0 (client_id + client_secret -> 12-hour bearer token)

## Decisions

- **Approach:** Direct REST client (same pattern as existing providers)
- **Duplicate rates:** Show all rates side-by-side across providers, no deduplication
- **Token caching:** In-memory with TTL (module-level variable, 5-min expiry buffer)
- **Scope:** Rates + Labels + Address validation (full parity)
- **Ship date:** Backend defaults to today (no frontend changes)

## New File: `shippo-frontend/lib/gori_client.py`

Class: `GoriClient`

### Token Management
- Module-level `_token_cache = {"token": None, "expires_at": 0}`
- `_get_token()` calls `POST /auth/token` with client credentials
- Returns cached token if still valid (12h TTL, refresh 5 min before expiry)

### Methods
- `__init__(client_id, client_secret, test_mode)` — reads from env: `GORI_CLIENT_ID`, `GORI_CLIENT_SECRET`, `GORI_TEST_MODE`
- `get_rates(from_address, to_address, parcel, signature_confirmation) -> List[Rate]` — calls `POST /shipments/rates`, sets `ship_date` to today, maps response to Rate models with `provider="gori"`
- `purchase_label(rate_id, label_format, signature_confirmation) -> ShippingLabel` — calls `POST /shipments`, maps response to ShippingLabel model
- `validate_address(address) -> ValidationResult` — calls `POST /addresses`, maps response to ValidationResult model

## Wiring: `api/rates.py`

- Add `_get_gori_rates()` method
- Gate on `os.environ.get('GORI_CLIENT_ID')`
- Submit 2 futures to ThreadPoolExecutor (base + signature rates)
- Results under `data["gori"]["base"]` and `data["gori"]["signature"]`

## Wiring: `api/purchase.py`

- Add `_purchase_gori_label()` method
- Add `elif provider == 'gori':` branch in routing

## Wiring: `api/validate.py`

- Add Gori as another validation provider with env-var gating

## Environment Variables

- `GORI_CLIENT_ID` — OAuth client ID
- `GORI_CLIENT_SECRET` — OAuth client secret
- `GORI_TEST_MODE` — optional, defaults to false (true = staging API)

## No Frontend Changes

The frontend dynamically renders rates from all providers. Gori rates will appear automatically tagged with `provider: "gori"`.
