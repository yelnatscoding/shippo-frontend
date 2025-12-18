"""Shippo API client wrapper using REST API"""

import requests
from typing import Dict, List, Optional
import logging
import os
from models import Address, Parcel, Rate, ShippingLabel, ValidationResult

logger = logging.getLogger(__name__)

class ShippoClient:
    """Wrapper around Shippo REST API"""

    BASE_URL = "https://api.goshippo.com"

    def __init__(self, api_key: Optional[str] = None, test_mode: Optional[bool] = None):
        """
        Initialize Shippo client

        Args:
            api_key: Shippo API key (defaults to SHIPPO_API_KEY env var)
            test_mode: Use test mode (defaults to SHIPPO_TEST_MODE env var)
        """
        self.api_key = api_key or os.getenv("SHIPPO_API_KEY", "")
        self.test_mode = test_mode if test_mode is not None else os.getenv("SHIPPO_TEST_MODE", "true").lower() == "true"

        if not self.api_key:
            raise ValueError("Shippo API key not configured. Set SHIPPO_API_KEY in .env file")

        # Setup headers for API requests
        self.headers = {
            "Authorization": f"ShippoToken {self.api_key}",
            "Content-Type": "application/json"
        }

        mode = "TEST" if self.test_mode else "LIVE"
        logger.info(f"Initialized Shippo REST client in {mode} mode")

    def _address_to_dict(self, address: Address) -> dict:
        """Convert Address model to dict for Shippo API"""
        return {
            "name": address.name,
            "street1": address.street1,
            "street2": address.street2,
            "city": address.city,
            "state": address.state,
            "zip": address.zip,
            "country": address.country,
            "phone": address.phone,
            "email": address.email,
            "is_residential": address.is_residential,
        }

    def _parcel_to_dict(self, parcel: Parcel) -> dict:
        """Convert Parcel model to dict for Shippo API"""
        return {
            "length": str(parcel.length),
            "width": str(parcel.width),
            "height": str(parcel.height),
            "distance_unit": parcel.distance_unit,
            "weight": str(parcel.weight),
            "mass_unit": parcel.mass_unit,
        }

    def get_rates(self, from_address: Address, to_address: Address,
                  parcel: Parcel, carrier_accounts: Optional[List[str]] = None,
                  signature_confirmation: Optional[str] = None) -> List[Rate]:
        """
        Get shipping rates from all carriers

        Args:
            from_address: Sender address
            to_address: Recipient address
            parcel: Package dimensions and weight
            carrier_accounts: Optional list of specific carrier account IDs
            signature_confirmation: Optional signature type ("STANDARD", "ADULT", "CERTIFIED", "INDIRECT")

        Returns:
            List of available rates
        """
        sig_info = f" with signature={signature_confirmation}" if signature_confirmation else ""
        logger.info(f"Creating shipment to get rates via REST API{sig_info}")

        # Create shipment request payload
        payload = {
            "address_from": self._address_to_dict(from_address),
            "address_to": self._address_to_dict(to_address),
            "parcels": [self._parcel_to_dict(parcel)],
            "async": False  # Wait for rates synchronously
        }

        if carrier_accounts:
            payload["carrier_accounts"] = carrier_accounts

        if signature_confirmation:
            # Shippo uses string values: "STANDARD", "ADULT", "CERTIFIED", "INDIRECT"
            # Some docs show boolean true, but string values give more control
            # Map our standard values to Shippo's expected values
            sig_value = signature_confirmation
            if signature_confirmation == "STANDARD":
                sig_value = "STANDARD"  # Standard signature (anyone can sign)
            elif signature_confirmation == "ADULT":
                sig_value = "ADULT"     # Adult signature required

            payload["extra"] = {
                "signature_confirmation": sig_value
            }
            logger.info(f"Added signature_confirmation: {sig_value} to payload")

        try:
            # Make POST request to create shipment
            response = requests.post(
                f"{self.BASE_URL}/shipments/",
                json=payload,
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 201:
                raise Exception(f"Shippo API returned status {response.status_code}: {response.text}")

            data = response.json()

            # Convert to Rate models
            rates = []
            for rate_data in data.get("rates", []):
                rate = Rate(
                    object_id=rate_data.get("object_id", ""),
                    provider=rate_data.get("provider", "Unknown"),
                    servicelevel_name=rate_data.get("servicelevel", {}).get("name", ""),
                    servicelevel_token=rate_data.get("servicelevel", {}).get("token", ""),
                    amount=float(rate_data.get("amount", 0)),
                    currency=rate_data.get("currency", "USD"),
                    estimated_days=rate_data.get("estimated_days"),
                    duration_terms=rate_data.get("duration_terms"),
                    signature_confirmation=signature_confirmation,
                )
                rates.append(rate)

            logger.info(f"Retrieved {len(rates)} rates from Shippo")
            return rates

        except requests.exceptions.RequestException as e:
            logger.error(f"Shippo API request error: {str(e)}")
            raise Exception(f"Shippo API error: {str(e)}")
        except Exception as e:
            logger.error(f"Shippo error: {str(e)}")
            raise Exception(f"Shippo error: {str(e)}")

    def purchase_label(self, rate_id: str, label_format: str = "PDF",
                       signature_confirmation: Optional[str] = None) -> ShippingLabel:
        """
        Purchase shipping label

        Args:
            rate_id: Rate object ID from get_rates()
            label_format: PDF, PNG, or ZPL
            signature_confirmation: Signature type for tracking (already embedded in rate)

        Returns:
            ShippingLabel with tracking number and label URL
        """
        sig_info = f" (signature: {signature_confirmation})" if signature_confirmation else ""
        logger.info(f"Purchasing label with rate ID: {rate_id}{sig_info}")

        payload = {
            "rate": rate_id,
            "label_file_type": label_format.upper(),
            "async": False
        }

        try:
            response = requests.post(
                f"{self.BASE_URL}/transactions/",
                json=payload,
                headers=self.headers,
                timeout=30
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"Shippo API returned status {response.status_code}: {response.text}")

            data = response.json()

            if data.get("status") != "SUCCESS":
                error_msg = data.get("messages", ["Unknown error"])[0]
                raise Exception(f"Label purchase failed: {error_msg}")

            label = ShippingLabel(
                tracking_number=data.get("tracking_number", ""),
                label_url=data.get("label_url", ""),
                carrier=data.get("rate", {}).get("provider", "Unknown") if isinstance(data.get("rate"), dict) else "Unknown",
                service=data.get("rate", {}).get("servicelevel", {}).get("name", "Unknown") if isinstance(data.get("rate"), dict) else "Unknown",
                cost=float(data.get("rate", {}).get("amount", 0.0)) if isinstance(data.get("rate"), dict) else 0.0,
                signature_confirmation=signature_confirmation,
            )

            logger.info(f"Label created successfully. Tracking: {label.tracking_number}")
            return label

        except requests.exceptions.RequestException as e:
            logger.error(f"Shippo API request error: {str(e)}")
            raise Exception(f"Shippo API error: {str(e)}")
        except Exception as e:
            logger.error(f"Shippo error: {str(e)}")
            raise Exception(f"Shippo error: {str(e)}")

    def validate_address(self, address: Address) -> ValidationResult:
        """
        Validate and normalize address

        Args:
            address: Address to validate

        Returns:
            ValidationResult with validation status and corrected address
        """
        logger.info(f"Validating address in {address.city}, {address.state}")

        address_data = self._address_to_dict(address)
        address_data["validate"] = True

        try:
            response = requests.post(
                f"{self.BASE_URL}/addresses/",
                json=address_data,
                headers=self.headers,
                timeout=30
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"Shippo API returned status {response.status_code}: {response.text}")

            data = response.json()

            validation_results = data.get("validation_results", {})
            is_valid = validation_results.get("is_valid", False)
            messages = validation_results.get("messages", [])

            result = ValidationResult(
                is_valid=is_valid,
                messages=[msg.get("text", str(msg)) if isinstance(msg, dict) else str(msg) for msg in messages],
                original_address=address,
            )

            if is_valid:
                # Create validated address from response
                result.validated_address = Address(
                    name=address.name,
                    street1=data.get("street1", address.street1),
                    street2=data.get("street2", address.street2),
                    city=data.get("city", address.city),
                    state=data.get("state", address.state),
                    zip=data.get("zip", address.zip),
                    country=data.get("country", address.country),
                    phone=address.phone,
                    email=address.email,
                    is_residential=address.is_residential,
                )
                logger.info("Address validated successfully")
            else:
                logger.warning(f"Address validation failed: {result.messages}")

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Shippo API request error: {str(e)}")
            raise Exception(f"Shippo API error: {str(e)}")
        except Exception as e:
            logger.error(f"Shippo error: {str(e)}")
            raise Exception(f"Shippo error: {str(e)}")

    def track_shipment(self, carrier: str, tracking_number: str) -> dict:
        """
        Track shipment status

        Args:
            carrier: Carrier code (usps, ups, fedex)
            tracking_number: Tracking number

        Returns:
            Tracking information
        """
        logger.info(f"Tracking {carrier} shipment: {tracking_number}")

        try:
            response = requests.get(
                f"{self.BASE_URL}/tracks/{carrier}/{tracking_number}",
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                raise Exception(f"Shippo API returned status {response.status_code}: {response.text}")

            data = response.json()
            tracking_status = data.get("tracking_status", {})

            return {
                "carrier": data.get("carrier", carrier),
                "tracking_number": data.get("tracking_number", tracking_number),
                "status": tracking_status.get("status", "Unknown"),
                "status_date": tracking_status.get("status_date"),
                "status_details": tracking_status.get("status_details"),
                "location": tracking_status.get("location"),
                "eta": data.get("eta"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Shippo API request error: {str(e)}")
            raise Exception(f"Shippo API error: {str(e)}")
        except Exception as e:
            logger.error(f"Shippo error: {str(e)}")
            raise Exception(f"Shippo error: {str(e)}")
