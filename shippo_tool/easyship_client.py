"""Easyship API client wrapper using REST API"""

import os
import requests
from typing import List, Optional
import logging
from .models import Address, Parcel, Rate

logger = logging.getLogger(__name__)

class EasyshipClient:
    """Wrapper around Easyship REST API"""

    BASE_URL = "https://public-api.easyship.com/2024-09"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Easyship client

        Args:
            api_key: Easyship API key (defaults to EASYSHIP_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("EASYSHIP_API_KEY", "")

        if not self.api_key:
            raise ValueError("Easyship API key not configured. Set EASYSHIP_API_KEY in .env file")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        logger.info("Initialized Easyship client")

    def _address_to_dict(self, address: Address) -> dict:
        """Convert Address model to dict for Easyship API"""
        # Easyship has a 22 character limit on contact_name
        contact_name = address.name[:22] if len(address.name) > 22 else address.name

        addr_dict = {
            "line_1": address.street1,
            "city": address.city,
            "state": address.state,
            "postal_code": address.zip,
            "country_alpha2": address.country,
            "contact_name": contact_name,
        }

        # Only add optional fields if they have valid values
        if address.street2:
            addr_dict["line_2"] = address.street2
        if address.phone:
            addr_dict["contact_phone"] = address.phone
        if address.email:
            addr_dict["contact_email"] = address.email

        return addr_dict

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
        logger.info("Getting rates from Easyship")

        # Prepare shipment data for Easyship
        payload = {
            "origin_address": self._address_to_dict(from_address),
            "destination_address": self._address_to_dict(to_address),
            "parcels": [
                {
                    "box": {
                        "length": parcel.length,
                        "width": parcel.width,
                        "height": parcel.height
                    },
                    "items": [
                        {
                            "actual_weight": parcel.weight,
                            "category": "general",
                            "declared_currency": "USD",
                            "declared_customs_value": 50.0,
                            "description": "Package",
                            "quantity": 1,
                            "hs_code": "9999.99.99"  # Generic HS code for unspecified goods
                        }
                    ]
                }
            ],
            "incoterms": "DDU",
            "insurance": {
                "is_insured": False
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
                raise Exception(f"Easyship API returned status {response.status_code}: {response.text}")

            data = response.json()

            # Convert to Rate models
            rates = []
            if "rates" in data:
                for rate_data in data["rates"]:
                    # Extract courier information
                    service_name = rate_data.get("full_description", rate_data.get("courier_display_name", ""))
                    courier_name = rate_data.get("courier_name", "")

                    # If courier_name is empty, extract from service description
                    if not courier_name and service_name:
                        # Try "USPS - " pattern first
                        if " - " in service_name:
                            courier_name = service_name.split(" - ")[0].strip()
                        # Try "FedEx" pattern
                        elif service_name.startswith("FedEx"):
                            courier_name = "FedEx"
                        else:
                            courier_name = "Unknown"
                    elif not courier_name:
                        courier_name = "Unknown"

                    total_charge = rate_data.get("total_charge", 0)

                    rate = Rate(
                        object_id=rate_data.get("courier_id", ""),
                        provider=courier_name,
                        servicelevel_name=service_name,
                        servicelevel_token=rate_data.get("courier_id", ""),
                        amount=float(total_charge),
                        currency="USD",
                        estimated_days=rate_data.get("min_delivery_time", None),
                        duration_terms=f"{rate_data.get('min_delivery_time', '?')}-{rate_data.get('max_delivery_time', '?')} days" if rate_data.get('min_delivery_time') else None,
                        shipment_id=None,
                    )
                    rates.append(rate)

            logger.info(f"Retrieved {len(rates)} rates from Easyship")
            return rates

        except requests.exceptions.RequestException as e:
            logger.error(f"Easyship API request error: {str(e)}")
            raise Exception(f"Easyship API error: {str(e)}")
        except Exception as e:
            logger.error(f"Easyship error: {str(e)}")
            raise Exception(f"Easyship error: {str(e)}")
