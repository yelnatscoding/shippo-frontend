"""Command-line interface for EasyPost Shipping Tool"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import sys
from pathlib import Path

from .easypost_client import EasyPostClient
from .shippo_client import ShippoClient
from .shipengine_client import ShipEngineClient
from .easyship_client import EasyshipClient
from .models import Address, Parcel
from .utils import download_label, format_address_for_display
from .config import config

console = Console()

@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    🚚 EasyPost Shipping Tool

    Create shipping labels, compare carrier rates, and validate addresses.
    """
    # Check if API key is configured
    if not config.validate_api_key():
        console.print("[red]Error: EASYPOST_API_KEY not configured![/red]")
        console.print("Please set your API key in the .env file")
        console.print("Get your API key from: https://www.easypost.com/account/api-keys")
        sys.exit(1)

@cli.command()
@click.option('--from-name', default=config.default_sender.name, help='Sender name')
@click.option('--from-street', default=config.default_sender.street1, help='Sender street address')
@click.option('--from-city', default=config.default_sender.city, help='Sender city')
@click.option('--from-state', default=config.default_sender.state, help='Sender state')
@click.option('--from-zip', default=config.default_sender.zip, help='Sender ZIP code')
@click.option('--to-name', required=True, help='Recipient name')
@click.option('--to-street', required=True, help='Recipient street address')
@click.option('--to-city', required=True, help='Recipient city')
@click.option('--to-state', required=True, help='Recipient state')
@click.option('--to-zip', required=True, help='Recipient ZIP code')
@click.option('--to-phone', help='Recipient phone number (required for FedEx)')
@click.option('--to-email', help='Recipient email address')
@click.option('--weight', required=True, type=float, help='Package weight in pounds')
@click.option('--length', required=True, type=float, help='Package length in inches')
@click.option('--width', required=True, type=float, help='Package width in inches')
@click.option('--height', required=True, type=float, help='Package height in inches')
@click.option('--carrier', help='Filter by carrier (usps, ups, fedex)')
@click.option('--provider', default='easypost', type=click.Choice(['easypost', 'shippo', 'shipengine', 'easyship'], case_sensitive=False), help='Shipping API provider (default: easypost)')
def rates(from_name, from_street, from_city, from_state, from_zip,
         to_name, to_street, to_city, to_state, to_zip, to_phone, to_email,
         weight, length, width, height, carrier, provider):
    """Get shipping rates from all carriers"""

    try:
        # Choose the appropriate client based on provider
        provider_lower = provider.lower()
        if provider_lower == 'shippo':
            client = ShippoClient()
            provider_name = "Shippo"
        elif provider_lower == 'shipengine':
            client = ShipEngineClient()
            provider_name = "ShipEngine"
        elif provider_lower == 'easyship':
            client = EasyshipClient()
            provider_name = "EasyShip"
        else:
            client = EasyPostClient()
            provider_name = "EasyPost"

        # Create address objects
        from_addr = Address(
            name=from_name,
            street1=from_street,
            city=from_city,
            state=from_state,
            zip=from_zip,
            phone=config.default_sender.phone,
            email=config.default_sender.email,
        )

        to_addr = Address(
            name=to_name,
            street1=to_street,
            city=to_city,
            state=to_state,
            zip=to_zip,
            phone=to_phone,
            email=to_email,
        )

        parcel = Parcel(
            length=length,
            width=width,
            height=height,
            weight=weight,
        )

        # Show progress while fetching rates
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching rates from carriers...", total=None)
            rate_list = client.get_rates(from_addr, to_addr, parcel)

        # Filter by carrier if specified
        if carrier:
            rate_list = [r for r in rate_list if r.provider.lower() == carrier.lower()]

        if not rate_list:
            console.print("[yellow]No rates available[/yellow]")
            return

        # Sort by price (cheapest first)
        rate_list.sort(key=lambda r: r.amount)

        # Display rates in a table
        table = Table(title=f"📦 Available Shipping Rates ({provider_name})", show_header=True, header_style="bold magenta")
        table.add_column("Carrier", style="cyan", width=10)
        table.add_column("Service", style="white", width=30)
        table.add_column("Price", style="green", justify="right", width=10)
        table.add_column("Delivery", style="yellow", width=12)
        table.add_column("Rate ID", style="dim", width=15)

        for rate in rate_list:
            days_str = f"{rate.estimated_days} days" if rate.estimated_days else rate.duration_terms or "N/A"
            table.add_row(
                rate.provider,
                rate.servicelevel_name,
                f"${rate.amount:.2f}",
                days_str,
                rate.object_id[:15] + "..."
            )

        console.print(table)

        # Show summary
        cheapest = rate_list[0]
        console.print(f"\n[green]💡 Cheapest option:[/green] {cheapest.provider} {cheapest.servicelevel_name} - ${cheapest.amount:.2f}")

        # Show how to create label
        console.print(f"\n[cyan]To create a label, run:[/cyan]")
        console.print(f"  python -m shippo_tool create-label --rate-id {cheapest.object_id}")

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)

