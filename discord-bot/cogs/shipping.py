"""Shipping cog - AI-powered conversational shipping flow"""

import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import Dict, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta, timezone
import asyncio
import base64
import io
import logging
import re
import sys
import os

# Add shippo-frontend lib to path for importing shipping clients
lib_path = os.path.join(os.path.dirname(__file__), "..", "..", "shippo-frontend", "lib")
sys.path.insert(0, lib_path)

from services.gemini_client import GeminiClient
from google.genai import types as genai_types

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



class PackageTypeView(ui.View):
    """Ask user if shipping an envelope or a box"""

    def __init__(self, cog, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id

    @ui.button(label="Envelope", style=discord.ButtonStyle.primary, emoji="\u2709\ufe0f")
    async def envelope_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        session = self.cog.sessions.get(self.user_id)
        if session:
            session["package_type"] = "envelope"

        await interaction.response.edit_message(view=None)
        await self.cog._show_delivery_options(interaction)

    @ui.button(label="Box / Package", style=discord.ButtonStyle.primary, emoji="\U0001f4e6")
    async def box_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        session = self.cog.sessions.get(self.user_id)
        if session:
            session["package_type"] = "box"

        await interaction.response.edit_message(view=None)
        await self.cog._show_delivery_options(interaction)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        if self.user_id in self.cog.sessions:
            del self.cog.sessions[self.user_id]
        await interaction.response.edit_message(content="Shipment cancelled.", embed=None, view=None)
        self.stop()


class DeliveryOptionsView(ui.View):
    """Optional delivery options before fetching rates"""

    def __init__(self, cog, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.saturday = False

    @ui.button(label="Saturday Delivery", style=discord.ButtonStyle.secondary)
    async def saturday_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        self.saturday = not self.saturday
        button.style = discord.ButtonStyle.success if self.saturday else discord.ButtonStyle.secondary
        button.label = "\u2705 Saturday Delivery" if self.saturday else "Saturday Delivery"

        session = self.cog.sessions.get(self.user_id)
        if session:
            session["saturday_delivery"] = self.saturday

        await interaction.response.edit_message(view=self)

    @ui.button(label="Get Rates", style=discord.ButtonStyle.primary, emoji="\U0001f69a")
    async def continue_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        await interaction.response.edit_message(content="Fetching rates...", embed=None, view=None)
        await self.cog._fetch_all_rates(interaction)

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        if self.user_id in self.cog.sessions:
            del self.cog.sessions[self.user_id]
        await interaction.response.edit_message(content="Shipment cancelled.", embed=None, view=None)


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
            name="\U0001f4e4 From",
            value=f"{self.from_addr.name}\n{self.from_addr.street1}\n{self.from_addr.city}, {self.from_addr.state} {self.from_addr.zip}",
            inline=True
        )
        embed.add_field(
            name="\U0001f4e5 To",
            value=f"{self.to_addr.name}\n{self.to_addr.street1}\n{self.to_addr.city}, {self.to_addr.state} {self.to_addr.zip}",
            inline=True
        )
        embed.add_field(
            name="\U0001f4e6 Package",
            value=f"{self.parcel.weight} lbs \u2022 {int(self.parcel.length)}x{int(self.parcel.width)}x{int(self.parcel.height)} in",
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

        view = InsuranceView(self.cog, self, embed)
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


class InsuranceModal(ui.Modal, title="Add Insurance"):
    """Modal for entering insurance value"""

    amount = ui.TextInput(
        label="Declared Value (USD)",
        placeholder="e.g. 100.00",
        required=True,
        max_length=10,
    )

    def __init__(self, cog, rate_view: RateSelectView, confirm_embed: discord.Embed):
        super().__init__()
        self.cog = cog
        self.rate_view = rate_view
        self.confirm_embed = confirm_embed

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = float(self.amount.value.replace("$", "").replace(",", "").strip())
            if value <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("Please enter a valid dollar amount.", ephemeral=True)
            return

        session = self.cog.sessions.get(self.rate_view.user_id)
        if session:
            session["insured_value"] = value

        self.confirm_embed.add_field(
            name="\U0001f6e1\ufe0f Insurance",
            value=f"${value:.2f} declared value",
            inline=True
        )

        view = ConfirmPurchaseView(self.cog, self.rate_view)
        await interaction.response.edit_message(embed=self.confirm_embed, view=view)


class InsuranceView(ui.View):
    """Ask user if they want to add insurance before purchase"""

    def __init__(self, cog, rate_view: RateSelectView, confirm_embed: discord.Embed):
        super().__init__(timeout=300)
        self.cog = cog
        self.rate_view = rate_view
        self.confirm_embed = confirm_embed

    @ui.button(label="Add Insurance", style=discord.ButtonStyle.primary, emoji="\U0001f6e1\ufe0f")
    async def insurance_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.rate_view.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return
        modal = InsuranceModal(self.cog, self.rate_view, self.confirm_embed)
        await interaction.response.send_modal(modal)

    @ui.button(label="Skip - No Insurance", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.rate_view.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return
        view = ConfirmPurchaseView(self.cog, self.rate_view)
        await interaction.response.edit_message(embed=self.confirm_embed, view=view)

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.rate_view.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return
        if self.rate_view.user_id in self.cog.sessions:
            del self.cog.sessions[self.rate_view.user_id]
        await interaction.response.edit_message(content="Shipment cancelled.", embed=None, view=None)


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

    @ui.button(label="Go Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.rate_view.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        # Rebuild a fresh RateSelectView and restore the rate embeds
        rv = self.rate_view
        new_view = RateSelectView(self.cog, rv.base_rates, rv.sig_rates, rv.from_addr, rv.to_addr, rv.parcel, rv.user_id)
        embeds = getattr(rv, 'rate_embeds', [])
        new_view.rate_embeds = embeds
        await interaction.response.edit_message(embeds=embeds, view=new_view)

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

        # Initialize shipping clients (ShipEngine only for now)
        self.clients = {}
        if SHIPPING_AVAILABLE:
            try:
                if os.environ.get("SHIPENGINE_API_KEY"):
                    self.clients["shipengine"] = ShipEngineClient()
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
            default_origin = self.config.get("default_origin_address", {})
            system_context = self.gemini.build_shipping_system_context(default_origin) if self.gemini else ""

            self.sessions[user_id] = {
                "step": "awaiting_info",
                "collected": {},
                "missing": [],
                "messages": [
                    genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=system_context)]),
                    genai_types.Content(role="model", parts=[genai_types.Part.from_text(text="Ready to help with your shipment! Tell me the recipient details and package info.")]),
                ],
            }

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
                result = await self.gemini.process_shipping_message(
                    content, session["messages"]
                )

            if result.get("error"):
                logger.error(f"Gemini function calling error: {result['error']}")
                await message.reply("\u274c AI service encountered an error. Please try again.")
                return

            function_calls = result["function_calls"]
            model_response = result["model_response"]
            logger.info(f"Gemini returned {len(function_calls)} function call(s) for user {user_id}: {[fc['name'] for fc in function_calls]}")

            # Append user message + model response to history
            session["messages"].append(
                genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=content)])
            )
            if model_response:
                session["messages"].append(model_response)

            # Handle ask_clarification — relay question to user
            for fc in function_calls:
                if fc["name"] == "ask_clarification":
                    question = fc["args"].get("question", "Could you clarify?")
                    await message.reply(f"\U0001f914 {question}")
                    # Add function response + model ack to maintain turn alternation
                    session["messages"].append(
                        self.gemini.build_function_responses(function_calls)
                    )
                    session["messages"].append(
                        genai_types.Content(role="model", parts=[genai_types.Part.from_text(text=question)])
                    )
                    return

            # Process function calls to update session state
            collected = session["collected"]
            for fc in function_calls:
                if fc["name"] == "set_to_address":
                    for key, value in fc["args"].items():
                        collected[f"to_{key}"] = value
                elif fc["name"] == "set_from_address":
                    for key, value in fc["args"].items():
                        collected[f"from_{key}"] = value
                elif fc["name"] == "set_package":
                    for key, value in fc["args"].items():
                        collected[key] = value
                elif fc["name"] == "update_field":
                    field = fc["args"].get("field", "")
                    value = fc["args"].get("value", "")
                    if field in collected or field.startswith(("to_", "from_")) or field in ("weight", "length", "width", "height"):
                        # Convert numeric fields
                        if field in ("weight", "length", "width", "height"):
                            try:
                                value = float(value)
                            except (ValueError, TypeError):
                                pass
                        collected[field] = value

            # Add function responses + synthetic model ack to history
            # Gemini requires strict user/model turn alternation.
            # Function responses are role=user, so we must follow with a model turn
            # before the next user message.
            if function_calls:
                session["messages"].append(
                    self.gemini.build_function_responses(function_calls)
                )
                session["messages"].append(
                    genai_types.Content(role="model", parts=[genai_types.Part.from_text(text="OK, updated.")])
                )

            # Trim history to last 20 entries to control token cost
            if len(session["messages"]) > 20:
                # Keep first 2 (system context) + last 18
                session["messages"] = session["messages"][:2] + session["messages"][-18:]

            # Determine missing required fields
            required = ["to_name", "to_street", "to_city", "to_state", "to_zip", "to_phone", "weight"]
            missing = [f for f in required if not collected.get(f)]
            has_dimensions = all(collected.get(d) for d in ["length", "width", "height"])

            session["collected"] = collected
            session["missing"] = missing

            if missing:
                prompt_text = self._build_missing_prompt(missing, has_dimensions)
                # Show what we've collected so far
                collected_display = []
                if collected.get("to_name"):
                    collected_display.append(f"**Name:** {collected['to_name']}")
                if collected.get("to_street"):
                    street_display = collected['to_street']
                    if collected.get("to_street2"):
                        street_display += f", {collected['to_street2']}"
                    collected_display.append(f"**Street:** {street_display}")
                if collected.get("to_city") or collected.get("to_state"):
                    city_state = f"{collected.get('to_city', '?')}, {collected.get('to_state', '?')} {collected.get('to_zip', '')}".strip()
                    collected_display.append(f"**Location:** {city_state}")
                if collected.get("to_phone"):
                    collected_display.append(f"**Phone:** {collected['to_phone']}")
                if collected.get("to_email"):
                    collected_display.append(f"**Email:** {collected['to_email']}")
                if collected.get("weight"):
                    collected_display.append(f"**Weight:** {collected['weight']} lbs")
                if has_dimensions:
                    collected_display.append(f"**Dimensions:** {collected.get('length')}x{collected.get('width')}x{collected.get('height')} in")

                # Show from-address if user provided one
                if collected.get("from_street"):
                    from_parts = [collected.get("from_name", ""), collected["from_street"]]
                    if collected.get("from_city"):
                        from_parts.append(f"{collected['from_city']}, {collected.get('from_state', '')} {collected.get('from_zip', '')}")
                    collected_display.append(f"**From:** {', '.join(p for p in from_parts if p)}")

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
                street2=collected.get("to_street2") or None,
                city=collected["to_city"],
                state=collected["to_state"],
                zip=collected["to_zip"],
                country="US",
                phone=collected["to_phone"],
                email=collected.get("to_email") or None,
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
            to_lines = [to_addr.name, to_addr.street1]
            if to_addr.street2:
                to_lines.append(to_addr.street2)
            to_lines.append(f"{to_addr.city}, {to_addr.state} {to_addr.zip}")
            to_lines.append(to_addr.phone)
            if to_addr.email:
                to_lines.append(to_addr.email)
            embed.add_field(
                name="\U0001f4e5 To",
                value="\n".join(to_lines),
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

        # Use EasyPost for address validation (ShipEngine requires billing upgrade)
        validation_client = None
        try:
            if EasyPostClient and os.environ.get("EASYPOST_API_KEY"):
                validation_client = EasyPostClient()
        except Exception as e:
            logger.warning(f"Could not init EasyPost for validation: {e}")

        if not validation_client:
            await self._show_package_type(interaction)
            return

        try:
            result = await asyncio.to_thread(validation_client.validate_address, to_addr)
        except Exception as e:
            logger.error(f"Address validation error: {e}")
            await self._show_package_type(interaction)
            return

        if result.is_valid and result.validated_address:
            validated = result.validated_address
            # Auto-accept the validated address
            session["to_addr"] = validated

            # Show what changed (if anything)
            changed = (
                validated.street1.lower() != to_addr.street1.lower() or
                validated.city.lower() != to_addr.city.lower() or
                validated.state.upper() != to_addr.state.upper() or
                validated.zip != to_addr.zip
            )

            if changed:
                res_label = "Residential" if validated.is_residential else "Commercial"
                embed = discord.Embed(
                    title="\u2705 Address Validated",
                    description=f"Address corrected automatically ({res_label}):",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="Original",
                    value=f"{to_addr.street1}\n{to_addr.city}, {to_addr.state} {to_addr.zip}",
                    inline=True
                )
                embed.add_field(
                    name="Corrected",
                    value=f"{validated.street1}\n{validated.city}, {validated.state} {validated.zip}",
                    inline=True
                )
                await interaction.followup.send(embed=embed)

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

        await self._show_package_type(interaction)

    async def _show_package_type(self, interaction: discord.Interaction):
        """Ask envelope or box"""
        user_id = interaction.user.id
        session = self.sessions.get(user_id)
        if not session:
            return

        embed = discord.Embed(
            title="\u2709\ufe0f Package Type",
            description="Is this an **envelope** or a **box/package**?",
            color=discord.Color.blue()
        )

        view = PackageTypeView(self, user_id)
        await interaction.followup.send(embed=embed, view=view)

    async def _show_delivery_options(self, interaction: discord.Interaction):
        """Show optional delivery options before fetching rates"""
        user_id = interaction.user.id
        session = self.sessions.get(user_id)
        if not session:
            return

        embed = discord.Embed(
            title="\U0001f4cb Delivery Options",
            description="Toggle any options, then click **Get Rates**.",
            color=discord.Color.blue()
        )

        view = DeliveryOptionsView(self, user_id)
        await interaction.followup.send(embed=embed, view=view)

    async def _fetch_all_rates(self, interaction: discord.Interaction):
        """Fetch rates from all providers, display FedEx and USPS as separate embeds"""
        user_id = interaction.user.id
        session = self.sessions.get(user_id)
        if not session:
            return

        session["step"] = "selecting_rate"
        from_addr = session["from_addr"]
        to_addr = session["to_addr"]
        parcel = session["parcel"]

        # Determine package type for filtering returned rates
        package_type = session.get("package_type", "box")
        ENVELOPE_PKG_TYPES = {"flat_rate_envelope", "flat_rate_legal_envelope", "flat_rate_padded_envelope", "letter"}
        BOX_PKG_TYPES = {"package", "small_flat_rate_box", "medium_flat_rate_box", "large_flat_rate_box", "large_flat_rate_board_game_box", "regional_rate_box_a", "regional_rate_box_b"}

        def is_fedex_one_rate(rate: Rate) -> bool:
            """FedEx One Rate requires FedEx-branded packaging, filter these out"""
            return "one rate" in (rate.servicelevel_name or "").lower()

        def matches_package_type(rate: Rate) -> bool:
            """Filter rates based on user's envelope/box selection"""
            if is_fedex_one_rate(rate):
                return False
            pkg = (rate.package_type or "").lower()
            if not pkg:
                return True  # Keep rates with no package_type info
            if package_type == "envelope":
                return pkg in ENVELOPE_PKG_TYPES
            else:
                return pkg not in ENVELOPE_PKG_TYPES

        # Fetch rates from all providers in parallel (base + signature)
        all_base_rates = []
        all_sig_rates = []
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
                    if rate_type == "base":
                        all_base_rates.extend(rates)
                    else:
                        all_sig_rates.extend(rates)
                except Exception as e:
                    logger.error(f"Error fetching {rate_type} rates from {provider_name}: {e}")
                    errors.append(f"{provider_name} ({rate_type}): {e}")

        # Filter by package type, then split by carrier
        all_base_rates = [r for r in all_base_rates if matches_package_type(r)]
        all_sig_rates = [r for r in all_sig_rates if matches_package_type(r)]

        def matches_carrier(rate: Rate, carrier: str) -> bool:
            return carrier in rate.provider.lower()

        def dedup_rates(rates: List[Rate]) -> List[Rate]:
            seen = {}
            for rate in rates:
                key = (rate.servicelevel_name.lower().strip(), (rate.package_type or "").lower())
                if key not in seen or rate.amount < seen[key].amount:
                    seen[key] = rate
            return sorted(seen.values(), key=lambda r: r.amount)

        # Build per-carrier rate lists
        fedex_base = dedup_rates([r for r in all_base_rates if matches_carrier(r, "fedex")])
        fedex_sig = dedup_rates([r for r in all_sig_rates if matches_carrier(r, "fedex")])
        usps_base = dedup_rates([r for r in all_base_rates if matches_carrier(r, "usps")])
        usps_sig = dedup_rates([r for r in all_sig_rates if matches_carrier(r, "usps")])

        all_rates_combined = fedex_base + fedex_sig + usps_base + usps_sig

        if not all_rates_combined:
            error_detail = "\n".join(errors) if errors else "No rates available."
            await interaction.followup.send(f"\u274c No rates found.\n{error_detail}")
            return

        session["rates"] = {
            "fedex_base": fedex_base, "fedex_sig": fedex_sig,
            "usps_base": usps_base, "usps_sig": usps_sig,
        }

        def fmt_pkg(pkg_type: str) -> str:
            """Format package_type for display"""
            if not pkg_type or pkg_type == "package":
                return ""
            return " (" + pkg_type.replace("_", " ").title() + ")"

        def fmt_rate_line(r, sig=False):
            days = f"{r.estimated_days}d" if r.estimated_days else "varies"
            sig_tag = " [SIG]" if sig else ""
            pkg = fmt_pkg(r.package_type or "")
            return f"**${r.amount:.2f}** \u2022 {r.servicelevel_name}{pkg}{sig_tag} \u2022 {days}"

        # Build FedEx embed
        fedex_embed = discord.Embed(
            title="\U0001f69a FedEx Rates",
            color=discord.Color.purple()
        )
        if fedex_base:
            lines = [fmt_rate_line(r) for r in fedex_base[:8]]
            fedex_embed.add_field(name="Standard", value="\n".join(lines), inline=False)
        if fedex_sig:
            lines = [fmt_rate_line(r, sig=True) for r in fedex_sig[:8]]
            fedex_embed.add_field(name="Signature Required", value="\n".join(lines), inline=False)
        if not fedex_base and not fedex_sig:
            fedex_embed.description = "No FedEx rates available"

        # Build USPS embed
        usps_embed = discord.Embed(
            title="\U0001f4ee USPS Rates",
            color=discord.Color.blue()
        )
        if usps_base:
            lines = [fmt_rate_line(r) for r in usps_base[:8]]
            usps_embed.add_field(name="Standard", value="\n".join(lines), inline=False)
        if usps_sig:
            lines = [fmt_rate_line(r, sig=True) for r in usps_sig[:8]]
            usps_embed.add_field(name="Signature Required", value="\n".join(lines), inline=False)
        if not usps_base and not usps_sig:
            usps_embed.description = "No USPS rates available"

        rate_embeds = [fedex_embed, usps_embed]
        view = RateSelectView(self, fedex_base + usps_base, fedex_sig + usps_sig, from_addr, to_addr, parcel, user_id)
        view.rate_embeds = rate_embeds
        await interaction.followup.send(embeds=rate_embeds, view=view)

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
            label_format = self.config.get("label_format", "pdf").upper()
            label_layout = self.config.get("label_layout", "4x6")

            # Get insurance value if set in session
            session = self.sessions.get(view.user_id, {})
            insured_value = session.get("insured_value")

            label = await asyncio.to_thread(
                purchase_client.purchase_label,
                rate_id=rate.object_id,
                label_format=label_format,
                label_layout=label_layout,
                signature_confirmation=rate.signature_confirmation,
                insured_value=insured_value,
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

            # Post to labels log channel if configured
            log_channel_id = self.config.get("labels_log_channel_id")
            if log_channel_id:
                try:
                    channel = self.bot.get_channel(int(log_channel_id))
                    if channel:
                        log_embed = discord.Embed(
                            title="\U0001f3f7\ufe0f New Label Purchased",
                            color=discord.Color.green(),
                            timestamp=discord.utils.utcnow()
                        )
                        log_embed.add_field(name="Tracking", value=f"`{label.tracking_number}`", inline=True)
                        log_embed.add_field(name="Carrier", value=f"{label.carrier} {label.service}", inline=True)
                        log_embed.add_field(name="Cost", value=f"${label.cost:.2f}", inline=True)
                        log_embed.add_field(
                            name="From",
                            value=f"{view.from_addr.city}, {view.from_addr.state} {view.from_addr.zip}",
                            inline=True
                        )
                        log_embed.add_field(
                            name="To",
                            value=f"{view.to_addr.name}\n{view.to_addr.city}, {view.to_addr.state} {view.to_addr.zip}",
                            inline=True
                        )
                        log_embed.add_field(
                            name="Package",
                            value=f"{view.parcel.weight} lbs",
                            inline=True
                        )
                        if label.label_url:
                            log_embed.add_field(name="Label", value=f"[Download PDF]({label.label_url})", inline=False)
                        log_embed.set_footer(text=f"Purchased by {interaction.user.display_name}")

                        log_files = []
                        if label_data.get("label_pdf_base64"):
                            try:
                                pdf_bytes = base64.b64decode(label_data["label_pdf_base64"])
                                log_files.append(discord.File(io.BytesIO(pdf_bytes), filename=f"label_{label.tracking_number}.pdf"))
                            except Exception:
                                pass

                        await channel.send(embed=log_embed, files=log_files)
                except Exception as e:
                    logger.warning(f"Could not post to labels log channel: {e}")

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

        default_origin = self.config.get("default_origin_address", {})
        system_context = self.gemini.build_shipping_system_context(default_origin) if self.gemini else ""

        self.sessions[interaction.user.id] = {
            "step": "awaiting_info",
            "collected": {},
            "missing": [],
            "messages": [
                genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=system_context)]),
                genai_types.Content(role="model", parts=[genai_types.Part.from_text(text="Ready to help with your shipment! Tell me the recipient details and package info.")]),
            ],
        }

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

    # --- Tracking ---

    @staticmethod
    def _detect_carrier(tracking_number: str) -> Optional[str]:
        """Auto-detect carrier from tracking number format.

        - USPS: starts with '9', 20-22 digits
        - UPS: starts with '1Z'
        - FedEx: 12-15 digits
        """
        cleaned = tracking_number.strip().upper()
        if cleaned.startswith("1Z"):
            return "ups"
        if cleaned.startswith("9") and cleaned.isdigit() and 20 <= len(cleaned) <= 22:
            return "usps"
        if cleaned.isdigit() and 12 <= len(cleaned) <= 15:
            return "fedex"
        return None

    @staticmethod
    def _tracking_status_display(status: str) -> str:
        """Return a user-friendly status string with emoji."""
        status_map = {
            "pre_transit": "\U0001f4e6 Pre-Transit",
            "in_transit": "\U0001f69a In Transit",
            "out_for_delivery": "\U0001f3e0 Out for Delivery",
            "delivered": "\u2705 Delivered",
            "return_to_sender": "\u21a9\ufe0f Return to Sender",
            "failure": "\u274c Delivery Failed",
        }
        return status_map.get(status, f"\U0001f4cb {status}")

    @app_commands.command(name="track", description="Track a shipment")
    @app_commands.describe(
        tracking="Tracking number",
        carrier="Carrier (auto-detected if label is in our system)"
    )
    @app_commands.choices(carrier=[
        app_commands.Choice(name="USPS", value="usps"),
        app_commands.Choice(name="FedEx", value="fedex"),
        app_commands.Choice(name="UPS", value="ups"),
    ])
    async def track_command(self, interaction: discord.Interaction, tracking: str,
                            carrier: Optional[app_commands.Choice[str]] = None):
        """Track a shipment by tracking number"""
        await interaction.response.defer(ephemeral=True)

        # Resolve the carrier string
        carrier_code = carrier.value if carrier else None

        # Check our DB first
        label = self.bot.db.get_label_by_tracking(tracking)
        if label and not carrier_code:
            # Use the carrier from the DB record
            db_carrier = (label.get("carrier") or "").lower()
            # Normalize common carrier names
            if "fedex" in db_carrier:
                carrier_code = "fedex"
            elif "usps" in db_carrier:
                carrier_code = "usps"
            elif "ups" in db_carrier:
                carrier_code = "ups"
            else:
                carrier_code = db_carrier

        # Auto-detect from tracking number format if still unknown
        if not carrier_code:
            carrier_code = self._detect_carrier(tracking)

        if not carrier_code:
            await interaction.followup.send(
                "\u274c Could not determine carrier. Please specify the carrier using the `carrier` option.",
                ephemeral=True
            )
            return

        # Create or reuse EasyPost client for tracking
        easypost_client = None
        if "easypost" in self.clients:
            easypost_client = self.clients["easypost"]
        elif SHIPPING_AVAILABLE and EasyPostClient and os.environ.get("EASYPOST_API_KEY"):
            try:
                easypost_client = EasyPostClient()
            except Exception as e:
                logger.warning(f"Could not initialize EasyPost client for tracking: {e}")

        if not easypost_client:
            await interaction.followup.send(
                "\u274c Tracking service not available (EasyPost not configured).",
                ephemeral=True
            )
            return

        try:
            result = await asyncio.to_thread(easypost_client.track_shipment, carrier_code, tracking)
        except Exception as e:
            logger.error(f"Tracking error: {e}")
            await interaction.followup.send(f"\u274c Tracking failed: {str(e)}", ephemeral=True)
            return

        # Build the tracking embed
        status = result.get("status", "unknown")
        status_display = self._tracking_status_display(status)

        # Choose embed color based on status
        color_map = {
            "delivered": discord.Color.green(),
            "in_transit": discord.Color.blue(),
            "out_for_delivery": discord.Color.gold(),
            "failure": discord.Color.red(),
            "return_to_sender": discord.Color.orange(),
        }
        embed_color = color_map.get(status, discord.Color.greyple())

        embed = discord.Embed(
            title=f"{status_display}",
            color=embed_color
        )
        embed.add_field(name="\U0001f4cb Tracking Number", value=f"`{tracking}`", inline=True)
        embed.add_field(name="\U0001f69a Carrier", value=result.get("carrier", carrier_code).upper(), inline=True)

        if result.get("status_details"):
            embed.add_field(name="\U0001f4dd Details", value=result["status_details"], inline=False)

        if result.get("location"):
            embed.add_field(name="\U0001f4cd Location", value=result["location"], inline=True)

        if result.get("eta"):
            embed.add_field(name="\U0001f4c5 ETA", value=str(result["eta"]), inline=True)

        if result.get("status_date"):
            embed.add_field(name="\U0001f552 Last Update", value=str(result["status_date"]), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Tracking lookup: {tracking} ({carrier_code}) by user {interaction.user.id}")

    # --- Pickup Scheduling ---

    @app_commands.command(name="pickup", description="Schedule a carrier pickup")
    @app_commands.describe(
        date="Pickup date (YYYY-MM-DD, or 'today', 'tomorrow')",
        start_time="Pickup window start (HH:MM, default 08:00)",
        end_time="Pickup window end (HH:MM, default 17:00)",
        notes="Pickup notes (e.g. 'Ring doorbell')"
    )
    async def pickup_command(self, interaction: discord.Interaction, date: str,
                             start_time: str = "08:00", end_time: str = "17:00",
                             notes: str = None):
        """Schedule a carrier pickup for today's labels"""
        await interaction.response.defer(ephemeral=True)

        # Parse the date
        date_lower = date.strip().lower()
        if date_lower == "today":
            pickup_date = datetime.now(timezone.utc).date()
        elif date_lower == "tomorrow":
            pickup_date = datetime.now(timezone.utc).date() + timedelta(days=1)
        else:
            try:
                pickup_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
            except ValueError:
                await interaction.followup.send(
                    "\u274c Invalid date format. Use YYYY-MM-DD, 'today', or 'tomorrow'.",
                    ephemeral=True
                )
                return

        # Validate time format
        time_pattern = re.compile(r"^\d{2}:\d{2}$")
        if not time_pattern.match(start_time) or not time_pattern.match(end_time):
            await interaction.followup.send(
                "\u274c Invalid time format. Use HH:MM (e.g. 08:00).",
                ephemeral=True
            )
            return

        # Check for ShipEngine client
        shipengine_client = self.clients.get("shipengine")
        if not shipengine_client:
            await interaction.followup.send(
                "\u274c Pickup scheduling requires ShipEngine. No ShipEngine client configured.",
                ephemeral=True
            )
            return

        # Get today's active labels with provider_label_id
        labels = self.bot.db.get_todays_active_labels()
        if not labels:
            await interaction.followup.send(
                "\u274c No active labels found for today. Create a label first before scheduling a pickup.",
                ephemeral=True
            )
            return

        label_ids = [lbl["provider_label_id"] for lbl in labels if lbl.get("provider_label_id")]
        if not label_ids:
            await interaction.followup.send(
                "\u274c No labels with valid provider IDs found for pickup.",
                ephemeral=True
            )
            return

        # Get contact info from default origin address
        default_origin = self.config.get("default_origin_address", {})
        contact_name = default_origin.get("name", "Pickup Contact")
        contact_phone = default_origin.get("phone", "5551234567")

        # Build confirmation embed
        pickup_date_str = pickup_date.isoformat()
        label_summary = "\n".join(
            f"`{lbl['tracking_number']}` - {lbl['carrier']}"
            for lbl in labels[:10]
        )

        confirm_embed = discord.Embed(
            title="\U0001f69a Confirm Pickup",
            description="Review the pickup details below and click **Confirm** to schedule.",
            color=discord.Color.blue()
        )
        confirm_embed.add_field(
            name="\U0001f4c5 Date",
            value=pickup_date_str,
            inline=True
        )
        confirm_embed.add_field(
            name="\u23f0 Window",
            value=f"{start_time} - {end_time}",
            inline=True
        )
        confirm_embed.add_field(
            name="\U0001f464 Contact",
            value=f"{contact_name}\n{contact_phone}",
            inline=True
        )
        confirm_embed.add_field(
            name=f"\U0001f4e6 Labels ({len(label_ids)})",
            value=label_summary or "None",
            inline=False
        )
        if notes:
            confirm_embed.add_field(name="\U0001f4dd Notes", value=notes, inline=False)

        view = PickupConfirmView(
            self, interaction.user.id, shipengine_client, label_ids,
            contact_name, contact_phone, pickup_date_str, start_time, end_time, notes
        )
        await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)

    # --- Preset Commands ---

    preset_group = app_commands.Group(name="preset", description="Manage package presets")

    @preset_group.command(name="add", description="Save a package preset")
    @app_commands.describe(
        name="Preset name (e.g. 'Standard Box')",
        length="Length in inches",
        width="Width in inches",
        height="Height in inches",
        weight="Weight in pounds"
    )
    async def preset_add(self, interaction: discord.Interaction, name: str,
                         length: float, width: float, height: float, weight: float):
        self.bot.db.save_preset(name, length, width, height, weight, str(interaction.user.id))
        await interaction.response.send_message(
            f"\u2705 Preset **{name}** saved ({length}x{width}x{height} in, {weight} lbs)",
            ephemeral=True
        )

    @preset_group.command(name="list", description="View your package presets")
    async def preset_list(self, interaction: discord.Interaction):
        presets = self.bot.db.get_presets(str(interaction.user.id))
        if not presets:
            await interaction.response.send_message("No presets saved. Use `/preset add` to create one.", ephemeral=True)
            return

        embed = discord.Embed(title="\U0001f4e6 Package Presets", color=discord.Color.blue())
        for p in presets:
            embed.add_field(
                name=f"{p['name']} (#{p['id']})",
                value=f"{float(p['length'])}x{float(p['width'])}x{float(p['height'])} in \u2022 {float(p['weight'])} lbs",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @preset_group.command(name="delete", description="Delete a package preset")
    @app_commands.describe(preset_id="Preset ID (from /preset list)")
    async def preset_delete(self, interaction: discord.Interaction, preset_id: int):
        success = self.bot.db.delete_preset(preset_id, str(interaction.user.id))
        if success:
            await interaction.response.send_message(f"\u2705 Preset #{preset_id} deleted.", ephemeral=True)
        else:
            await interaction.response.send_message("Preset not found or you don't have permission.", ephemeral=True)


class PickupConfirmView(ui.View):
    """Confirmation view for pickup scheduling"""

    def __init__(self, cog, user_id: int, client, label_ids: List[str],
                 contact_name: str, contact_phone: str, pickup_date: str,
                 start_time: str, end_time: str, notes: Optional[str]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.client = client
        self.label_ids = label_ids
        self.contact_name = contact_name
        self.contact_phone = contact_phone
        self.pickup_date = pickup_date
        self.start_time = start_time
        self.end_time = end_time
        self.notes = notes

    @ui.button(label="Confirm Pickup", style=discord.ButtonStyle.success, emoji="\U0001f69a")
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your pickup request!", ephemeral=True)
            return

        await interaction.response.edit_message(content="\u23f3 Scheduling pickup...", embed=None, view=None)

        try:
            result = await asyncio.to_thread(
                self.client.schedule_pickup,
                label_ids=self.label_ids,
                contact_name=self.contact_name,
                contact_phone=self.contact_phone,
                pickup_date=self.pickup_date,
                start_time=self.start_time,
                end_time=self.end_time,
                notes=self.notes,
            )

            embed = discord.Embed(
                title="\u2705 Pickup Scheduled!",
                color=discord.Color.green()
            )
            if result.get("pickup_id"):
                embed.add_field(name="\U0001f194 Pickup ID", value=f"`{result['pickup_id']}`", inline=True)
            if result.get("confirmation_number"):
                embed.add_field(name="\U0001f4cb Confirmation", value=f"`{result['confirmation_number']}`", inline=True)
            embed.add_field(name="\U0001f4c6 Status", value=result.get("status", "scheduled").title(), inline=True)

            window = result.get("pickup_window", {})
            window_start = window.get("start_at", f"{self.pickup_date}T{self.start_time}:00Z")
            window_end = window.get("end_at", f"{self.pickup_date}T{self.end_time}:00Z")
            embed.add_field(
                name="\u23f0 Pickup Window",
                value=f"{window_start}\nto\n{window_end}",
                inline=False
            )
            embed.add_field(
                name="\U0001f4e6 Labels",
                value=f"{len(self.label_ids)} label(s)",
                inline=True
            )

            await interaction.edit_original_response(content=None, embed=embed, view=None)
            logger.info(f"Pickup scheduled: {result.get('pickup_id')} by user {interaction.user.id}")

        except Exception as e:
            logger.error(f"Pickup scheduling error: {e}")
            await interaction.edit_original_response(
                content=f"\u274c Pickup scheduling failed: {str(e)}", embed=None, view=None
            )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your pickup request!", ephemeral=True)
            return

        await interaction.response.edit_message(content="Pickup cancelled.", embed=None, view=None)
        self.stop()


async def setup(bot):
    await bot.add_cog(ShippingCog(bot))
