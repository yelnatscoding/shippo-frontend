#!/usr/bin/env python3
"""
Quick EasyPost rate checker
Usage: python check_easypost_rates.py
"""

from dotenv import load_dotenv
load_dotenv()  # Load .env file

from shippo_tool.easypost_client import EasyPostClient
from shippo_tool.models import Address, Parcel
from rich.console import Console
from rich.table import Table

console = Console()

# Configuration - Edit these values as needed
FROM_ADDRESS = {
    "name": "Sender",
    "street1": "123 Main St",
    "city": "Ontario",
    "state": "CA",
    "zip": "91761",
    "phone": "555-123-4567"
}

TO_ADDRESS = {
    "name": "Recipient",
    "street1": "123 Main St",
    "city": "Eagan",
    "state": "MN",
    "zip": "55124",
    "phone": "555-987-6543"
}

PACKAGE = {
    "weight": 1,      # pounds
    "length": 10,     # inches
    "width": 8,       # inches
    "height": 2       # inches
}

def main():
    console.print("[bold cyan]EasyPost Rate Check[/bold cyan]")
    console.print(f"Route: {FROM_ADDRESS['zip']} → {TO_ADDRESS['zip']}")
    console.print(f"Package: {PACKAGE['weight']} lb, {PACKAGE['length']}x{PACKAGE['width']}x{PACKAGE['height']} in\n")

    # Initialize client
    client = EasyPostClient()

    # Create addresses
    from_addr = Address(**FROM_ADDRESS)
    to_addr = Address(**TO_ADDRESS)
    parcel = Parcel(**PACKAGE)

    # Get rates
    console.print("Fetching rates...\n")
    rates = client.get_rates(from_addr, to_addr, parcel)

    # Filter out UPS rates
    rates = [r for r in rates if "UPS" not in r.provider.upper()]

    # Sort by price
    rates.sort(key=lambda r: r.amount)

    # Display in table
    table = Table(title="EasyPost Rates", show_header=True, header_style="bold magenta")
    table.add_column("Carrier", style="cyan", width=10)
    table.add_column("Service", style="white", width=30)
    table.add_column("Price", style="green", justify="right", width=10)
    table.add_column("Delivery", style="yellow", width=12)

    for rate in rates:
        days_str = f"{rate.estimated_days} days" if rate.estimated_days else rate.duration_terms or "N/A"
        table.add_row(
            rate.provider,
            rate.servicelevel_name,
            f"${rate.amount:.2f}",
            days_str
        )

    console.print(table)

    # Show cheapest
    cheapest = rates[0]
    console.print(f"\n[green]💡 Cheapest:[/green] {cheapest.provider} {cheapest.servicelevel_name} - ${cheapest.amount:.2f}")

if __name__ == "__main__":
    main()
