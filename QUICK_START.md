# Quick Start Guide

Get up and running with EasyPost Shipping Tool in 5 minutes!

## Step 1: Get Your API Key

1. Go to [https://www.easypost.com/signup](https://www.easypost.com/signup) and sign up
2. Navigate to Account → API Keys
3. Copy your **Test API Key** (starts with `EZTEST`)

## Step 2: Configure

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and paste your API key:
   ```
   EASYPOST_API_KEY=EZTEST_your_key_here
   EASYPOST_TEST_MODE=true
   ```

3. (Optional) Edit `config.yaml` to set your default sender address

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 4: Try It Out!

### Compare Shipping Rates

```bash
python -m shippo_tool rates \
  --to-name "John Doe" \
  --to-street "1106 S Foster Rd" \
  --to-city "China Grove" \
  --to-state TX \
  --to-zip 78263 \
  --weight 13 \
  --length 44 \
  --width 29 \
  --height 26
```

This will show you rates from USPS, UPS, and FedEx!

### Create a Test Label

1. First, get rates (see above) and copy a `Rate ID` from the output

2. Create the label:
   ```bash
   python -m shippo_tool create-label --rate-id <paste_rate_id_here>
   ```

3. Find your PDF in the `labels/` folder!

### Validate an Address

```bash
python -m shippo_tool validate \
  --name "John Doe" \
  --street "1106 S Foster Rd" \
  --city "China Grove" \
  --state TX \
  --zip 78263
```

## Step 5: Go Live!

When you're ready for production:

1. Get your **Live API Key** from EasyPost (starts with `EZAK`)
2. Update `.env`:
   ```
   EASYPOST_API_KEY=EZAK_your_live_key_here
   EASYPOST_TEST_MODE=false
   ```

3. You're now creating real labels that will be charged to your account!

## Common Use Cases

### California to Texas (your example)

```bash
# Your from address is in config.yaml, so just specify destination:
python -m shippo_tool rates \
  --to-name "Recipient Name" \
  --to-street "1106 S Foster Rd" \
  --to-city "China Grove" \
  --to-state TX \
  --to-zip 78263 \
  --weight 13 \
  --length 44 \
  --width 29 \
  --height 26
```

Expected rates:
- **USPS Ground Advantage:** ~$20-25 (3-5 days)
- **USPS Priority:** ~$25-32 (2-3 days)
- **UPS Ground:** ~$22-28 (3-5 days)
- **FedEx Ground:** ~$24-30 (3-5 days)

### Compare with Your $23 Quote

The tool will show you which carrier gives the best rate. EasyPost provides access to discounted carrier rates from 100+ carriers.

## Tips

- **Save typing:** Set your sender address in `config.yaml`
- **Filter carriers:** Use `--carrier usps` to only see USPS rates
- **Batch processing:** See `examples/` for programmatic usage
- **Test mode:** Always test with sandbox API key first (free labels!)

## Need Help?

- Check the full `README.md`
- Look at examples in `examples/`
- EasyPost docs: [https://docs.easypost.com/](https://docs.easypost.com/)

## Cost Breakdown

For your use case (<100 labels/month):

- **First 3,000 labels/month:** FREE platform fee (just pay carrier)
- **After 3,000:** 8¢ each + carrier cost
- **Total monthly cost:** $0 in platform fees + shipping costs
- **No monthly minimums or commitments**

**Example:** 100 labels at avg $12 shipping cost each
- Platform fees: 100 × $0 = **$0.00** (under 3,000 limit)
- Carrier costs: 100 × $12 = $1,200
- **Total:** $1,200.00/month (save ~$5/month vs other platforms!)
