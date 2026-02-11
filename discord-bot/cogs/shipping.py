"""Shipping cog - natural language shipping quotes and label creation"""

import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import Dict, Optional, List
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

# Try to import shipping models and client
try:
    from models import Address, Parcel, Rate
    from easypost_client import EasyPostClient
    SHIPPING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import shipping modules: {e}")
    SHIPPING_AVAILABLE = False
    Address = None
    Parcel = None
    Rate = None
    EasyPostClient = None


class RateSelectView(ui.View):
    """View for selecting a shipping rate"""

    def __init__(self, cog, rates: List, from_addr, to_addr, parcel, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.rates = rates
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.parcel = parcel
        self.user_id = user_id
        self.selected_rate = None

        # Add buttons for top 5 rates
        for i, rate in enumerate(rates[:5]):
            button = ui.Button(
                label=f"{i+1}. ${rate.amount:.2f}",
                style=discord.ButtonStyle.primary,
                custom_id=f"rate_{i}"
            )
            button.callback = self._make_callback(i)
            self.add_item(button)

        # Add cancel button
        cancel_btn = ui.Button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
        cancel_btn.callback = self._cancel_callback
        self.add_item(cancel_btn)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("This isn't your quote!", ephemeral=True)
                return

            self.selected_rate = self.rates[index]
            await interaction.response.send_message(
                f"Purchasing {self.selected_rate.provider} {self.selected_rate.servicelevel_name}...",
                ephemeral=True
            )
            await self.cog._purchase_label(interaction, self)
            self.stop()

        return callback

    async def _cancel_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your quote!", ephemeral=True)
            return
        await interaction.response.send_message("Quote cancelled.", ephemeral=True)
        self.stop()


class ShippingCog(commands.Cog):
    """Natural language shipping quotes and labels"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.shipping
        self.gemini = None
        self.shipping_client = None
        self.active_sessions: Dict[int, Dict] = {}  # user_id -> session data

        # Initialize Gemini
        if bot.config.gemini_api_key:
            try:
                self.gemini = GeminiClient(bot.config.gemini_api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Gemini client: {e}")

        # Initialize shipping client
        if SHIPPING_AVAILABLE:
            try:
                self.shipping_client = EasyPostClient()
                logger.info("Shipping client initialized")
            except Exception as e:
                logger.warning(f"Could not initialize shipping client: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for shipping requests in designated channel"""
        if message.author.bot:
            return

        channel_id = self.config.get("channel_id")
        if not channel_id or str(message.channel.id) != str(channel_id):
            return

        # Check for shipping keywords
        shipping_keywords = ["ship", "shipping", "quote", "send", "package", "box", "label", "mail", "deliver"]
        content_lower = message.content.lower()
        if not any(kw in content_lower for kw in shipping_keywords):
            return

        await self._handle_shipping_message(message)

    async def _handle_shipping_message(self, message: discord.Message):
        """Process natural language shipping request"""
        if not self.gemini:
            await message.reply("AI service not configured. Please contact an administrator.")
            return

        if not self.shipping_client:
            await message.reply("Shipping service not configured. Please contact an administrator.")
            return

        async with message.channel.typing():
            # Parse the request
            parsed = await self.gemini.parse_shipping_request(message.content)

            if parsed.get("error"):
                await message.reply("Sorry, I couldn't understand that. Please try something like: 'Ship 5lbs to Austin TX 78701'")
                return

            missing = parsed.get("missing_fields", [])

            # Check if we have minimum required info
            has_destination = parsed.get("destination_zip") or (
                parsed.get("destination_city") and parsed.get("destination_state")
            )
            has_weight = parsed.get("weight")

            if not has_destination or not has_weight:
                # Ask follow-up question
                follow_up = await self.gemini.generate_follow_up_question(missing)
                self.active_sessions[message.author.id] = {
                    "parsed": parsed,
                    "channel_id": message.channel.id
                }
                await message.reply(f"I need a bit more info: {follow_up}")
                return

            # We have enough info - get rates
            await self._get_and_display_rates(message, parsed)

    async def _get_and_display_rates(self, message: discord.Message, parsed: Dict):
        """Fetch rates and display them"""
        if not SHIPPING_AVAILABLE or not self.shipping_client:
            await message.reply("Shipping service not available.")
            return

        # Build addresses
        default_origin = self.config.get("default_origin_address", {})
        from_addr = Address(
            name=default_origin.get("name", "Sender"),
            street1=default_origin.get("street1", "123 Main St"),
            city=default_origin.get("city", "Los Angeles"),
            state=default_origin.get("state", "CA"),
            zip=parsed.get("origin_zip") or default_origin.get("zip", "90001"),
            country="US"
        )

        # For destination, we need at minimum a zip code
        dest_zip = parsed.get("destination_zip") or "00000"
        to_addr = Address(
            name="Recipient",
            street1="123 Delivery St",
            city=parsed.get("destination_city") or "Unknown",
            state=parsed.get("destination_state") or "XX",
            zip=dest_zip,
            country="US"
        )

        parcel = Parcel(
            length=parsed.get("length") or 12,
            width=parsed.get("width") or 12,
            height=parsed.get("height") or 12,
            weight=parsed.get("weight") or 1
        )

        try:
            rates = self.shipping_client.get_rates(from_addr, to_addr, parcel)
            rates.sort(key=lambda r: r.amount)

            if not rates:
                await message.reply("No shipping rates found for this route. Please check the addresses and try again.")
                return

            # Build embed
            embed = discord.Embed(
                title=f"Shipping Quote to {to_addr.zip}",
                description=f"Package: {parcel.weight}lbs, {int(parcel.length)}x{int(parcel.width)}x{int(parcel.height)} in",
                color=discord.Color.green()
            )

            for i, rate in enumerate(rates[:5]):
                days = f"{rate.estimated_days} days" if rate.estimated_days else "varies"
                embed.add_field(
                    name=f"{i+1}. {rate.provider} {rate.servicelevel_name}",
                    value=f"**${rate.amount:.2f}** ({days})",
                    inline=True
                )

            embed.set_footer(text="Click a button below to purchase a label")

            # Create rate selection view
            view = RateSelectView(self, rates, from_addr, to_addr, parcel, message.author.id)
            await message.reply(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error getting rates: {e}")
            await message.reply(f"Error getting shipping rates: {str(e)}")

    async def _purchase_label(self, interaction: discord.Interaction, view: RateSelectView):
        """Purchase the selected shipping label"""
        rate = view.selected_rate
        if not rate:
            return

        try:
            label = self.shipping_client.purchase_label(
                rate_id=rate.object_id,
                label_format="PDF"
            )

            # Save to database
            label_data = {
                "tracking_number": label.tracking_number,
                "carrier": label.carrier,
                "service": label.service,
                "provider": "easypost",
                "provider_label_id": getattr(label, 'label_id', None),
                "provider_shipment_id": rate.shipment_id,
                "rate_amount": label.cost,
                "label_url": label.label_url,
                "from_address": view.from_addr.model_dump(),
                "to_address": view.to_addr.model_dump(),
                "parcel": view.parcel.model_dump(),
                "discord_user_id": str(interaction.user.id),
            }

            # Fetch and store PDF as base64
            try:
                import requests
                pdf_response = requests.get(label.label_url, timeout=30)
                if pdf_response.status_code == 200:
                    label_data["label_pdf_base64"] = base64.b64encode(pdf_response.content).decode()
            except Exception as e:
                logger.warning(f"Could not fetch label PDF: {e}")

            self.bot.db.save_label(label_data)

            # Send success message with label
            embed = discord.Embed(
                title="Label Created!",
                color=discord.Color.green()
            )
            embed.add_field(name="Tracking", value=label.tracking_number, inline=False)
            embed.add_field(name="Carrier", value=f"{label.carrier} {label.service}", inline=True)
            embed.add_field(name="Cost", value=f"${label.cost:.2f}", inline=True)
            embed.add_field(name="Label", value=f"[Download PDF]({label.label_url})", inline=False)

            await interaction.followup.send(embed=embed)
            logger.info(f"Label created: {label.tracking_number} for user {interaction.user.id}")

        except Exception as e:
            logger.error(f"Error purchasing label: {e}")
            await interaction.followup.send(f"Error creating label: {str(e)}")

    @app_commands.command(name="labels", description="View your recent shipping labels")
    async def labels_command(self, interaction: discord.Interaction):
        """List user's recent labels"""
        labels = self.bot.db.get_user_labels(str(interaction.user.id), limit=10)

        if not labels:
            await interaction.response.send_message("You haven't created any labels yet.", ephemeral=True)
            return

        embed = discord.Embed(title="Your Recent Labels", color=discord.Color.blue())

        for label in labels:
            status_emoji = "Active" if label["status"] == "active" else "Voided"
            embed.add_field(
                name=f"[{status_emoji}] {label['tracking_number']}",
                value=f"{label['carrier']} - ${float(label['rate_amount']):.2f}",
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

        embed = discord.Embed(title=f"Label: {tracking}", color=discord.Color.blue())
        embed.add_field(name="Carrier", value=f"{label['carrier']} {label['service']}", inline=True)
        embed.add_field(name="Cost", value=f"${float(label['rate_amount']):.2f}", inline=True)
        embed.add_field(name="Status", value=label["status"], inline=True)

        if label.get("label_url"):
            embed.add_field(name="Download", value=f"[Label PDF]({label['label_url']})", inline=False)

        # Attach PDF if available
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

        # Check if user owns the label
        if label.get("discord_user_id") != str(interaction.user.id):
            await interaction.response.send_message("You can only void your own labels.", ephemeral=True)
            return

        # Mark as voided in database (actual provider void API call could be added here)
        success = self.bot.db.void_label(tracking)
        if success:
            await interaction.response.send_message(f"Label {tracking} has been voided.", ephemeral=True)
            logger.info(f"Label voided: {tracking} by user {interaction.user.id}")
        else:
            await interaction.response.send_message("Failed to void label.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ShippingCog(bot))
