# Quick Start Guide

Get your shipping label tool running in 15 minutes!

## Prerequisites Checklist

- [ ] Vercel account (free): [Sign up](https://vercel.com/signup)
- [ ] At least one shipping provider API key (Shippo recommended for testing)
- [ ] Google Cloud account (optional, for Drive integration)

## Step 1: Install Vercel CLI (2 minutes)

```bash
npm install -g vercel
vercel login
```

## Step 2: Set Up Shipping Provider (5 minutes)

### Option A: Shippo (Recommended for Testing)

1. Go to [goshippo.com](https://goshippo.com) and sign up
2. Navigate to API settings
3. Copy your test API key (starts with `shippo_test_`)

### Option B: EasyPost

1. Go to [easypost.com](https://easypost.com)
2. Sign up for free account
3. Get test API key (starts with `EZTEST_`)

## Step 3: Configure Environment (3 minutes)

```bash
cd /home/stan/Desktop/code/shippo-shipping-tool/shippo-frontend

# Copy environment template
cp .env.example .env.local

# Edit with your API keys
nano .env.local
```

**Minimum configuration** (just to get started):

```bash
SHIPPO_API_KEY=shippo_test_YOUR_KEY_HERE
SHIPPO_TEST_MODE=true
```

## Step 4: Run Locally (1 minute)

```bash
vercel dev
```

Open browser to `http://localhost:3000`

🎉 **You're running!** Try comparing rates now.

## Step 5: Deploy to Production (2 minutes)

```bash
# Link to Vercel
vercel link

# Set environment variables in Vercel
vercel env add SHIPPO_API_KEY production
# Paste your API key when prompted

# Deploy
vercel --prod
```

You'll get a URL like `https://shippo-frontend-abc123.vercel.app`

## Step 6: Optional - Google Drive Integration (10 minutes)

If you want permanent label storage:

### Create Google Cloud Service Account

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create project "shipping-labels"
3. Enable Google Drive API
4. Create service account
5. Download JSON key

### Setup Drive Folder

1. Create "Shipping Labels" folder in Google Drive
2. Share with service account email
3. Copy folder ID from URL

### Add to Environment

```bash
# Add to .env.local
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...entire JSON here...}
GOOGLE_DRIVE_FOLDER_ID=1ABC123xyz

# Also add to Vercel
vercel env add GOOGLE_SERVICE_ACCOUNT_JSON production
vercel env add GOOGLE_DRIVE_FOLDER_ID production
```

## Testing Your Setup

### Test 1: Compare Rates

1. Go to "Compare Rates" tab
2. Enter destination address:
   - Name: John Doe
   - Street: 123 Main St
   - City: New York
   - State: NY
   - ZIP: 10001

3. Enter package:
   - Click "Medium" preset (or enter custom dimensions)
   - Weight: 2 lbs

4. Click "Compare Rates"

**Expected**: See rates from all configured providers

### Test 2: Validate Address

1. Go to "Validate Address" tab
2. Enter:
   - Street: 1600 Amphitheatre Parkway
   - City: Mountain View
   - State: CA
   - ZIP: 94043

3. Click "Validate Address"

**Expected**: Address validated with suggested corrections

### Test 3: Purchase Label (Test Mode)

1. Compare rates (as above)
2. Click "Purchase" on any rate
3. Confirm purchase

**Expected**:
- Label purchased successfully
- If Google Drive configured: Link to view label
- Tracking number displayed
- Label appears in History tab

## Common Issues

### "No rates found"

- Check API key is correct in `.env.local`
- Make sure you're using test mode keys
- Verify addresses are valid US addresses

### "Module not found" errors

```bash
# Install Python dependencies locally
pip install -r requirements.txt
```

### CORS errors in browser

- Make sure you're using `vercel dev` (not direct Python)
- Check browser console for specific error
- Clear cache and try again

### Google Drive upload fails

- Verify JSON key is correct (paste as single line)
- Check folder is shared with service account
- Ensure folder ID is correct

## Next Steps

1. **Add more providers**: Get API keys for EasyPost, ShipEngine, Easyship
2. **Customize sender address**: Edit `api/config.py` line 6
3. **Add package presets**: Edit `public/app.js` lines 16-21
4. **Custom domain**: Add in Vercel dashboard settings

## Getting Help

- Check `README.md` for detailed docs
- Review `docs/FRONTEND_IMPLEMENTATION_PLAN.md`
- Check Vercel function logs for errors
- Look at browser console for frontend errors

## Production Checklist

Before going live:

- [ ] Switch to production API keys
- [ ] Update environment variables: `*_TEST_MODE=false`
- [ ] Test with real addresses
- [ ] Set up Google Drive (for permanent storage)
- [ ] Add custom domain (optional)
- [ ] Test label printing
- [ ] Share URL with team member

---

**Estimated setup time**: 15-30 minutes (depending on Google Drive setup)

**Ready to ship!** 📦🚀
