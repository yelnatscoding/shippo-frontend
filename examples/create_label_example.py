"""
Example: Create shipping label

This example shows the complete workflow:
1. Get rates
2. Select a rate
3. Purchase label
4. Download PDF
"""

from shippo_tool.shippo_client import ShippoClient
from shippo_tool.models import Address, Parcel
from shippo_tool.utils import download_label

# Initialize client
client = ShippoClient()

# Addresses
from_address = Address(
    name="Your Company",
    street1="2755 E Philadelphia St",
    city="Ontario",
    state="CA",
    zip="91761"
)

to_address = Address(
    name="Jane Smith",
    street1="123 Main St",
    city="New York",
    state="NY",
    zip="10001"
)

# Package (1 lb, small box)
parcel = Parcel(
    length=10,
    width=8,
    height=6,
    weight=1
)

# Step 1: Get rates
print("Step 1: Getting rates...")
rates = client.get_rates(from_address, to_address, parcel)

# Step 2: Select cheapest rate
cheapest = min(rates, key=lambda r: r.amount)
print(f"\nStep 2: Selected {cheapest.provider} {cheapest.servicelevel_name} - ${cheapest.amount}")

# Step 3: Purchase label
print("\nStep 3: Purchasing label...")
label = client.purchase_label(cheapest.object_id)

print(f"\n✅ Label created!")
print(f"   Tracking: {label.tracking_number}")
print(f"   Cost: ${label.cost}")
print(f"   Label URL: {label.label_url}")

# Step 4: Download PDF
print("\nStep 4: Downloading label...")
local_path = download_label(label.label_url, label.tracking_number)
print(f"   Saved to: {local_path}")

print("\n🎉 Done! You can now print the label.")
