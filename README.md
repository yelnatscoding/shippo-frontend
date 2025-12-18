# EasyPost Shipping Tool

A Python CLI tool for creating shipping labels, comparing carrier rates, and validating addresses using the EasyPost API.

## Features

- 📦 **Rate Shopping** - Compare rates from USPS, UPS, FedEx, and 100+ carriers
- 🏷️ **Label Generation** - Create and download shipping labels as PDFs
- ✅ **Address Validation** - Validate addresses before shipping
- 💰 **Cost Savings** - Access to discounted carrier rates (up to 90% off retail)
- 🆓 **Free Platform Fees** - First 3,000 labels/month with no platform fees

## Installation

1. Clone or download this repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your EasyPost API key:
   ```bash
   cp .env.example .env
   # Edit .env and add your EASYPOST_API_KEY
   ```

## Quick Start

### Get Shipping Rates

Compare rates from all carriers:

```bash
python -m shippo_tool rates \
  --from-zip 91761 \
  --to-zip 78263 \
  --weight 13 \
  --length 44 \
  --width 29 \
  --height 26
```

### Create a Shipping Label

```bash
python -m shippo_tool create-label \
  --rate-id <rate_id_from_previous_command> \
  --output ./labels/
```

### Validate an Address

```bash
python -m shippo_tool validate \
  --street "1106 S Foster Rd" \
  --city "China Grove" \
  --state TX \
  --zip 78263
```

## Configuration

Edit `config.yaml` to set default values:

```yaml
default_sender:
  name: "Your Company"
  street1: "2755 E Philadelphia St"
  city: "Ontario"
  state: "CA"
  zip: "91761"
  country: "US"

preferences:
  auto_select_cheapest: false
  label_format: "PDF"
```

## Getting an EasyPost API Key

1. Sign up at [https://www.easypost.com/signup](https://www.easypost.com/signup)
2. Go to Account → API Keys
3. Copy your **Test** API key for development (starts with `EZTEST`)
4. Use your **Live** API key for production (starts with `EZAK`)

## Cost

- **EasyPost Platform:** First 3,000 labels/month FREE, then $0.08/label
- **Carrier Costs:** Variable by weight, distance, and service level
- **No monthly fees** or minimums
- **Instant signup** - no approval process needed

## Development

Run tests:
```bash
pytest tests/
```

## License

MIT
