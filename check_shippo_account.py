#!/usr/bin/env python3
"""
Check Shippo account configuration
"""

from dotenv import load_dotenv
load_dotenv()

import os
from shippo import Shippo
from shippo.models import operations

SHIPPO_TOKEN = os.getenv("SHIPPO_API_KEY")
client = Shippo(api_key_header=SHIPPO_TOKEN)

print("=" * 80)
print("Shippo Account Investigation")
print("=" * 80)

# Check carrier accounts
print("\n1. CARRIER ACCOUNTS")
print("-" * 80)

try:
    response = client.carrier_accounts.list(operations.ListCarrierAccountsRequest())

    if response and hasattr(response, 'carrier_accounts'):
        accounts = response.carrier_accounts
        print(f"Found {len(accounts)} carrier account(s):\n")

        for account in accounts:
            # Handle both dict and object access
            carrier = getattr(account, 'carrier', None) or (account.get('carrier') if isinstance(account, dict) else 'N/A')
            obj_id = getattr(account, 'object_id', None) or (account.get('object_id') if isinstance(account, dict) else 'N/A')
            active = getattr(account, 'active', None) or (account.get('active') if isinstance(account, dict) else False)
            test = getattr(account, 'test', None) or (account.get('test') if isinstance(account, dict) else False)
            acct_id = getattr(account, 'account_id', None) or (account.get('account_id') if isinstance(account, dict) else '')

            print(f"  Carrier: {carrier}")
            print(f"    Account ID: {obj_id}")
            print(f"    Active: {active}")
            print(f"    Test: {test}")

            # Check if it's Shippo's account or yours
            if acct_id:
                print(f"    Account Number: {acct_id}")
                print(f"    Type: BYOC (Your Account)")
            else:
                print(f"    Type: Shippo Platform Account")
            print()
    else:
        print("No carrier accounts found or unable to retrieve")

except Exception as e:
    print(f"Error fetching carrier accounts: {e}")

print("\n" + "=" * 80)
print("Investigation Complete")
print("=" * 80)
