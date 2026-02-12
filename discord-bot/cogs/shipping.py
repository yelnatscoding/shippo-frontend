"""Shipping cog - AI-powered conversational shipping flow"""

import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import Dict, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
import base64
import io
import logging
import sys
import os

# Add shippo-frontend lib to path for importing shipping clients
lib_path = os.path.join(os.path.dirname(__file__), "..", "..", "shippo-frontend", "lib")
sys.path.insert(0, lib_path)

from services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

# Try to import shipping models and clients
try:
    from models import Address, Parcel, Rate, ValidationResult
    from shipengine_client import ShipEngineClient
    from easypost_client import EasyPostClient
    from shippo_client import ShippoClient
    SHIPPING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import shipping modules: {e}")
    SHIPPING_AVAILABLE = False
    Address = None
    Parcel = None
    Rate = None
    ValidationResult = None
    ShipEngineClient = None
    EasyPostClient = None
    ShippoClient = None


# --- Field display names for user-friendly messages ---
FIELD_LABELS = {
    "to_name": "recipient name",
    "to_street": "street address",
    "to_city": "city",
    "to_state": "state",
    "to_zip": "ZIP code",
    "to_phone": "phone number",
    "weight": "package weight (lbs)",
}


# --- Views ---

class ShipmentConfirmView(ui.View):
    """Confirm shipment details before address validation"""

    def __init__(self, cog, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id

    @ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="\u2705")
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        await interaction.response.edit_message(view=None)
        await self.cog._validate_and_select_carrier(interaction)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        if self.user_id in self.cog.sessions:
            del self.cog.sessions[self.user_id]

        await interaction.response.edit_message(content="Shipment cancelled.", embed=None, view=None)
        self.stop()


