"""Gori Company (ShipBae) API client wrapper using REST API"""

import os
import time
import requests
from typing import List, Optional
import logging
from datetime import date
from models import Address, Parcel, Rate, ShippingLabel, ValidationResult

logger = logging.getLogger(__name__)

# Module-level token cache (shared across instances within same process)
_token_cache = {"token": None, "expires_at": 0}


class GoriClient:
    """Wrapper around Gori Company REST API (v2)"""

    PRODUCTION_URL = "https://api.goricompany.com/v2"
    STAGING_URL = "https://staging.api.goricompany.com/v2"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None,
                 test_mode: Optional[bool] = None):
        self.client_id = client_id or os.getenv("GORI_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("GORI_CLIENT_SECRET", "")

        if not self.client_id or not self.client_secret:
            raise ValueError("Gori API credentials not configured. Set GORI_CLIENT_ID and GORI_CLIENT_SECRET in .env file")

        if test_mode is None:
            test_mode = os.getenv("GORI_TEST_MODE", "false").lower() == "true"

        self.base_url = self.STAGING_URL if test_mode else self.PRODUCTION_URL
        logger.info(f"Initialized Gori client (base_url={self.base_url})")

    def _get_token(self) -> str:
        global _token_cache
        # Return cached token if still valid (5-min buffer before expiry)
        if _token_cache["token"] and time.time() < (_token_cache["expires_at"] - 300):
            return _token_cache["token"]

        response = requests.post(
            f"{self.base_url}/auth/token",
            json={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        _token_cache["token"] = data["access_token"]
        # Token lasts 12 hours
        _token_cache["expires_at"] = time.time() + (12 * 60 * 60)

        logger.info("Obtained new Gori API token")
        return _token_cache["token"]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json"
        }

    def _address_to_dict(self, address: Address) -> dict:
        addr = {
            "name": address.name,
            "street1": address.street1,
            "city": address.city,
            "state": address.state,
            "zip": address.zip,
            "country": address.country,
        }
        if address.street2:
            addr["street2"] = address.street2
        if address.phone:
            addr["phone"] = address.phone
        if address.email:
            addr["email"] = address.email
        return addr

    def get_rates(self, from_address: Address, to_address: Address, parcel: Parcel,
                  signature_confirmation: Optional[str] = None) -> List[Rate]:
        sig_info = f" with signature={signature_confirmation}" if signature_confirmation else ""
        logger.info(f"Getting rates from Gori{sig_info}")

        payload = {
            "from_address": self._address_to_dict(from_address),
            "to_address": self._address_to_dict(to_address),
            "parcel": {
                "length": parcel.length,
                "width": parcel.width,
                "height": parcel.height,
                "weight": parcel.weight,
                "distance_unit": parcel.distance_unit,
                "mass_unit": parcel.mass_unit,
            },
            "ship_date": date.today().isoformat(),
        }

        try:
            response = requests.post(
                f"{self.base_url}/shipments/rates",
                json=payload,
                headers=self._headers(),
                timeout=30
            )

            if response.status_code != 200:
                raise Exception(f"Gori API returned status {response.status_code}: {response.text}")

            data = response.json()
            rates = []

            for rate_data in data.get("rates", []):
                rate = Rate(
                    object_id=rate_data.get("id", ""),
                    provider=rate_data.get("carrier", "Gori"),
                    servicelevel_name=rate_data.get("service", ""),
                    servicelevel_token=rate_data.get("id", ""),
                    amount=float(rate_data.get("amount", 0)),
                    currency=rate_data.get("currency", "USD"),
                    estimated_days=rate_data.get("estimated_days"),
                    duration_terms=f"{rate_data.get('estimated_days', '?')} days" if rate_data.get("estimated_days") else None,
                    shipment_id=data.get("shipment_id"),
                    signature_confirmation=signature_confirmation,
                )
                rates.append(rate)

            logger.info(f"Retrieved {len(rates)} rates from Gori")
            return rates

        except requests.exceptions.RequestException as e:
            logger.error(f"Gori API request error: {str(e)}")
            raise Exception(f"Gori API error: {str(e)}")
        except Exception as e:
            logger.error(f"Gori error: {str(e)}")
            raise Exception(f"Gori error: {str(e)}")

    def purchase_label(self, rate_id: str, label_format: str = "PDF",
                       signature_confirmation: Optional[str] = None) -> ShippingLabel:
        logger.info(f"Purchasing Gori label for rate {rate_id}")

        payload = {
            "rate_id": rate_id,
            "label_format": label_format,
        }

        try:
            response = requests.post(
                f"{self.base_url}/shipments",
                json=payload,
                headers=self._headers(),
                timeout=30
            )

            if response.status_code not in (200, 201):
                raise Exception(f"Gori API returned status {response.status_code}: {response.text}")

            data = response.json()

            label = ShippingLabel(
                tracking_number=data.get("tracking_number", ""),
                label_url=data.get("label_url", data.get("label_download", "")),
                carrier=data.get("carrier", ""),
                service=data.get("service", ""),
                cost=float(data.get("amount", 0)),
                signature_confirmation=signature_confirmation,
                label_id=data.get("id"),
            )

            logger.info(f"Purchased Gori label: {label.tracking_number}")
            return label

        except requests.exceptions.RequestException as e:
            logger.error(f"Gori label purchase error: {str(e)}")
            raise Exception(f"Gori label purchase error: {str(e)}")
        except Exception as e:
            logger.error(f"Gori error: {str(e)}")
            raise Exception(f"Gori error: {str(e)}")

    def validate_address(self, address: Address) -> ValidationResult:
        logger.info(f"Validating address with Gori: {address.street1}, {address.city}, {address.state}")

        payload = {
            "street1": address.street1,
            "city": address.city,
            "state": address.state,
            "zip": address.zip,
            "country": address.country,
        }
        if address.street2:
            payload["street2"] = address.street2

        try:
            response = requests.post(
                f"{self.base_url}/addresses",
                json=payload,
                headers=self._headers(),
                timeout=10
            )

            if response.status_code != 200:
                raise Exception(f"Gori validation returned status {response.status_code}: {response.text}")

            data = response.json()
            is_valid = data.get("verified", False)
            validated_addr = data.get("address", {})

            validated_address = None
            if is_valid and validated_addr:
                validated_address = Address(
                    name=address.name,
                    street1=validated_addr.get("street1", address.street1),
                    street2=validated_addr.get("street2", address.street2),
                    city=validated_addr.get("city", address.city),
                    state=validated_addr.get("state", address.state),
                    zip=validated_addr.get("zip", address.zip),
                    country=validated_addr.get("country", address.country),
                    phone=address.phone,
                    email=address.email,
                )

            return ValidationResult(
                is_valid=is_valid,
                messages=data.get("corrections", []),
                original_address=address,
                validated_address=validated_address,
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Gori validation error: {str(e)}")
            raise Exception(f"Gori validation error: {str(e)}")
        except Exception as e:
            logger.error(f"Gori error: {str(e)}")
            raise Exception(f"Gori error: {str(e)}")
