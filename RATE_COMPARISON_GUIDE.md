# Rate Comparison Scripts

Quick and easy scripts to compare shipping rates between EasyPost and Shippo.

## Quick Start

### Check EasyPost Rates Only
```bash
python check_easypost_rates.py
```

### Check Shippo Rates Only
```bash
python check_shippo_rates.py
```

### Compare Both Side-by-Side
```bash
python compare_rates.py
```

## Customize Your Package

Edit the configuration at the top of each script:

```python
FROM_ADDRESS = {
    "name": "Sender",
    "street1": "123 Main St",
    "city": "Ontario",
    "state": "CA",
    "zip": "91761"
}

TO_ADDRESS = {
    "name": "Recipient",
    "street1": "123 Main St",
    "city": "Eagan",
    "state": "MN",
    "zip": "55124"
}

PACKAGE = {
    "weight": 1,      # pounds
    "length": 10,     # inches
    "width": 8,       # inches
    "height": 2       # inches
}
```

## Current Results (91761 → 55124, 1 lb)

**EasyPost Winner:** USPS Ground Advantage - **$4.95** (4 days)
- UPS Ground: $8.09
- USPS Priority (2-day): $12.59

**Shippo:** UPS Ground Saver - **$7.99**
- USPS Ground Advantage: $8.14
- USPS Priority (3-day): $12.59

**Winner:** EasyPost saves $3.04 over Shippo on cheapest option

## vs Your Current ShipStation Cost

- **ShipStation:** $14.63 (2-day FedEx)
- **EasyPost Equivalent:** $12.59 (2-day USPS Priority) - saves $2.04
- **Shippo Equivalent:** $12.59 (3-day USPS Priority) - saves $2.04
- **Best Ground:** $4.95 (EasyPost) - saves $9.68

## API Keys Required

Both API keys are already configured in your `.env` file:
- `EASYPOST_API_KEY` ✅
- `SHIPPO_API_KEY` ✅