class AddressCorrectionView(ui.View):
    """Let user pick original vs suggested address"""

    def __init__(self, cog, user_id: int, original: 'Address', suggested: 'Address', is_residential: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.original = original
        self.suggested = suggested
        self.is_residential = is_residential

    @ui.button(label="Use Suggested", style=discord.ButtonStyle.success)
    async def use_suggested(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        session = self.cog.sessions.get(self.user_id)
        if session:
            session["to_addr"] = self.suggested

        await interaction.response.edit_message(view=None)
        await self.cog._show_carrier_selection(interaction)

    @ui.button(label="Keep Original", style=discord.ButtonStyle.secondary)
    async def keep_original(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        await interaction.response.edit_message(view=None)
        await self.cog._show_carrier_selection(interaction)


class CarrierSelectView(ui.View):
    """Dropdown to select a carrier"""

    def __init__(self, cog, user_id: int, available_carriers: List[str]):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id

        options = []
        carrier_info = {
            "USPS": ("USPS", "United States Postal Service"),
            "UPS": ("UPS", "United Parcel Service"),
            "FedEx": ("FedEx", "Federal Express"),
        }

        for carrier in available_carriers:
            label, desc = carrier_info.get(carrier, (carrier, carrier))
            options.append(discord.SelectOption(label=label, value=carrier, description=desc))

        if options:
            self.carrier_select.options = options

    @ui.select(placeholder="Select a carrier...")
    async def carrier_select(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        carrier = select.values[0]
        session = self.cog.sessions.get(self.user_id)
        if session:
            session["selected_carrier"] = carrier
            session["step"] = "selecting_rate"

        await interaction.response.edit_message(content=f"Fetching **{carrier}** rates...", embed=None, view=None)
        await self.cog._fetch_and_show_rates(interaction, self.user_id, carrier)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        if self.user_id in self.cog.sessions:
            del self.cog.sessions[self.user_id]
        await interaction.response.edit_message(content="Shipment cancelled.", embed=None, view=None)
        self.stop()


class RateSelectView(ui.View):
    """View for selecting a shipping rate — split by standard/signature"""

    def __init__(self, cog, base_rates: List, sig_rates: List, from_addr, to_addr, parcel, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.all_rates = base_rates + sig_rates
        self.base_rates = base_rates
        self.sig_rates = sig_rates
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.parcel = parcel
        self.user_id = user_id
        self.selected_rate = None

        options = []
        for i, rate in enumerate(self.all_rates[:25]):
            days = f"{rate.estimated_days}d" if rate.estimated_days else "varies"
            sig = " [SIG]" if rate.signature_confirmation else ""
            label = f"${rate.amount:.2f} - {rate.servicelevel_name}{sig}"[:100]
            options.append(discord.SelectOption(
                label=label,
                value=str(i),
                description=f"{rate.provider} \u2022 {days}"[:100]
            ))

        if options:
            self.rate_select.options = options

    @ui.select(placeholder="Select a shipping rate...")
    async def rate_select(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        index = int(select.values[0])
        self.selected_rate = self.all_rates[index]
        rate = self.selected_rate

        sig_text = f"\n**Signature:** {rate.signature_confirmation}" if rate.signature_confirmation else ""

        embed = discord.Embed(
            title="\u2705 Confirm Purchase",
            color=discord.Color.green()
        )
        embed.add_field(
            name="\U0001f4cd To",
            value=f"{self.to_addr.name}\n{self.to_addr.street1}\n{self.to_addr.city}, {self.to_addr.state} {self.to_addr.zip}",
            inline=True
        )
        embed.add_field(
            name="\U0001f4e6 Package",
            value=f"{self.parcel.weight} lbs\n{int(self.parcel.length)}x{int(self.parcel.width)}x{int(self.parcel.height)} in",
            inline=True
        )
        embed.add_field(
            name="\U0001f69a Service",
            value=f"{rate.provider}\n{rate.servicelevel_name}{sig_text}",
            inline=True
        )
        embed.add_field(
            name="\U0001f4b0 Cost",
            value=f"**${rate.amount:.2f}**",
            inline=True
        )
        embed.add_field(
            name="\U0001f4c5 Delivery",
            value=f"{rate.estimated_days or 'varies'} days",
            inline=True
        )

        view = ConfirmPurchaseView(self.cog, self)
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        if self.user_id in self.cog.sessions:
            del self.cog.sessions[self.user_id]
        await interaction.response.edit_message(content="Shipment cancelled.", embed=None, view=None)
        self.stop()


class ConfirmPurchaseView(ui.View):
    """View for confirming label purchase"""

    def __init__(self, cog, rate_view: RateSelectView):
        super().__init__(timeout=300)
        self.cog = cog
        self.rate_view = rate_view

    @ui.button(label="\U0001f3f7\ufe0f Purchase Label", style=discord.ButtonStyle.success)
    async def purchase_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.rate_view.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        await interaction.response.edit_message(content="\u23f3 Creating your label...", embed=None, view=None)
        await self.cog._purchase_label(interaction, self.rate_view)

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.rate_view.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        if self.rate_view.user_id in self.cog.sessions:
            del self.cog.sessions[self.rate_view.user_id]
        await interaction.response.edit_message(content="Shipment cancelled.", embed=None, view=None)


# --- Main Cog ---

class ShippingCog(commands.Cog):
    """AI-powered conversational shipping quotes and labels"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.shipping
        self.sessions: Dict[int, Dict] = {}  # user_id -> session data

        # Initialize Gemini client
        self.gemini = None
        if bot.config.gemini_api_key:
            try:
                self.gemini = GeminiClient(bot.config.gemini_api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Gemini client: {e}")

        # Initialize shipping clients
        self.clients = {}
        if SHIPPING_AVAILABLE:
            try:
                if os.environ.get("SHIPENGINE_API_KEY"):
                    self.clients["shipengine"] = ShipEngineClient()
                if os.environ.get("EASYPOST_API_KEY"):
                    self.clients["easypost"] = EasyPostClient()
                if os.environ.get("SHIPPO_API_KEY"):
                    self.clients["shippo"] = ShippoClient()
                logger.info(f"Shipping clients initialized: {list(self.clients.keys())}")
            except Exception as e:
                logger.warning(f"Could not initialize shipping clients: {e}")

    def _get_from_address(self) -> 'Address':
        """Build from-address from config"""
        default_origin = self.config.get("default_origin_address", {})
        return Address(
            name=default_origin.get("name", "Sender"),
            street1=default_origin.get("street1", "123 Main St"),
            city=default_origin.get("city", "Los Angeles"),
            state=default_origin.get("state", "CA"),
            zip=default_origin.get("zip", "90001"),
            country=default_origin.get("country", "US"),
            phone=default_origin.get("phone", "5551234567")
        )

    def _build_missing_prompt(self, missing: List[str], has_dimensions: bool) -> str:
        """Build a friendly message listing what info is still needed"""
        labels = [FIELD_LABELS.get(f, f) for f in missing]
        parts = []
        if labels:
            parts.append("I still need: **" + "**, **".join(labels) + "**")
        if not has_dimensions:
            parts.append("_(No dimensions provided \u2014 I'll use a default 12\u00d712\u00d712 box)_")
        return "\n".join(parts)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle conversational shipping flow"""
        if message.author.bot:
            return

        channel_id = self.config.get("channel_id")
        if not channel_id or str(message.channel.id) != str(channel_id):
            return

        user_id = message.author.id
        content = message.content.strip()
        content_lower = content.lower()

        session = self.sessions.get(user_id)

        # Cancel command
        if content_lower == "cancel" and session:
            del self.sessions[user_id]
            await message.reply("Shipment cancelled.")
            return

        # Start new session
        if content_lower in ["ship", "shipping", "new shipment", "create label", "new label"]:
            self.sessions[user_id] = {
                "step": "awaiting_info",
                "collected": {},
                "missing": [],
            }

            default_origin = self.config.get("default_origin_address", {})

            embed = discord.Embed(
                title="\U0001f4e6 New Shipment",
                description=(
                    "**Tell me about your shipment!**\n\n"
                    "You can type everything at once or piece by piece.\n"
                    "I need: **recipient name, address, phone, and package weight**."
                ),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Examples",
                value=(
                    "`Stanley Huang, 960 W 7th St, Los Angeles, CA 90017, 9178650776, 5lbs 12x8x4`\n"
                    "`ship 5lbs to austin tx`\n"
                    "`John Doe, 123 Main St, Austin TX 78701`"
                ),
                inline=False
            )
            embed.set_footer(text=f"Shipping from: {default_origin.get('city', 'N/A')}, {default_origin.get('state', 'N/A')} {default_origin.get('zip', 'N/A')}")

            await message.reply(embed=embed)
            return

        # Handle active session — AI parse loop
        if session and session.get("step") == "awaiting_info":
            if not self.gemini:
                await message.reply("\u274c AI service not available. Please try again later.")
                return

            async with message.channel.typing():
                result = await self.gemini.parse_shipping_info(content, session.get("collected"))

            collected = result["collected"]
            missing = result["missing"]
            has_dimensions = result["has_dimensions"]

            session["collected"] = collected
            session["missing"] = missing

            if missing:
                prompt_text = self._build_missing_prompt(missing, has_dimensions)
                # Show what we've collected so far
                collected_display = []
                if collected.get("to_name"):
                    collected_display.append(f"**Name:** {collected['to_name']}")
                if collected.get("to_street"):
                    collected_display.append(f"**Street:** {collected['to_street']}")
                if collected.get("to_city") or collected.get("to_state"):
                    city_state = f"{collected.get('to_city', '?')}, {collected.get('to_state', '?')} {collected.get('to_zip', '')}".strip()
                    collected_display.append(f"**Location:** {city_state}")
                if collected.get("to_phone"):
                    collected_display.append(f"**Phone:** {collected['to_phone']}")
                if collected.get("weight"):
                    collected_display.append(f"**Weight:** {collected['weight']} lbs")
                if has_dimensions:
                    collected_display.append(f"**Dimensions:** {collected.get('length')}x{collected.get('width')}x{collected.get('height')} in")

                embed = discord.Embed(
                    title="\U0001f4cb Shipment Info",
                    color=discord.Color.orange()
                )
                if collected_display:
                    embed.add_field(name="Collected so far", value="\n".join(collected_display), inline=False)
                embed.add_field(name="What's missing", value=prompt_text, inline=False)

                await message.reply(embed=embed)
                return

            # All required fields collected — move to confirmation
            session["step"] = "confirming"

            # Set default dimensions if not provided
            if not has_dimensions:
                collected.setdefault("length", 12)
                collected.setdefault("width", 12)
                collected.setdefault("height", 12)

            # Build from-address: use config defaults, override with user-provided from_* fields
            from_addr = self._get_from_address()
            if collected.get("from_street"):
                from_addr = Address(
                    name=collected.get("from_name", from_addr.name),
                    street1=collected["from_street"],
                    city=collected.get("from_city", from_addr.city),
                    state=collected.get("from_state", from_addr.state),
                    zip=collected.get("from_zip", from_addr.zip),
                    country="US",
                    phone=collected.get("from_phone", from_addr.phone)
                )

            to_addr = Address(
                name=collected["to_name"],
                street1=collected["to_street"],
                city=collected["to_city"],
                state=collected["to_state"],
                zip=collected["to_zip"],
                country="US",
                phone=collected["to_phone"]
            )
            parcel = Parcel(
                length=collected.get("length", 12),
                width=collected.get("width", 12),
                height=collected.get("height", 12),
                weight=collected["weight"]
            )

            session["from_addr"] = from_addr
            session["to_addr"] = to_addr
            session["parcel"] = parcel

            dim_text = f"{int(parcel.length)}x{int(parcel.width)}x{int(parcel.height)} in"

            embed = discord.Embed(
                title="\U0001f4e6 Confirm Shipment Details",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="\U0001f4e4 From",
                value=f"{from_addr.name}\n{from_addr.street1}\n{from_addr.city}, {from_addr.state} {from_addr.zip}",
                inline=True
            )
            embed.add_field(
                name="\U0001f4e5 To",
                value=f"{to_addr.name}\n{to_addr.street1}\n{to_addr.city}, {to_addr.state} {to_addr.zip}\n{to_addr.phone}",
                inline=True
            )
            embed.add_field(
                name="\U0001f4e6 Package",
                value=f"{parcel.weight} lbs \u2022 {dim_text}",
                inline=False
            )
            embed.set_footer(text="Click Confirm to validate the address and continue.")

            view = ShipmentConfirmView(self, user_id)
            await message.reply(embed=embed, view=view)
            return

    async def _validate_and_select_carrier(self, interaction: discord.Interaction):
        """Step 2: Validate address via ShipEngine, then show carrier selection"""
        user_id = interaction.user.id
        session = self.sessions.get(user_id)
        if not session:
            return

        to_addr = session["to_addr"]

        # Use ShipEngine for address validation (best USPS data)
        validation_client = self.clients.get("shipengine")
        if not validation_client:
            # Skip validation if no ShipEngine client
            await self._show_carrier_selection(interaction)
            return

        try:
            result = await asyncio.to_thread(validation_client.validate_address, to_addr)
        except Exception as e:
            logger.error(f"Address validation error: {e}")
            # Continue without validation
            await interaction.followup.send(f"\u26a0\ufe0f Could not validate address: {e}\nContinuing anyway...")
            await self._show_carrier_selection(interaction)
            return

        if result.is_valid and result.validated_address:
            validated = result.validated_address
            # Check if address was corrected
            changed = (
                validated.street1.lower() != to_addr.street1.lower() or
                validated.city.lower() != to_addr.city.lower() or
                validated.state.upper() != to_addr.state.upper() or
                validated.zip != to_addr.zip
            )

            if changed:
                res_label = "Residential" if validated.is_residential else "Commercial"
                embed = discord.Embed(
                    title="\U0001f4ec Address Correction Suggested",
                    description=f"ShipEngine suggests a correction ({res_label}):",
                    color=discord.Color.yellow()
                )
                embed.add_field(
                    name="Your Input",
                    value=f"{to_addr.street1}\n{to_addr.city}, {to_addr.state} {to_addr.zip}",
                    inline=True
                )
                embed.add_field(
                    name="Suggested",
                    value=f"{validated.street1}\n{validated.city}, {validated.state} {validated.zip}",
                    inline=True
                )

                view = AddressCorrectionView(self, user_id, to_addr, validated, validated.is_residential)
                await interaction.followup.send(embed=embed, view=view)
                return
            else:
                # Address matched — update with validated version (gets residential flag)
                session["to_addr"] = validated

        elif not result.is_valid:
            msgs = "\n".join(result.messages) if result.messages else "Address could not be verified."
            embed = discord.Embed(
                title="\u274c Address Validation Failed",
                description=f"{msgs}\n\nPlease type a corrected address.",
                color=discord.Color.red()
            )
            session["step"] = "awaiting_info"
            # Keep collected data but clear address fields so user re-enters
            for key in ["to_street", "to_city", "to_state", "to_zip"]:
                session["collected"].pop(key, None)
            session["missing"] = ["to_street", "to_city", "to_state", "to_zip"]
            await interaction.followup.send(embed=embed)
            return

        await self._show_carrier_selection(interaction)

    async def _show_carrier_selection(self, interaction: discord.Interaction):
        """Show carrier dropdown"""
        user_id = interaction.user.id
        session = self.sessions.get(user_id)
        if not session:
            return

        session["step"] = "selecting_carrier"

        available = ["USPS", "UPS", "FedEx"]

        embed = discord.Embed(
            title="\U0001f69a Select a Carrier",
            description="Choose a carrier to see rates:",
            color=discord.Color.blue()
        )

        view = CarrierSelectView(self, user_id, available)
        await interaction.followup.send(embed=embed, view=view)

    async def _fetch_and_show_rates(self, interaction: discord.Interaction, user_id: int, carrier: str):
        """Fetch rates for a specific carrier from all providers, split by base/signature"""
        session = self.sessions.get(user_id)
        if not session:
            return

        from_addr = session["from_addr"]
        to_addr = session["to_addr"]
        parcel = session["parcel"]

        # Map display carrier to provider carrier name patterns
        carrier_map = {
            "USPS": ["usps"],
            "UPS": ["ups"],
            "FedEx": ["fedex"],
        }
        carrier_patterns = carrier_map.get(carrier, [carrier.lower()])

        def matches_carrier(rate: Rate) -> bool:
            provider_lower = rate.provider.lower()
            return any(p in provider_lower for p in carrier_patterns)

        # Fetch rates from all providers in parallel (base + signature)
        base_rates = []
        sig_rates = []
        errors = []

        def fetch_rates(client, sig_conf):
            return client.get_rates(from_addr, to_addr, parcel, signature_confirmation=sig_conf)

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {}
            for provider_name, client in self.clients.items():
                futures[executor.submit(fetch_rates, client, None)] = (provider_name, "base")
                futures[executor.submit(fetch_rates, client, "STANDARD")] = (provider_name, "signature")

            for future in as_completed(futures, timeout=20):
                provider_name, rate_type = futures[future]
                try:
                    rates = future.result(timeout=15)
                    filtered = [r for r in rates if matches_carrier(r)]
                    if rate_type == "base":
                        base_rates.extend(filtered)
                    else:
                        sig_rates.extend(filtered)
                except Exception as e:
                    logger.error(f"Error fetching {rate_type} rates from {provider_name}: {e}")
                    errors.append(f"{provider_name} ({rate_type}): {e}")

        # Deduplicate rates by service level — keep cheapest per service
        def dedup_rates(rates: List[Rate]) -> List[Rate]:
            seen = {}
            for rate in rates:
                key = rate.servicelevel_name.lower().strip()
                if key not in seen or rate.amount < seen[key].amount:
                    seen[key] = rate
            return sorted(seen.values(), key=lambda r: r.amount)

        base_rates = dedup_rates(base_rates)
        sig_rates = dedup_rates(sig_rates)

        if not base_rates and not sig_rates:
            error_detail = "\n".join(errors) if errors else "No rates available."
            await interaction.followup.send(f"\u274c No {carrier} rates found.\n{error_detail}")
            return

        session["rates"] = {"base": base_rates, "signature": sig_rates}

        # Build embed with standard + signature sections
        embed = discord.Embed(
            title=f"\U0001f69a {carrier} Rates",
            color=discord.Color.green()
        )

        if base_rates:
            lines = []
            for r in base_rates[:8]:
                days = f"{r.estimated_days}d" if r.estimated_days else "varies"
                lines.append(f"**${r.amount:.2f}** \u2022 {r.servicelevel_name} \u2022 {days}")
            embed.add_field(name="Standard Rates", value="\n".join(lines), inline=False)

        if sig_rates:
            lines = []
            for r in sig_rates[:8]:
                days = f"{r.estimated_days}d" if r.estimated_days else "varies"
                lines.append(f"**${r.amount:.2f}** \u2022 {r.servicelevel_name} [SIG] \u2022 {days}")
            embed.add_field(name="Signature Required Rates", value="\n".join(lines), inline=False)

        embed.set_footer(text="Select a rate from the dropdown below")

        view = RateSelectView(self, base_rates, sig_rates, from_addr, to_addr, parcel, user_id)
        await interaction.followup.send(embed=embed, view=view)

    async def _purchase_label(self, interaction: discord.Interaction, view: RateSelectView):
        """Purchase the selected shipping label"""
        rate = view.selected_rate
        if not rate:
            return

        # Determine which client to use based on the rate's provider info
        # Default to shipengine since it generated the rate_id
        purchase_client = None
        for name, client in self.clients.items():
            # Match by checking if the rate object_id was generated by this client
            # ShipEngine rate IDs start with "se-", EasyPost with "rate_", Shippo are UUIDs
            if rate.object_id.startswith("se-") and name == "shipengine":
                purchase_client = client
                break
            elif rate.object_id.startswith("rate_") and name == "easypost":
                purchase_client = client
                break
            elif name == "shippo" and not rate.object_id.startswith("se-") and not rate.object_id.startswith("rate_"):
                purchase_client = client
                break

        if not purchase_client:
            purchase_client = next(iter(self.clients.values()), None)

        if not purchase_client:
            await interaction.edit_original_response(content="\u274c No shipping client available.", embed=None, view=None)
            return

        try:
            label = await asyncio.to_thread(
                purchase_client.purchase_label,
                rate_id=rate.object_id,
                label_format="PDF",
                signature_confirmation=rate.signature_confirmation,
            )

            label_data = {
                "tracking_number": label.tracking_number,
                "carrier": label.carrier,
                "service": label.service,
                "provider": type(purchase_client).__name__.lower().replace("client", ""),
                "provider_label_id": getattr(label, 'label_id', None),
                "provider_shipment_id": rate.object_id,
                "rate_amount": label.cost,
                "label_url": label.label_url,
                "from_address": view.from_addr.model_dump(),
                "to_address": view.to_addr.model_dump(),
                "parcel": view.parcel.model_dump(),
                "discord_user_id": str(interaction.user.id),
                "signature_confirmation": rate.signature_confirmation,
            }

            # Fetch label PDF
            try:
                import requests as req
                pdf_response = req.get(label.label_url, timeout=30)
                if pdf_response.status_code == 200:
                    label_data["label_pdf_base64"] = base64.b64encode(pdf_response.content).decode()
            except Exception as e:
                logger.warning(f"Could not fetch label PDF: {e}")

            self.bot.db.save_label(label_data)

            if view.user_id in self.sessions:
                del self.sessions[view.user_id]

            sig_text = f"\n\U0001f58a Signature: {label.signature_confirmation}" if label.signature_confirmation else ""

            embed = discord.Embed(
                title="\u2705 Label Created!",
                color=discord.Color.green()
            )
            embed.add_field(name="\U0001f4cb Tracking", value=f"`{label.tracking_number}`", inline=False)
            embed.add_field(name="\U0001f69a Carrier", value=f"{label.carrier} {label.service}", inline=True)
            embed.add_field(name="\U0001f4b0 Cost", value=f"${label.cost:.2f}", inline=True)
            if sig_text:
                embed.add_field(name="\U0001f58a Signature", value=rate.signature_confirmation, inline=True)
            embed.add_field(name="\U0001f3f7\ufe0f Label", value=f"[Download PDF]({label.label_url})", inline=False)

            await interaction.edit_original_response(content=None, embed=embed, view=None)
            logger.info(f"Label created: {label.tracking_number} for user {interaction.user.id}")

        except Exception as e:
            logger.error(f"Error purchasing label: {e}")
            await interaction.edit_original_response(content=f"\u274c Error creating label: {str(e)}", embed=None, view=None)

    # --- Slash Commands ---

    @app_commands.command(name="ship", description="Start a new shipment")
    async def ship_command(self, interaction: discord.Interaction):
        """Slash command to start shipping flow"""
        if not self.clients:
            await interaction.response.send_message("Shipping service not configured.", ephemeral=True)
            return

        self.sessions[interaction.user.id] = {
            "step": "awaiting_info",
            "collected": {},
            "missing": [],
        }

        default_origin = self.config.get("default_origin_address", {})

        embed = discord.Embed(
            title="\U0001f4e6 New Shipment",
            description=(
                "**Tell me about your shipment!**\n\n"
                "You can type everything at once or piece by piece.\n"
                "I need: **recipient name, address, phone, and package weight**."
            ),
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Examples",
            value=(
                "`Stanley Huang, 960 W 7th St, Los Angeles, CA 90017, 9178650776, 5lbs 12x8x4`\n"
                "`ship 5lbs to austin tx`\n"
                "`John Doe, 123 Main St, Austin TX 78701`"
            ),
            inline=False
        )
        embed.set_footer(text=f"Shipping from: {default_origin.get('city', 'N/A')}, {default_origin.get('state', 'N/A')} {default_origin.get('zip', 'N/A')}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="labels", description="View your recent shipping labels")
    async def labels_command(self, interaction: discord.Interaction):
        """List user's recent labels"""
        labels = self.bot.db.get_user_labels(str(interaction.user.id), limit=10)

        if not labels:
            await interaction.response.send_message("You haven't created any labels yet.", ephemeral=True)
            return

        embed = discord.Embed(title="\U0001f4e6 Your Recent Labels", color=discord.Color.blue())

        for label in labels:
            status_emoji = "\u2705" if label["status"] == "active" else "\u274c"
            embed.add_field(
                name=f"{status_emoji} {label['tracking_number']}",
                value=f"{label['carrier']} \u2022 ${float(label['rate_amount']):.2f}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="label", description="Get details and re-download a label")
    @app_commands.describe(tracking="Tracking number")
    async def label_command(self, interaction: discord.Interaction, tracking: str):
        """Get label details and PDF"""
        label = self.bot.db.get_label_by_tracking(tracking)

        if not label:
            await interaction.response.send_message("Label not found.", ephemeral=True)
            return

        embed = discord.Embed(title=f"\U0001f3f7\ufe0f Label: {tracking}", color=discord.Color.blue())
        embed.add_field(name="Carrier", value=f"{label['carrier']} {label['service']}", inline=True)
        embed.add_field(name="Cost", value=f"${float(label['rate_amount']):.2f}", inline=True)
        embed.add_field(name="Status", value="\u2705 Active" if label["status"] == "active" else "\u274c Voided", inline=True)

        if label.get("label_url"):
            embed.add_field(name="Download", value=f"[Label PDF]({label['label_url']})", inline=False)

        files = []
        if label.get("label_pdf_base64"):
            try:
                pdf_bytes = base64.b64decode(label["label_pdf_base64"])
                files.append(discord.File(io.BytesIO(pdf_bytes), filename=f"label_{tracking}.pdf"))
            except Exception as e:
                logger.warning(f"Could not decode label PDF: {e}")

        await interaction.response.send_message(embed=embed, files=files, ephemeral=True)

    @app_commands.command(name="void", description="Void a shipping label")
    @app_commands.describe(tracking="Tracking number to void")
    async def void_command(self, interaction: discord.Interaction, tracking: str):
        """Void a shipping label"""
        label = self.bot.db.get_label_by_tracking(tracking)

        if not label:
            await interaction.response.send_message("Label not found.", ephemeral=True)
            return

        if label["status"] == "voided":
            await interaction.response.send_message("Label is already voided.", ephemeral=True)
            return

        if label.get("discord_user_id") != str(interaction.user.id):
            await interaction.response.send_message("You can only void your own labels.", ephemeral=True)
            return

        try:
            label_id = label.get("provider_label_id")
            if label_id:
                # Try to void with appropriate client
                void_client = None
                provider = label.get("provider", "")
                if "shipengine" in provider and "shipengine" in self.clients:
                    void_client = self.clients["shipengine"]
                elif "easypost" in provider and "easypost" in self.clients:
                    void_client = self.clients["easypost"]
                elif "shippo" in provider and "shippo" in self.clients:
                    void_client = self.clients["shippo"]
                else:
                    void_client = next(iter(self.clients.values()), None)

                if void_client and hasattr(void_client, 'void_label'):
                    void_result = await asyncio.to_thread(void_client.void_label, label_id)
                    if not void_result.get("approved"):
                        await interaction.response.send_message(
                            f"Void request not approved: {void_result.get('message', 'Unknown error')}",
                            ephemeral=True
                        )
                        return
        except Exception as e:
            logger.warning(f"Could not void label with provider: {e}")

        success = self.bot.db.void_label(tracking)
        if success:
            await interaction.response.send_message(f"\u2705 Label {tracking} has been voided.", ephemeral=True)
            logger.info(f"Label voided: {tracking} by user {interaction.user.id}")
        else:
            await interaction.response.send_message("Failed to void label.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ShippingCog(bot))
