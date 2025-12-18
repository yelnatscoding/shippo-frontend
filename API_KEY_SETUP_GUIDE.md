# API Key Setup Guide

Follow these steps to get API keys for ShipEngine and Easyship.

---

## ShipEngine API Key

### Step 1: Create Account
1. Go to **https://www.shipengine.com/**
2. Click **"Get Started"** or **"Sign Up"**
3. Create your account (free developer account available)

### Step 2: Get Your API Key
1. Log in to your ShipEngine account
2. Go to **https://app.shipengine.com/#/portal/apimanagement**
3. Click **"API Keys"** in the sidebar
4. You'll see two keys:
   - **API Key (Test)** - for testing
   - **API Key (Production)** - for live shipping
5. Click **"Show"** to reveal your API key
6. Copy the API key

### Step 3: Add to .env File
```bash
SHIPENGINE_API_KEY=your_api_key_here
```

### Pricing
- **Free Developer Account**: For testing and building
- **Advanced Plan**: Starting at $10/month for 1,000 API calls
- **Enterprise**: Custom pricing for 25,000+ shipments/month

### Features
- 200+ carriers (USPS, FedEx, UPS, DHL, etc.)
- Address validation
- Label creation
- Tracking
- Rate shopping

### Documentation
- API Docs: https://www.shipengine.com/docs/
- Developer Portal: https://app.shipengine.com

---

## Easyship API Key

### Step 1: Create Account
1. Go to **https://www.easyship.com/signup**
2. Create your account (free to use, no monthly fees)
3. Complete the onboarding process

### Step 2: Get Your API Key
1. Log in to your Easyship account
2. Go to **Settings** → **API** or visit **https://app.easyship.com/settings/api**
3. Under **"API Credentials"**, you'll see:
   - **Access Token** (this is your API key)
4. Click to reveal and copy your Access Token

### Step 3: Add to .env File
```bash
EASYSHIP_API_KEY=your_access_token_here
```

### Pricing
- **100% Free Platform**: No monthly fees, no setup fees
- **Pay Only for Shipping**: Only pay the actual shipping cost
- **Volume Discounts**: Pre-negotiated rates (up to 90% off retail)

### Features
- 250+ carriers globally (USPS, FedEx, UPS, DHL, etc.)
- Claims 90% off FedEx retail rates
- Strong international shipping focus
- Address validation
- Label creation
- Tracking
- Insurance options

### Documentation
- API Docs: https://developers.easyship.com/
- API Reference: https://developers.easyship.com/reference/introduction

---

## Testing Your Setup

After adding both API keys to your `.env` file, test them:

### Test ShipEngine:
```bash
python check_shipengine_rates.py
```

### Test Easyship:
```bash
python check_easyship_rates.py
```

### Compare All Providers:
Once you have both API keys set up, you can create an updated comparison script that includes all 4 providers:
- EasyPost
- Shippo
- ShipEngine
- Easyship

---

## Troubleshooting

### ShipEngine Errors

**"Invalid API Key"**
- Make sure you copied the entire key
- Check that there are no extra spaces
- Verify you're using the correct environment (test vs production)

**"Rate limit exceeded"**
- Free tier has API call limits
- Upgrade to a paid plan for higher limits

### Easyship Errors

**"Authentication failed"**
- Ensure you copied the Access Token (not API Secret)
- Check for trailing spaces in your `.env` file
- Make sure the key is active in your Easyship account

**"No rates returned"**
- Easyship may need additional account setup
- Some carriers require connecting your carrier accounts first
- International shipping may require additional business information

---

## Security Best Practices

1. **Never commit `.env` file to git**
   - It's already in `.gitignore`
   - Keep your API keys secret

2. **Use test keys for development**
   - Both platforms offer test/sandbox keys
   - Switch to production keys only when ready

3. **Rotate keys regularly**
   - Change your API keys every few months
   - Revoke old keys after rotation

---

## What's Next?

After setting up both API keys:

1. Run comparison tests to see which provider offers the best rates for your routes
2. Consider which features matter most (carrier selection, international shipping, etc.)
3. Evaluate pricing models for your shipping volume

**Need help?** Contact support:
- ShipEngine: https://www.shipengine.com/contact/
- Easyship: https://support.easyship.com/
