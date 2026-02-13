"""ShipEngine API client wrapper using REST API"""

import os
import requests
from datetime import datetime, timezone
from typing import List, Optional
import logging
from models import Address, Parcel, Rate, ShippingLabel, ValidationResult

logger = logging.getLogger(__name__)

class ShipEngineClient:
    """Wrapper around ShipEngine REST API"""

    BASE_URL = "https://api.shipengine.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize ShipEngine client

        Args:
            api_key: ShipEngine API key (defaults to SHIPENGINE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("SHIPENGINE_API_KEY", "")

        if not self.api_key:
            raise ValueError("ShipEngine API key not configured. Set SHIPENGINE_API_KEY in .env file")

        self.headers = {
            "API-Key": self.api_key,
            "Content-Type": "application/json"
        }

        # Cache carrier IDs after first fetch
        self._carrier_ids: Optional[List[str]] = None

        logger.info("Initialized ShipEngine client")

    def _get_carrier_ids(self) -> List[str]:
        """
        Get list of connected carrier IDs

        Returns:
            List of carrier IDs
        """
        if self._carrier_ids is not None:
            return self._carrier_ids

        try:
            response = requests.get(
                f"{self.BASE_URL}/carriers",
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                logger.warning(f"Failed to fetch carriers: {response.status_code}")
                return []

            data = response.json()
            carriers = data.get("carriers", [])
            self._carrier_ids = [c["carrier_id"] for c in carriers if c.get("carrier_id")]

            logger.info(f"Found {len(self._carrier_ids)} connected carriers")
            return self._carrier_ids

        except Exception as e:
            logger.warning(f"Failed to fetch carrier IDs: {str(e)}")
            return []

    def _address_to_dict(self, address: Address) -> dict:
        """Convert Address model to dict for ShipEngine API"""
        result = {
            "name": address.name,
            "address_line1": address.street1,
            "city_locality": address.city,
            "state_province": address.state,
            "postal_code": address.zip,
            "country_code": address.country,
        }

        # Add optional fields only if they have values
        if address.street2:
            result["address_line2"] = address.street2
        if address.phone:
            result["phone"] = address.phone

        return result

    def get_rates(self, from_address: Address, to_address: Address, parcel: Parcel,
                  signature_confirmation: Optional[str] = None) -> List[Rate]:
        """
        Get shipping rates from all carriers

        Args:
            from_address: Sender address
            to_address: Recipient address
            parcel: Package dimensions and weight
            signature_confirmation: Optional signature type ("STANDARD" maps to "signature")

        Returns:
            List of available rates
        """
        sig_info = f" with signature={signature_confirmation}" if signature_confirmation else ""
        logger.info(f"Getting rates from ShipEngine{sig_info}")

        # Get carrier IDs (required by ShipEngine API)
        carrier_ids = self._get_carrier_ids()
        if not carrier_ids:
            logger.warning("No carriers found or configured")
            return []

        # Map signature confirmation to ShipEngine confirmation option
        confirmation = "none"
        if signature_confirmation:
            sig_map = {
                "STANDARD": "signature",
                "ADULT": "adult_signature",
                "CERTIFIED": "signature",
                "INDIRECT": "delivery",
            }
            confirmation = sig_map.get(signature_confirmation, "signature")

        # Prepare shipment data for ShipEngine API
        # According to ShipEngine docs: POST /v1/rates requires "shipment" wrapper
        # and "rate_options" with carrier_ids
        payload = {
            "rate_options": {
                "carrier_ids": carrier_ids
            },
            "shipment": {
                "ship_to": self._address_to_dict(to_address),
                "ship_from": self._address_to_dict(from_address),
                "confirmation": confirmation,
                "packages": [
                    {
                        "weight": {
                            "value": parcel.weight,
                            "unit": "pound"
                        },
                        "dimensions": {
                            "length": parcel.length,
                            "width": parcel.width,
                            "height": parcel.height,
                            "unit": "inch"
                        }
                    }
                ]
            }
        }

        try:
            # Make API request
            response = requests.post(
                f"{self.BASE_URL}/rates",
                json=payload,
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                raise Exception(f"ShipEngine API returned status {response.status_code}: {response.text}")

            data = response.json()

            # Convert to Rate models
            rates = []
            if "rate_response" in data and "rates" in data["rate_response"]:
                for rate_data in data["rate_response"]["rates"]:
                    # Extract delivery date/days info
                    estimated_days = rate_data.get("estimated_delivery_days", None)
                    delivery_days = rate_data.get("delivery_days", None)

                    # Try to calculate days from delivery_date if available
                    if not estimated_days and not delivery_days:
                        # Check for guaranteed_date or estimated_delivery_date
                        delivery_date = rate_data.get("guaranteed_date") or rate_data.get("estimated_delivery_date")
                        if delivery_date:
                            # Parse date and calculate days from now
                            try:
                                from datetime import datetime
                                delivery_dt = datetime.fromisoformat(delivery_date.replace('Z', '+00:00'))
                                now = datetime.now(delivery_dt.tzinfo)
                                days_diff = (delivery_dt - now).days
                                estimated_days = max(1, days_diff)  # At least 1 day
                            except:
                                pass

                    # Use delivery_days if estimated_delivery_days is not available
                    if not estimated_days and delivery_days:
                        estimated_days = delivery_days

                    # Calculate total amount: shipping + confirmation + insurance + other
                    shipping_amt = float(rate_data.get("shipping_amount", {}).get("amount", 0))
                    confirmation_amt = float(rate_data.get("confirmation_amount", {}).get("amount", 0))
                    insurance_amt = float(rate_data.get("insurance_amount", {}).get("amount", 0))
                    other_amt = float(rate_data.get("other_amount", {}).get("amount", 0))
                    total_amount = shipping_amt + confirmation_amt + insurance_amt + other_amt

                    rate = Rate(
                        object_id=rate_data.get("rate_id", ""),
                        provider=rate_data.get("carrier_friendly_name", "Unknown"),
                        servicelevel_name=rate_data.get("service_type", ""),
                        servicelevel_token=rate_data.get("service_code", ""),
                        amount=total_amount,
                        currency=rate_data.get("shipping_amount", {}).get("currency", "USD"),
                        estimated_days=estimated_days,
                        duration_terms=None,
                        shipment_id=None,
                        signature_confirmation=signature_confirmation,
                        package_type=rate_data.get("package_type"),
                    )
                    rates.append(rate)

            logger.info(f"Retrieved {len(rates)} rates from ShipEngine")
            return rates

        except requests.exceptions.RequestException as e:
            logger.error(f"ShipEngine API request error: {str(e)}")
            raise Exception(f"ShipEngine API error: {str(e)}")
        except Exception as e:
            logger.error(f"ShipEngine error: {str(e)}")
            raise Exception(f"ShipEngine error: {str(e)}")

    def purchase_label(self, rate_id: str, label_format: str = "pdf",
                       label_layout: str = "4x6",
                       signature_confirmation: Optional[str] = None,
                       insured_value: Optional[float] = None) -> ShippingLabel:
        """
        Purchase shipping label using a rate ID

        Args:
            rate_id: Rate ID from get_rates()
            label_format: Label format (pdf, png, zpl) - default: pdf
            label_layout: Label size (4x6 or letter) - default: 4x6
            signature_confirmation: Signature type for tracking (already embedded in rate)
            insured_value: Optional declared value for insurance in USD

        Returns:
            ShippingLabel with tracking number and label URL
        """
        sig_info = f" (signature: {signature_confirmation})" if signature_confirmation else ""
        ins_info = f" (insured: ${insured_value:.2f})" if insured_value else ""
        logger.info(f"Purchasing label with rate ID: {rate_id}{sig_info}{ins_info}")

        # Prepare label purchase request
        # ShipEngine API: POST /v1/labels/rates/{rate_id}
        payload = {
            "label_format": label_format.lower(),
            "label_layout": label_layout,
        }

        if insured_value and insured_value > 0:
            payload["insurance_provider"] = "carrier"
            payload["packages"] = [{"insured_value": {"amount": insured_value, "currency": "usd"}}]

        try:
            # Make API request to purchase label
            response = requests.post(
                f"{self.BASE_URL}/labels/rates/{rate_id}",
                json=payload,
                headers=self.headers,
                timeout=30
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"ShipEngine API returned status {response.status_code}: {response.text}")

            data = response.json()

            # Extract label information
            label = ShippingLabel(
                tracking_number=data.get("tracking_number", ""),
                label_url=data.get("label_download", {}).get("pdf", "") if label_format.lower() == "pdf" else data.get("label_download", {}).get(label_format.lower(), ""),
                carrier=data.get("carrier_id", "Unknown"),
                service=data.get("service_code", "Unknown"),
                cost=float(data.get("shipment_cost", {}).get("amount", 0.0)),
                signature_confirmation=signature_confirmation,
                label_id=data.get("label_id", ""),  # Store for voiding
            )

            logger.info(f"Label created successfully. Tracking: {label.tracking_number}")
            return label

        except requests.exceptions.RequestException as e:
            logger.error(f"ShipEngine label purchase error: {str(e)}")
            raise Exception(f"ShipEngine label purchase error: {str(e)}")
        except Exception as e:
            logger.error(f"ShipEngine error: {str(e)}")
            raise Exception(f"ShipEngine error: {str(e)}")

    def validate_address(self, address: Address) -> ValidationResult:
        """
        Validate and normalize an address

        Args:
            address: Address to validate

        Returns:
            ValidationResult with validation status and corrected address
        """
        logger.info(f"Validating address in {address.city}, {address.state}")

        # Prepare address validation request
        # ShipEngine API: POST /v1/addresses/validate
        payload = [
            {
                "address_line1": address.street1,
                "city_locality": address.city,
                "state_province": address.state,
                "postal_code": address.zip,
                "country_code": address.country,
            }
        ]

        # Add optional fields
        if address.street2:
            payload[0]["address_line2"] = address.street2
        if address.name:
            payload[0]["name"] = address.name

        try:
            # Make API request to validate address
            response = requests.post(
                f"{self.BASE_URL}/addresses/validate",
                json=payload,
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                raise Exception(f"ShipEngine API returned status {response.status_code}: {response.text}")

            data = response.json()

            # ShipEngine returns an array, get first result
            if not data or len(data) == 0:
                raise Exception("No validation result returned")

            result_data = data[0]

            # Check validation status
            status = result_data.get("status", "unverified")
            is_valid = status in ["verified", "warning"]

            # Extract messages
            messages = []
            for msg in result_data.get("messages", []):
                message_text = msg.get("message", "")
                if message_text:
                    messages.append(message_text)

            result = ValidationResult(
                is_valid=is_valid,
                messages=messages,
                original_address=address,
            )

            # If address was validated or has warnings, create validated address
            if status in ["verified", "warning"]:
                matched = result_data.get("matched_address", result_data.get("normalized_address", {}))
                if matched:
                    result.validated_address = Address(
                        name=address.name,
                        street1=matched.get("address_line1", address.street1),
                        street2=matched.get("address_line2", "") or "",
                        city=matched.get("city_locality", address.city),
                        state=matched.get("state_province", address.state),
                        zip=matched.get("postal_code", address.zip),
                        country=matched.get("country_code", address.country),
                        phone=address.phone,
                        email=address.email,
                        is_residential=matched.get("address_residential_indicator") == "yes",
                    )
                    logger.info("Address validated successfully")
                else:
                    logger.warning(f"Address validation returned status '{status}' but no matched address")
            else:
                logger.warning(f"Address validation failed with status: {status}")

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"ShipEngine address validation error: {str(e)}")
            raise Exception(f"ShipEngine address validation error: {str(e)}")
        except Exception as e:
            logger.error(f"ShipEngine error: {str(e)}")
            raise Exception(f"ShipEngine error: {str(e)}")

    def schedule_pickup(self, label_ids: List[str], contact_name: str, contact_phone: str,
                        pickup_date: str, start_time: str = "08:00", end_time: str = "17:00",
                        contact_email: str = None, notes: str = None) -> dict:
        """
        Schedule a carrier pickup for one or more labels.

        Args:
            label_ids: List of ShipEngine label IDs (e.g. ["se-123456"])
            contact_name: Contact person name for the pickup
            contact_phone: Contact phone number
            pickup_date: Pickup date in YYYY-MM-DD format
            start_time: Pickup window start time in HH:MM format (default "08:00")
            end_time: Pickup window end time in HH:MM format (default "17:00")
            contact_email: Optional contact email
            notes: Optional pickup instructions

        Returns:
            Dict with pickup confirmation details:
            {
                "pickup_id": str,
                "status": str,
                "pickup_window": {"start_at": str, "end_at": str},
                "confirmation_number": str,
            }
        """
        logger.info(f"Scheduling pickup for {len(label_ids)} label(s) on {pickup_date}")

        # Build ISO datetime strings from date and time components
        start_at = f"{pickup_date}T{start_time}:00Z"
        end_at = f"{pickup_date}T{end_time}:00Z"

        payload = {
            "label_ids": label_ids,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "pickup_window": {
                "start_at": start_at,
                "end_at": end_at,
            },
        }

        if contact_email:
            payload["contact_email"] = contact_email
        if notes:
            payload["pickup_notes"] = notes

        try:
            response = requests.post(
                f"{self.BASE_URL}/pickups",
                json=payload,
                headers=self.headers,
                timeout=30
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"ShipEngine API returned status {response.status_code}: {response.text}")

            data = response.json()

            result = {
                "pickup_id": data.get("pickup_id", ""),
                "status": data.get("status", "unknown"),
                "pickup_window": data.get("pickup_window", {"start_at": start_at, "end_at": end_at}),
                "confirmation_number": data.get("confirmation_number", ""),
            }

            logger.info(f"Pickup scheduled: {result['pickup_id']}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"ShipEngine pickup scheduling error: {str(e)}")
            raise Exception(f"ShipEngine pickup scheduling error: {str(e)}")
        except Exception as e:
            logger.error(f"ShipEngine error: {str(e)}")
            raise Exception(f"ShipEngine error: {str(e)}")

    def void_label(self, label_id: str) -> dict:
        """
        Void a shipping label

        Args:
            label_id: Label ID to void (e.g., 'se-86616736')

        Returns:
            Dict with 'approved' boolean and 'message' string
        """
        logger.info(f"Voiding label: {label_id}")

        try:
            # ShipEngine API: PUT /v1/labels/{label_id}/void
            response = requests.put(
                f"{self.BASE_URL}/labels/{label_id}/void",
                json={},
                headers=self.headers,
                timeout=30
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"ShipEngine API returned status {response.status_code}: {response.text}")

            data = response.json()

            # ShipEngine returns: {"approved": true, "message": "Request for refund submitted..."}
            approved = data.get("approved", False)
            message = data.get("message", "Label void request processed")

            logger.info(f"Label void result: approved={approved}, message={message}")

            return {
                "approved": approved,
                "message": message
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"ShipEngine label void error: {str(e)}")
            raise Exception(f"ShipEngine label void error: {str(e)}")
        except Exception as e:
            logger.error(f"ShipEngine error: {str(e)}")
            raise Exception(f"ShipEngine error: {str(e)}")
