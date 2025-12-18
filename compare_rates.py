#!/usr/bin/env python3
"""
Compare rates from both EasyPost and Shippo side-by-side
Usage: python compare_rates.py
"""

from dotenv import load_dotenv
load_dotenv()

from shippo_tool.easypost_client import EasyPostClient
from shippo_tool.shippo_client import ShippoClient
from shippo_tool.models import Address, Parcel
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

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
    console.print(Panel.fit(
        f"[bold cyan]Shipping Rate Comparison[/bold cyan]\n"
        f"Route: {FROM_ADDRESS['zip']} → {TO_ADDRESS['zip']}\n"
        f"Package: {PACKAGE['weight']} lb, {PACKAGE['length']}x{PACKAGE['width']}x{PACKAGE['height']} in",
        border_style="cyan"
    ))

    # Create addresses
    from_addr = Address(**FROM_ADDRESS)
    to_addr = Address(**TO_ADDRESS)
    parcel = Parcel(**PACKAGE)

    # Get EasyPost rates
    console.print("\n[bold green]Fetching EasyPost rates...[/bold green]")
    easypost_client = EasyPostClient()
    easypost_rates = easypost_client.get_rates(from_addr, to_addr, parcel)
    # Filter out UPS rates
    easypost_rates = [r for r in easypost_rates if "UPS" not in r.provider.upper()]
    easypost_rates.sort(key=lambda r: r.amount)

    # Get Shippo rates
    console.print("[bold blue]Fetching Shippo rates...[/bold blue]\n")
    shippo_client = ShippoClient()
    shippo_rates = shippo_client.get_rates(from_addr, to_addr, parcel)
    # Filter out UPS rates
    shippo_rates = [r for r in shippo_rates if "UPS" not in r.provider.upper()]
    shippo_rates.sort(key=lambda r: r.amount)

    # Display comparison table
    table = Table(title="Rate Comparison", show_header=True, header_style="bold")
    table.add_column("Provider", style="cyan", width=12)
    table.add_column("Carrier", style="white", width=10)
    table.add_column("Service", style="white", width=28)
    table.add_column("Price", style="green", justify="right", width=10)
    table.add_column("Delivery", style="yellow", width=10)

    # Add EasyPost rates
    for rate in easypost_rates[:5]:  # Top 5 cheapest
        days_str = f"{rate.estimated_days}d" if rate.estimated_days else rate.duration_terms or "N/A"
        table.add_row(
            "[green]EasyPost[/green]",
            rate.provider,
            rate.servicelevel_name,
            f"${rate.amount:.2f}",
            days_str
        )

    table.add_section()  # Visual separator

    # Add Shippo rates
    for rate in shippo_rates[:5]:  # Top 5 cheapest
        days_str = f"{rate.estimated_days}d" if rate.estimated_days else rate.duration_terms or "N/A"
        table.add_row(
            "[blue]Shippo[/blue]",
            rate.provider,
            rate.servicelevel_name,
            f"${rate.amount:.2f}",
            days_str
        )

    console.print(table)

    # Show cheapest from each
    console.print(f"\n[green]💡 EasyPost Cheapest:[/green] {easypost_rates[0].provider} {easypost_rates[0].servicelevel_name} - ${easypost_rates[0].amount:.2f}")
    console.print(f"[blue]💡 Shippo Cheapest:[/blue] {shippo_rates[0].provider} {shippo_rates[0].servicelevel_name} - ${shippo_rates[0].amount:.2f}")

    # Show winner
    if easypost_rates[0].amount < shippo_rates[0].amount:
        savings = shippo_rates[0].amount - easypost_rates[0].amount
        console.print(f"\n[bold green]🏆 Winner: EasyPost (saves ${savings:.2f})[/bold green]")
    elif shippo_rates[0].amount < easypost_rates[0].amount:
        savings = easypost_rates[0].amount - shippo_rates[0].amount
        console.print(f"\n[bold blue]🏆 Winner: Shippo (saves ${savings:.2f})[/bold blue]")
    else:
        console.print(f"\n[bold yellow]🤝 Tie: Both offer the same cheapest rate[/bold yellow]")

if __name__ == "__main__":
    main()