@cli.command()
@click.option('--rate-id', required=True, help='Rate ID from rates command')
@click.option('--output', default='labels', help='Output directory for PDF')
@click.option('--format', default='PDF', type=click.Choice(['PDF', 'PNG', 'ZPL'], case_sensitive=False))
@click.option('--provider', default='easypost', type=click.Choice(['easypost', 'shippo', 'shipengine', 'easyship'], case_sensitive=False), help='Shipping API provider (default: easypost)')
def create_label(rate_id, output, format, provider):
    """Create and download shipping label"""

    try:
        # Choose the appropriate client based on provider
        provider_lower = provider.lower()
        if provider_lower == 'shippo':
            client = ShippoClient()
            provider_name = "Shippo"
        elif provider_lower == 'shipengine':
            client = ShipEngineClient()
            provider_name = "ShipEngine"
        elif provider_lower == 'easyship':
            client = EasyshipClient()
            provider_name = "EasyShip"
        else:
            client = EasyPostClient()
            provider_name = "EasyPost"

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Purchasing shipping label...", total=None)
            label = client.purchase_label(rate_id, format.upper())

        # Download label PDF
        local_path = download_label(label.label_url, label.tracking_number, output)
        label.local_path = local_path

        # Display success message
        panel = Panel(
            f"[green]✓ Label Created Successfully![/green]\n\n"
            f"[cyan]Tracking Number:[/cyan] {label.tracking_number}\n"
            f"[cyan]Carrier:[/cyan] {label.carrier}\n"
            f"[cyan]Service:[/cyan] {label.service}\n"
            f"[cyan]Cost:[/cyan] ${label.cost:.2f}\n"
            f"[cyan]Label:[/cyan] {local_path}\n\n"
            f"[yellow]Label URL (expires soon):[/yellow]\n{label.label_url}",
            title="📦 Shipping Label",
            border_style="green"
        )
        console.print(panel)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)

@cli.command()
@click.option('--name', required=True, help='Recipient name')
@click.option('--street', required=True, help='Street address')
@click.option('--city', required=True, help='City')
@click.option('--state', required=True, help='State (2-letter code)')
@click.option('--zip', required=True, help='ZIP code')
@click.option('--country', default='US', help='Country code')
@click.option('--provider', default='easypost', type=click.Choice(['easypost', 'shippo', 'shipengine'], case_sensitive=False), help='Shipping API provider (default: easypost)')
def validate(name, street, city, state, zip, country, provider):
    """Validate and normalize an address"""

    try:
        # Choose the appropriate client based on provider
        provider_lower = provider.lower()
        if provider_lower == 'shippo':
            client = ShippoClient()
            provider_name = "Shippo"
        elif provider_lower == 'shipengine':
            client = ShipEngineClient()
            provider_name = "ShipEngine"
        else:
            client = EasyPostClient()
            provider_name = "EasyPost"

        address = Address(
            name=name,
            street1=street,
            city=city,
            state=state,
            zip=zip,
            country=country,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Validating address...", total=None)
            result = client.validate_address(address)

        if result.is_valid:
            console.print("[green]✓ Address is valid![/green]\n")

            if result.validated_address:
                # Show original vs validated
                table = Table(show_header=True, header_style="bold")
                table.add_column("Original", style="yellow")
                table.add_column("Validated", style="green")

                orig_dict = result.original_address.model_dump()
                val_dict = result.validated_address.model_dump()

                for key in ['street1', 'city', 'state', 'zip']:
                    orig_val = orig_dict.get(key, '')
                    val_val = val_dict.get(key, '')
                    style = "green" if orig_val == val_val else "yellow"
                    table.add_row(
                        orig_val,
                        f"[{style}]{val_val}[/{style}]"
                    )

                console.print(table)
        else:
            console.print("[red]✗ Address validation failed[/red]\n")
            for msg in result.messages:
                console.print(f"  • {msg}")

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)

@cli.command()
@click.option('--carrier', required=True, help='Carrier code (usps, ups, fedex)')
@click.option('--tracking', required=True, help='Tracking number')
def track(carrier, tracking):
    """Track a shipment"""

    try:
        client = EasyPostClient()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching tracking info...", total=None)
            info = client.track_shipment(carrier.lower(), tracking)

        # Display tracking info
        panel = Panel(
            f"[cyan]Carrier:[/cyan] {info['carrier'].upper()}\n"
            f"[cyan]Tracking Number:[/cyan] {info['tracking_number']}\n"
            f"[cyan]Status:[/cyan] {info['status']}\n"
            f"[cyan]Details:[/cyan] {info['status_details']}\n"
            f"[cyan]Location:[/cyan] {info['location']}\n"
            f"[cyan]ETA:[/cyan] {info['eta'] or 'N/A'}",
            title="📍 Tracking Information",
            border_style="cyan"
        )
        console.print(panel)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)

if __name__ == '__main__':
    cli()
