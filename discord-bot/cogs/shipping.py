"""Shipping cog - conversational shipping flow"""

import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import Dict, Optional, List
import base64
import io
import logging
import sys
import os
import re

# Add shippo-frontend lib to path for importing shipping clients
lib_path = os.path.join(os.path.dirname(__file__), "..", "..", "shippo-frontend", "lib")
sys.path.insert(0, lib_path)

logger = logging.getLogger(__name__)

# Try to import shipping models and client
try:
    from models import Address, Parcel, Rate
    from shipengine_client import ShipEngineClient
    SHIPPING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import shipping modules: {e}")
    SHIPPING_AVAILABLE = False
    Address = None
    Parcel = None
    Rate = None
    ShipEngineClient = None


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

        # Create select menu with rates
        options = []
        for i, rate in enumerate(rates[:15]):
            days = f" • {rate.estimated_days}d" if rate.estimated_days else ""
            label = f"${rate.amount:.2f} - {rate.provider} {rate.servicelevel_name}"[:100]
            options.append(discord.SelectOption(
                label=label,
                value=str(i),
                description=f"Delivery: {rate.estimated_days or 'varies'} days"[:100]
            ))

        if options:
            self.rate_select.options = options

    @ui.select(placeholder="Select a shipping rate...")
    async def rate_select(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        index = int(select.values[0])
        self.selected_rate = self.rates[index]
        rate = self.selected_rate

        # Show confirmation
        embed = discord.Embed(
            title="✅ Confirm Purchase",
            color=discord.Color.green()
        )
        embed.add_field(
            name="📍 To",
            value=f"{self.to_addr.name}\n{self.to_addr.street1}\n{self.to_addr.city}, {self.to_addr.state} {self.to_addr.zip}",
            inline=True
        )
        embed.add_field(
            name="📦 Package",
            value=f"{self.parcel.weight} lbs\n{int(self.parcel.length)}x{int(self.parcel.width)}x{int(self.parcel.height)} in",
            inline=True
        )
        embed.add_field(
            name="🚚 Service",
            value=f"{rate.provider}\n{rate.servicelevel_name}",
            inline=True
        )
        embed.add_field(
            name="💰 Cost",
            value=f"**${rate.amount:.2f}**",
            inline=True
        )
        embed.add_field(
            name="📅 Delivery",
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

    @ui.button(label="🏷️ Purchase Label", style=discord.ButtonStyle.success)
    async def purchase_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.rate_view.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        await interaction.response.edit_message(content="⏳ Creating your label...", embed=None, view=None)
        await self.cog._purchase_label(interaction, self.rate_view)

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.rate_view.user_id:
            await interaction.response.send_message("This isn't your shipment!", ephemeral=True)
            return

        if self.rate_view.user_id in self.cog.sessions:
            del self.cog.sessions[self.rate_view.user_id]

        await interaction.response.edit_message(content="Shipment cancelled.", embed=None, view=None)


class ShippingCog(commands.Cog):
    """Conversational shipping quotes and labels"""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.shipping
        self.shipping_client = None
        self.sessions: Dict[int, Dict] = {}  # user_id -> session data

        if SHIPPING_AVAILABLE:
            try:
                self.shipping_client = ShipEngineClient()
                logger.info("Shipping client initialized")
            except Exception as e:
                logger.warning(f"Could not initialize shipping client: {e}")

    def _parse_address(self, text: str) -> Optional[Dict]:
        """Parse address from natural text input"""
        # Expected format: Name, Street, City, State ZIP, Phone
        # Or: Name, Street, City, State, ZIP, Phone
        # Be flexible with formatting

        text = text.strip()

        # Try to extract phone number first (10 digits, possibly with formatting)
        phone_match = re.search(r'(\d{3}[-.\s]?\d{3}[-.\s]?\d{4}|\d{10})', text)
        phone = None
        if phone_match:
            phone = re.sub(r'[-.\s]', '', phone_match.group(1))
            text = text[:phone_match.start()] + text[phone_match.end():]

        # Extract ZIP code (5 digits, possibly with -4 extension)
        zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', text)
        zip_code = None
        if zip_match:
            zip_code = zip_match.group(1)

        # Extract state (2 letter abbreviation)
        states = ['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
                  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
                  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
                  'VA','WA','WV','WI','WY','DC']
        state_pattern = r'\b(' + '|'.join(states) + r')\b'
        state_match = re.search(state_pattern, text.upper())
        state = state_match.group(1) if state_match else None

        # Split by commas for the rest
        parts = [p.strip() for p in text.split(',') if p.strip()]

        if len(parts) < 3:
            return None

        # First part is name
        name = parts[0]

        # Second part is street
        street = parts[1]

        # Try to find city - usually the part before state
        city = None
        for i, part in enumerate(parts[2:], 2):
            part_upper = part.upper().strip()
            # Check if this part contains the state
            if state and state in part_upper:
                # City is everything before the state in this part
                city_part = re.sub(state_pattern, '', part_upper).strip()
                # Or city might be the previous part
                if not city_part and i > 2:
                    city = parts[i-1].strip()
                else:
                    city = city_part if city_part else parts[i-1].strip() if i > 2 else None
                break
            elif i == 2:
                # If no state in this part, assume it's the city
                city = part.strip()

        # Clean up city - remove state and zip if they got mixed in
        if city:
            city = re.sub(r'\b\d{5}\b', '', city).strip()
            city = re.sub(state_pattern, '', city.upper()).strip().title()

        if not all([name, street, city, state, zip_code]):
            return None

        return {
            "name": name,
            "street": street,
            "city": city,
            "state": state,
            "zip": zip_code,
            "phone": phone or "5551234567"
        }

    def _parse_package(self, text: str) -> Optional[Dict]:
        """Parse package dimensions and weight from text"""
        text = text.lower().strip()

        result = {"length": None, "width": None, "height": None, "weight": None}

        # Extract dimensions (patterns like "12x8x4", "12 x 8 x 4", "12x8x4in")
        dim_match = re.search(r'(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)', text)
        if dim_match:
            result["length"] = float(dim_match.group(1))
            result["width"] = float(dim_match.group(2))
            result["height"] = float(dim_match.group(3))

        # Extract weight (patterns like "5lbs", "5 lbs", "5 pounds", "5lb", "5 oz")
        weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)', text)
        if weight_match:
            result["weight"] = float(weight_match.group(1))
        else:
            # Try ounces
            oz_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:oz|ounces?)', text)
            if oz_match:
                result["weight"] = float(oz_match.group(1)) / 16

        if result["weight"] is None:
            return None

        # Default dimensions if not provided
        if result["length"] is None:
            result["length"] = 12
            result["width"] = 12
            result["height"] = 12

        return result

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

        # Check if user has an active session
        session = self.sessions.get(user_id)

        # Start new session
        if content_lower in ["ship", "shipping", "new shipment", "create label", "new label"]:
            self.sessions[user_id] = {"step": "awaiting_destination"}

            default_origin = self.config.get("default_origin_address", {})

            embed = discord.Embed(
                title="📦 New Shipment",
                description="**Where are you shipping to?**\n\nType the destination address:",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Format",
                value="`Name, Street Address, City, State ZIP, Phone`",
                inline=False
            )
            embed.add_field(
                name="Example",
                value="`John Doe, 123 Main St, Austin, TX 78701, 5125551234`",
                inline=False
            )
            embed.set_footer(text=f"Shipping from: {default_origin.get('city', 'N/A')}, {default_origin.get('state', 'N/A')} {default_origin.get('zip', 'N/A')}")

            await message.reply(embed=embed)
            return

        # Handle session steps
        if session:
            step = session.get("step")

            # Step 1: Parse destination address
            if step == "awaiting_destination":
                address = self._parse_address(content)

                if not address:
                    await message.reply(
                        "❌ Couldn't parse that address. Please use this format:\n"
                        "`Name, Street Address, City, State ZIP, Phone`\n\n"
                        "Example: `John Doe, 123 Main St, Austin, TX 78701, 5125551234`"
                    )
                    return

                session["destination"] = address
                session["step"] = "awaiting_package"

                embed = discord.Embed(
                    title="✅ Destination Set",
                    description=f"**{address['name']}**\n{address['street']}\n{address['city']}, {address['state']} {address['zip']}",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="📦 What are the package details?",
                    value="Type dimensions and weight:",
                    inline=False
                )
                embed.add_field(
                    name="Format",
                    value="`LxWxH weight` (e.g., `12x8x4 2lbs`)",
                    inline=False
                )
                embed.add_field(
                    name="Or just weight",
                    value="`2lbs` (uses default 12x12x12 box)",
                    inline=False
                )

                await message.reply(embed=embed)
                return

            # Step 2: Parse package details and get rates
            if step == "awaiting_package":
                package = self._parse_package(content)

                if not package:
                    await message.reply(
                        "❌ Couldn't parse package details. Please include at least the weight:\n"
                        "`12x8x4 2lbs` or just `2lbs`"
                    )
                    return

                session["package"] = package
                session["step"] = "selecting_rate"

                # Build addresses and get rates
                await self._fetch_and_show_rates(message, user_id)
                return

        # Cancel command
        if content_lower == "cancel" and session:
            del self.sessions[user_id]
            await message.reply("Shipment cancelled.")

    async def _fetch_and_show_rates(self, message: discord.Message, user_id: int):
        """Fetch rates and display them"""
        session = self.sessions.get(user_id)
        if not session:
            return

        dest = session.get("destination", {})
        pkg = session.get("package", {})

        default_origin = self.config.get("default_origin_address", {})
        from_addr = Address(
            name=default_origin.get("name", "Sender"),
            street1=default_origin.get("street1", "123 Main St"),
            city=default_origin.get("city", "Los Angeles"),
            state=default_origin.get("state", "CA"),
            zip=default_origin.get("zip", "90001"),
            country="US",
            phone=default_origin.get("phone", "5551234567")
        )

        to_addr = Address(
            name=dest.get("name", "Recipient"),
            street1=dest.get("street", ""),
            city=dest.get("city", ""),
            state=dest.get("state", ""),
            zip=dest.get("zip", ""),
            country="US",
            phone=dest.get("phone", "5551234567")
        )

        parcel = Parcel(
            length=pkg.get("length", 12),
            width=pkg.get("width", 12),
            height=pkg.get("height", 12),
            weight=pkg.get("weight", 1)
        )

        async with message.channel.typing():
            try:
                rates = self.shipping_client.get_rates(from_addr, to_addr, parcel)
                rates.sort(key=lambda r: r.amount)

                if not rates:
                    await message.reply("❌ No shipping rates found. Please check the address and try again.")
                    del self.sessions[user_id]
                    return

                session["rates"] = rates
                session["from_addr"] = from_addr
                session["to_addr"] = to_addr
                session["parcel"] = parcel

                embed = discord.Embed(
                    title="🚚 Shipping Rates",
                    description=f"**{len(rates)}** rates found for your shipment.",
                    color=discord.Color.green()
                )

                # Show top 5 in embed
                for i, rate in enumerate(rates[:5]):
                    days = f"{rate.estimated_days}d" if rate.estimated_days else "varies"
                    embed.add_field(
                        name=f"{rate.provider} {rate.servicelevel_name}",
                        value=f"**${rate.amount:.2f}** • {days}",
                        inline=True
                    )

                embed.set_footer(text="Select a rate from the dropdown below")

                view = RateSelectView(self, rates, from_addr, to_addr, parcel, user_id)
                await message.reply(embed=embed, view=view)

            except Exception as e:
                logger.error(f"Error getting rates: {e}")
                await message.reply(f"❌ Error getting rates: {str(e)}")
                del self.sessions[user_id]

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

            label_data = {
                "tracking_number": label.tracking_number,
                "carrier": label.carrier,
                "service": label.service,
                "provider": "shipengine",
                "provider_label_id": getattr(label, 'label_id', None),
                "provider_shipment_id": rate.object_id,
                "rate_amount": label.cost,
                "label_url": label.label_url,
                "from_address": view.from_addr.model_dump(),
                "to_address": view.to_addr.model_dump(),
                "parcel": view.parcel.model_dump(),
                "discord_user_id": str(interaction.user.id),
            }

            try:
                import requests
                pdf_response = requests.get(label.label_url, timeout=30)
                if pdf_response.status_code == 200:
                    label_data["label_pdf_base64"] = base64.b64encode(pdf_response.content).decode()
            except Exception as e:
                logger.warning(f"Could not fetch label PDF: {e}")

            self.bot.db.save_label(label_data)

            if view.user_id in self.sessions:
                del self.sessions[view.user_id]

            embed = discord.Embed(
                title="✅ Label Created!",
                color=discord.Color.green()
            )
            embed.add_field(name="📋 Tracking", value=f"`{label.tracking_number}`", inline=False)
            embed.add_field(name="🚚 Carrier", value=f"{label.carrier} {label.service}", inline=True)
            embed.add_field(name="💰 Cost", value=f"${label.cost:.2f}", inline=True)
            embed.add_field(name="🏷️ Label", value=f"[Download PDF]({label.label_url})", inline=False)

            await interaction.edit_original_response(content=None, embed=embed, view=None)
            logger.info(f"Label created: {label.tracking_number} for user {interaction.user.id}")

        except Exception as e:
            logger.error(f"Error purchasing label: {e}")
            await interaction.edit_original_response(content=f"❌ Error creating label: {str(e)}", embed=None, view=None)

    @app_commands.command(name="ship", description="Start a new shipment")
    async def ship_command(self, interaction: discord.Interaction):
        """Slash command to start shipping flow"""
        if not self.shipping_client:
            await interaction.response.send_message("Shipping service not configured.", ephemeral=True)
            return

        self.sessions[interaction.user.id] = {"step": "awaiting_destination"}

        default_origin = self.config.get("default_origin_address", {})

        embed = discord.Embed(
            title="📦 New Shipment",
            description="**Where are you shipping to?**\n\nType the destination address in this channel:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Format",
            value="`Name, Street Address, City, State ZIP, Phone`",
            inline=False
        )
        embed.add_field(
            name="Example",
            value="`John Doe, 123 Main St, Austin, TX 78701, 5125551234`",
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

        embed = discord.Embed(title="📦 Your Recent Labels", color=discord.Color.blue())

        for label in labels:
            status_emoji = "✅" if label["status"] == "active" else "❌"
            embed.add_field(
                name=f"{status_emoji} {label['tracking_number']}",
                value=f"{label['carrier']} • ${float(label['rate_amount']):.2f}",
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

        embed = discord.Embed(title=f"🏷️ Label: {tracking}", color=discord.Color.blue())
        embed.add_field(name="Carrier", value=f"{label['carrier']} {label['service']}", inline=True)
        embed.add_field(name="Cost", value=f"${float(label['rate_amount']):.2f}", inline=True)
        embed.add_field(name="Status", value="✅ Active" if label["status"] == "active" else "❌ Voided", inline=True)

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
            if label_id and self.shipping_client:
                void_result = self.shipping_client.void_label(label_id)
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
            await interaction.response.send_message(f"✅ Label {tracking} has been voided.", ephemeral=True)
            logger.info(f"Label voided: {tracking} by user {interaction.user.id}")
        else:
            await interaction.response.send_message("Failed to void label.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ShippingCog(bot))
