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

    SERVICE_NAMES = {
        "usps_media": "USPS Media Mail",
        "usps_ground_advantage": "USPS Ground Advantage",
        "usps_priority": "USPS Priority",
        "usps_priority_express": "USPS Priority Express",
        "usps_first_class": "USPS First Class",
        "usps_parcel_select": "USPS Parcel Select",
        "fedex_ground": "FedEx Ground",
        "fedex_home_delivery": "FedEx Home Delivery",
        "fedex_2day": "FedEx 2Day",
        "fedex_express_saver": "FedEx Express Saver",
        "fedex_standard_overnight": "FedEx Standard Overnight",
        "fedex_priority_overnight": "FedEx Priority Overnight",
        "fedex_first_overnight": "FedEx First Overnight",
        "ups_ground": "UPS Ground",
        "ups_3_day_select": "UPS 3 Day Select",
        "ups_2nd_day_air": "UPS 2nd Day Air",
        "ups_next_day_air_saver": "UPS Next Day Air Saver",
        "ups_next_day_air": "UPS Next Day Air",
    }

    PACKAGE_NAMES = {
        "custom_package": "",
        "usps_flat_rate_envelope": "Flat Rate Envelope",
        "usps_legal_flat_rate_envelope": "Legal Flat Rate Envelope",
        "usps_padded_flat_rate_envelope": "Padded Flat Rate Envelope",
        "usps_sm_flat_rate_box": "Small Flat Rate Box",
        "usps_md_flat_rate_box": "Medium Flat Rate Box",
        "usps_lg_flat_rate_box": "Large Flat Rate Box",
    }

    # Estimated transit days (min, max) by service — matches other providers
    TRANSIT_DAYS = {
        "usps_media": (2, 8),
        "usps_ground_advantage": (2, 5),
        "usps_priority": (2, 3),
        "usps_priority_express": (1, 2),
        "usps_first_class": (2, 5),
        "usps_parcel_select": (2, 8),
        "fedex_ground": (1, 7),
        "fedex_home_delivery": (1, 7),
        "fedex_2day": (2, 2),
        "fedex_express_saver": (3, 3),
        "fedex_standard_overnight": (1, 1),
        "fedex_priority_overnight": (1, 1),
        "fedex_first_overnight": (1, 1),
        "ups_ground": (1, 5),
        "ups_3_day_select": (3, 3),
        "ups_2nd_day_air": (2, 2),
        "ups_next_day_air_saver": (1, 1),
        "ups_next_day_air": (1, 1),
    }

    def _format_service_name(self, service: str, package_type: str) -> str:
        name = self.SERVICE_NAMES.get(service, service.replace("_", " ").title())
        pkg = self.PACKAGE_NAMES.get(package_type, package_type.replace("_", " ").title() if package_type != "custom_package" else "")
        if pkg:
            return f"{name} - {pkg}"
        return name

    def _get_transit_info(self, service: str):
        """Return (estimated_days, duration_terms) for a service."""
        days = self.TRANSIT_DAYS.get(service)
        if days:
            min_d, max_d = days
            estimated = min_d
            if min_d == max_d:
                terms = f"{min_d} day{'s' if min_d > 1 else ''}"
            else:
                terms = f"{min_d}-{max_d} days"
            return estimated, terms
        return None, None

    def get_rates(self, from_address: Address, to_address: Address, parcel: Parcel,
                  signature_confirmation: Optional[str] = None) -> List[Rate]:
        sig_info = f" with signature={signature_confirmation}" if signature_confirmation else ""
        logger.info(f"Getting rates from Gori{sig_info}")

        payload = {
            "shipment": {
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

            # Response may be a list of rates directly or a dict with "rates" key
            rate_list = data if isinstance(data, list) else data.get("rates", [])
            shipment_id = data.get("shipment_id") if isinstance(data, dict) else None

            seen = set()
            for rate_data in rate_list:
                # Skip rates with errors (e.g. oversized for service)
                if "error" in rate_data:
                    continue

                fees = rate_data.get("fees", {})
                amount = float(fees.get("amount", 0)) if isinstance(fees, dict) else 0
                carrier = rate_data.get("carrier", "Gori")
                service = rate_data.get("service", "")
                package_type = rate_data.get("package_type", "")

                # Deduplicate identical rates
                dedup_key = (carrier, service, package_type, amount)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                rate_id = f"gori_{carrier}_{service}_{package_type}"
                service_name = self._format_service_name(service, package_type)
                carrier_display = carrier.upper()
                estimated_days, duration_terms = self._get_transit_info(service)

                rate = Rate(
                    object_id=rate_id,
                    provider=carrier_display,
                    servicelevel_name=service_name,
                    servicelevel_token=rate_id,
                    amount=amount,
                    currency="USD",
                    estimated_days=estimated_days,
                    duration_terms=duration_terms,
                    shipment_id=shipment_id,
                    signature_confirmation=signature_confirmation,
                    package_type=package_type,
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
