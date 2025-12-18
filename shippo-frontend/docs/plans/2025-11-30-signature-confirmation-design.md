# Signature Confirmation Pricing Feature

## Overview

Add signature confirmation pricing to the shipping rates display, showing two columns: base rate and rate with signature confirmation.

## UI Design

**Layout Structure:**
- **Tabs**: Provider tabs (Shippo, EasyPost, ShipEngine, Easyship)
- **Accordions**: Within each tab, carrier accordions (USPS, UPS, FedEx)
- **Tables**: Within each accordion, service table with signature columns

```
[Shippo] [EasyPost] [ShipEngine] [Easyship]  <-- tabs
         |
         v
┌─ USPS ──────────────────────────────────────┐
│ Service        | No Sig    | With Sig       │
│ Priority Mail  | $8.50 Buy | $11.25 Buy     │
│ Ground Advtg   | $5.20 Buy | N/A            │
└─────────────────────────────────────────────┘
┌─ UPS ───────────────────────────────────────┐
│ Service        | No Sig    | With Sig       │
│ Ground         | $12.00 Buy| $15.50 Buy     │
└─────────────────────────────────────────────┘
```

- **No Signature column**: Base rate with purchase button
- **With Signature column**: Rate + signature fee with purchase button, or "N/A" if unsupported
- Rows sorted by base price (cheapest first)

## API Changes

### Rates Endpoint

Two parallel requests per provider:
1. Base rate (no signature)
2. Rate with `signature_confirmation: "STANDARD"`

Response structure:
```json
{
  "shippo": {
    "base": [rate1, rate2, ...],
    "signature": [rate1, rate2, ...]
  }
}
```

Frontend matches rates by `servicelevel_token` to display side-by-side.

### Purchase Endpoint

Request changes:
```json
{ "rate_id": "xxx", "provider": "shippo", "signature": true }
```

## Files to Modify

1. `lib/shippo_client.py` - Add signature option to `get_rates()` and `purchase_label()`
2. `lib/easypost_client.py` - Same changes
3. `lib/shipengine_client.py` - Same changes
4. `lib/easyship_client.py` - Same changes
5. `api/rates.py` - Fetch base + signature rates in parallel
6. `api/purchase.py` - Accept signature parameter
7. `public/app.js` - Render table layout, pass signature flag on purchase
8. `public/style.css` - Table styling
