"""
Example: Simple rate check

This example shows how to use the Shippo client programmatically
to get shipping rates without using the CLI.
"""

from shippo_tool.shippo_client import ShippoClient
from shippo_tool.models import Address, Parcel

# Initialize client (reads API key from .env)
client = ShippoClient()

# Define addresses
from_address = Address(
    name="Your Company",
    street1="2755 E Philadelphia St",
    city="Ontario",
    state="CA",
    zip="91761"
)

to_address = Address(
    name="John Doe",
    street1="1106 S Foster Rd",
    city="China Grove",
    state="TX",
    zip="78263"
)

# Define package
parcel = Parcel(
    length=44,
    width=29,
    height=26,
    weight=13
)

# Get rates
print("Fetching shipping rates...")
rates = client.get_rates(from_address, to_address, parcel)

# Display rates
print(f"\nFound {len(rates)} rates:\n")
for rate in sorted(rates, key=lambda r: r.amount):
    print(f"  {rate.provider:8} {rate.servicelevel_name:30} ${rate.amount:7.2f} ({rate.estimated_days} days)")

# Show cheapest
cheapest = min(rates, key=lambda r: r.amount)
print(f"\n💡 Cheapest: {cheapest.provider} {cheapest.servicelevel_name} - ${cheapest.amount}")
print(f"   Rate ID: {cheapest.object_id}")
