"""ShipEngine API client wrapper using REST API"""

import os
import requests
from typing import List, Optional
import logging
from .models import Address, Parcel, Rate, ShippingLabel, ValidationResult

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

    def get_rates(self, from_address: Address, to_address: Address, parcel: Parcel) -> List[Rate]:
        """
        Get shipping rates from all carriers

        Args:
            from_address: Sender address
            to_address: Recipient address
            parcel: Package dimensions and weight

        Returns:
            List of available rates
        """
        logger.info("Getting rates from ShipEngine")

        # Get carrier IDs (required by ShipEngine API)
        carrier_ids = self._get_carrier_ids()
        if not carrier_ids:
            logger.warning("No carriers found or configured")
            return []

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
                    rate = Rate(
                        object_id=rate_data.get("rate_id", ""),
                        provider=rate_data.get("carrier_friendly_name", "Unknown"),
                        servicelevel_name=rate_data.get("service_type", ""),
                        servicelevel_token=rate_data.get("service_code", ""),
                        amount=float(rate_data.get("shipping_amount", {}).get("amount", 0)),
                        currency=rate_data.get("shipping_amount", {}).get("currency", "USD"),
                        estimated_days=rate_data.get("estimated_delivery_days", None),
                        duration_terms=None,
                        shipment_id=None,
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

    def purchase_label(self, rate_id: str, label_format: str = "pdf") -> ShippingLabel:
        """
        Purchase shipping label using a rate ID

        Args:
            rate_id: Rate ID from get_rates()
            label_format: Label format (pdf, png, zpl) - default: pdf

        Returns:
            ShippingLabel with tracking number and label URL
        """
        logger.info(f"Purchasing label with rate ID: {rate_id}")

        # Prepare label purchase request
        # ShipEngine API: POST /v1/labels/rates/{rate_id}
        payload = {
            "label_format": label_format.lower(),
            "label_layout": "4x6",  # Standard shipping label size
        }

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
