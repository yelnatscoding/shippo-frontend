# Testing the Shippo Tool

## Before You Test

Make sure you've:
1. Signed up for a Shippo account at [goshippo.com](https://goshippo.com)
2. Got your **Test API Key** from Settings → API
3. Created a `.env` file with your test key:
   ```
   SHIPPO_API_KEY=shippo_test_your_key_here
   SHIPPO_TEST_MODE=true
   ```

## Install Dependencies

```bash
# If you haven't already
pip install -r requirements.txt
```

## Test 1: Verify Installation

```bash
python -m shippo_tool --version
```

Expected output: `1.0.0`

## Test 2: Rate Shopping (CA → TX, your example)

```bash
python -m shippo_tool rates \
  --from-name "Your Company" \
  --from-street "2755 E Philadelphia St" \
  --from-city "Ontario" \
  --from-state CA \
  --from-zip 91761 \
  --to-name "Test Recipient" \
  --to-street "1106 S Foster Rd" \
  --to-city "China Grove" \
  --to-state TX \
  --to-zip 78263 \
  --weight 13 \
  --length 44 \
  --width 29 \
  --height 26
```

**Expected Results:**
- Should show 15-25 different shipping options
- USPS, UPS, and FedEx rates
- Prices ranging from ~$12 (economy) to ~$150 (express)
- Delivery times from 3-7 days (fastest) to 15-20 days (cheapest)

**What to check:**
- ✅ Rates are displayed in a formatted table
- ✅ Cheapest option is highlighted
- ✅ Rate IDs are shown
- ✅ No errors

## Test 3: Address Validation

```bash
python -m shippo_tool validate \
  --name "Test Person" \
  --street "1106 S Foster Rd" \
  --city "China Grove" \
  --state TX \
  --zip 78263
```

**Expected Results:**
- Address should validate successfully (green checkmark)
- May show normalized/corrected version
- No validation errors

**Try an invalid address:**
```bash
python -m shippo_tool validate \
  --name "Test" \
  --street "123 Fake Street That Does Not Exist" \
  --city "Nowhere" \
  --state CA \
  --zip 00000
```

Should show validation errors!

## Test 4: Create a Test Label

⚠️ **Important:** Test mode labels are FREE but don't create real shipments!

1. First, get rates (use Test 2 command)
2. Copy one of the Rate IDs from the output
3. Create label:

```bash
python -m shippo_tool create-label --rate-id <paste_rate_id_here>
```

**Expected Results:**
- Label downloads successfully to `labels/` folder
- Shows tracking number
- Shows cost
- PDF opens and displays label

**What to check:**
- ✅ PDF file exists in `labels/` folder
- ✅ Tracking number is displayed
- ✅ Cost matches the rate you selected
- ✅ Label has barcode and addresses
- ✅ Label says "TEST" or "SAMPLE" (test mode watermark)

## Test 5: Programmatic Usage

Run the example scripts:

```bash
# Simple rate check
python examples/simple_rate_check.py

# Full workflow (rates → label)
python examples/create_label_example.py
```

## Common Issues & Solutions

### "API key not configured"
- Make sure `.env` file exists
- Check that `SHIPPO_API_KEY` is set
- Verify you copied the full API key (starts with `shippo_test_`)

### "No rates available"
- Check that addresses are valid US addresses
- Verify weight/dimensions are reasonable
- Try with simpler address (just city, state, ZIP)

### "Label purchase failed"
- Make sure you're using a valid Rate ID from the rates command
- Rate IDs expire after ~10 minutes, get fresh rates
- Check that test mode is enabled

### Import errors
- Make sure you installed dependencies: `pip install -r requirements.txt`
- Make sure you're in the project directory

### "module 'shippo' has no attribute 'Shipment'"
- Update shippo library: `pip install --upgrade shippo`
- Check installed version: `pip show shippo`

## What Success Looks Like

After running all tests, you should have:
- ✅ Rates displayed for CA → TX shipment
- ✅ Validated address (green checkmark)
- ✅ Test label PDF in `labels/` folder
- ✅ No error messages

## Next Steps After Testing

1. **Compare costs:** How do Shippo's rates compare to your $23 quote?
2. **Test different packages:** Try 1 lb, 5 lb, 10 lb, 20 lb packages
3. **Test different destinations:** Try CA → CA, CA → NY, CA → FL
4. **Go live:** When ready, switch to live API key

## Production Checklist

Before using in production:

- [ ] Get Live API key from Shippo
- [ ] Update `.env` with live key
- [ ] Set `SHIPPO_TEST_MODE=false`
- [ ] Test with one real shipment first
- [ ] Set up default sender in `config.yaml`
- [ ] Set up label storage/backup strategy
- [ ] Document workflow for your team

## Support

If tests fail:
1. Check the logs in `logs/shippo_tool.log`
2. Review Shippo docs: [goshippo.com/docs](https://goshippo.com/docs)
3. Check your Shippo dashboard for API calls/errors
4. Verify your account is in good standing
