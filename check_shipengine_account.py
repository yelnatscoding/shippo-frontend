#!/usr/bin/env python3
"""
Check ShipEngine account configuration
"""

from dotenv import load_dotenv
load_dotenv()

import os
import requests
import json

API_KEY = os.getenv("SHIPENGINE_API_KEY")
BASE_URL = "https://api.shipengine.com/v1"

headers = {
    "API-Key": API_KEY,
    "Content-Type": "application/json"
}

print("=" * 80)
print("ShipEngine Account Investigation")
print("=" * 80)

# 1. Check carriers
print("\n1. CONNECTED CARRIERS")
print("-" * 80)
try:
    response = requests.get(f"{BASE_URL}/carriers", headers=headers, timeout=30)
    if response.status_code == 200:
        data = response.json()
        carriers = data.get("carriers", [])
        print(f"Found {len(carriers)} connected carrier(s):\n")

        for carrier in carriers:
            print(f"  Carrier: {carrier.get('friendly_name', 'N/A')}")
            print(f"    ID: {carrier.get('carrier_id', 'N/A')}")
            print(f"    Code: {carrier.get('carrier_code', 'N/A')}")
            print(f"    Account Number: {carrier.get('account_number', 'N/A')}")
            print(f"    Nickname: {carrier.get('nickname', 'N/A')}")
            print(f"    Balance: ${carrier.get('balance', 0):.2f}")

            # Check if it's a platform carrier or BYOC
            has_credentials = carrier.get('has_multi_package_supporting_services', False)
            print(f"    Type: {'Platform Carrier' if not carrier.get('account_number') else 'BYOC (Your Account)'}")
            print()
    else:
        print(f"Error fetching carriers: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"Error: {e}")

# 2. Check account/balance info
print("\n2. ACCOUNT INFORMATION")
print("-" * 80)
try:
    # Try to get account info
    response = requests.get(f"{BASE_URL}/account", headers=headers, timeout=30)
    if response.status_code == 200:
        data = response.json()
        print("Account details:")
        print(json.dumps(data, indent=2))
    else:
        print(f"Could not fetch account info (status {response.status_code})")
        if response.status_code == 404:
            print("  (This endpoint may not be available)")
except Exception as e:
    print(f"Error checking account: {e}")

# 3. Check balance endpoint
print("\n3. BALANCE INFORMATION")
print("-" * 80)
try:
    response = requests.get(f"{BASE_URL}/balance", headers=headers, timeout=30)
    if response.status_code == 200:
        data = response.json()
        print("Balance details:")
        print(json.dumps(data, indent=2))
    else:
        print(f"Could not fetch balance (status {response.status_code})")
        if response.status_code == 404:
            print("  (Balance endpoint may not exist or you're using BYOC)")
except Exception as e:
    print(f"Error checking balance: {e}")

print("\n" + "=" * 80)
print("Investigation Complete")
print("=" * 80)
