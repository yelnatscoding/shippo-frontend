"""EasyPost API client wrapper"""

import easypost
from typing import Dict, List, Optional
import logging
from .models import Address, Parcel, Rate, ShippingLabel, ValidationResult
from .config import config

logger = logging.getLogger(__name__)

class EasyPostClient:
    """Wrapper around EasyPost API"""

    def __init__(self, api_key: Optional[str] = None, test_mode: Optional[bool] = None):
        """
        Initialize EasyPost client

        Args:
            api_key: EasyPost API key (defaults to config)
            test_mode: Use test mode (defaults to config)
        """
        self.api_key = api_key or config.api_key
        self.test_mode = test_mode if test_mode is not None else config.test_mode

        if not self.api_key:
            raise ValueError("EasyPost API key not configured. Set EASYPOST_API_KEY in .env file")

        # Initialize EasyPost client with API key
        self.client = easypost.EasyPostClient(self.api_key)

        mode = "TEST" if self.test_mode else "LIVE"
        logger.info(f"Initialized EasyPost client in {mode} mode")

    def _address_to_dict(self, address: Address) -> dict:
        """Convert Address model to dict for EasyPost API"""
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
        }

    def _parcel_to_dict(self, parcel: Parcel) -> dict:
        """Convert Parcel model to dict for EasyPost API"""
        return {
            "length": parcel.length,
            "width": parcel.width,
            "height": parcel.height,
            "weight": parcel.weight,
        }

    def get_rates(self, from_address: Address, to_address: Address,
                  parcel: Parcel, carrier_accounts: Optional[List[str]] = None) -> List[Rate]:
        """
        Get shipping rates from all carriers

        Args:
            from_address: Sender address
            to_address: Recipient address
            parcel: Package dimensions and weight
            carrier_accounts: Optional list of specific carrier account IDs

        Returns:
            List of available rates
        """
        logger.info("Creating shipment to get rates")

        # Create shipment (EasyPost automatically fetches rates)
        shipment_data = {
            "from_address": self._address_to_dict(from_address),
            "to_address": self._address_to_dict(to_address),
            "parcel": self._parcel_to_dict(parcel),
        }

        if carrier_accounts:
            shipment_data["carrier_accounts"] = carrier_accounts

        shipment = self.client.shipment.create(**shipment_data)

        # Convert to Rate models
        rates = []
        for rate_data in shipment.rates:
            rate = Rate(
                object_id=rate_data.id,
                provider=rate_data.carrier,
                servicelevel_name=rate_data.service,
                servicelevel_token=rate_data.service,
                amount=float(rate_data.rate),
                currency=rate_data.currency,
                estimated_days=rate_data.delivery_days,
                duration_terms=None,
                shipment_id=shipment.id,  # Store for later label purchase
            )
            rates.append(rate)

        logger.info(f"Retrieved {len(rates)} rates")
        return rates

    def purchase_label(self, rate_id: str, label_format: str = "PDF") -> ShippingLabel:
        """
        Purchase shipping label

        Args:
            rate_id: Rate object ID from get_rates()
            label_format: PDF, PNG, or ZPL

        Returns:
            ShippingLabel with tracking number and label URL
        """
        logger.info(f"Purchasing label with rate ID: {rate_id}")

        # Retrieve the rate to get its shipment_id
        rate = self.client.rate.retrieve(rate_id)
        shipment_id = rate.shipment_id

        # Buy the shipment with the selected rate
        bought_shipment = self.client.shipment.buy(
            id=shipment_id,
            rate=rate,
            label_format=label_format
        )

        if not bought_shipment.postage_label:
            raise Exception("Label purchase failed: No postage label returned")

        # Extract label information
        label = ShippingLabel(
            tracking_number=bought_shipment.tracking_code,
            label_url=bought_shipment.postage_label.label_url,
            carrier=bought_shipment.selected_rate.carrier if bought_shipment.selected_rate else "Unknown",
            service=bought_shipment.selected_rate.service if bought_shipment.selected_rate else "Unknown",
            cost=float(bought_shipment.selected_rate.rate) if bought_shipment.selected_rate else 0.0,
        )

        logger.info(f"Label created successfully. Tracking: {label.tracking_number}")
        return label

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
        address_data["verify"] = True

        try:
            validated = self.client.address.create_and_verify(**address_data)

            # Check if verification was successful
            is_valid = False
            messages = []

            if hasattr(validated, 'verifications'):
                delivery_verification = getattr(validated.verifications, 'delivery', None)
                if delivery_verification:
                    is_valid = getattr(delivery_verification, 'success', False)
                    errors = getattr(delivery_verification, 'errors', [])
                    messages = [err.get('message', str(err)) if isinstance(err, dict) else str(err) for err in errors]

            result = ValidationResult(
                is_valid=is_valid,
                messages=messages,
                original_address=address,
            )

            if is_valid or validated:
                # Create validated address from response
                result.validated_address = Address(
                    name=address.name,
                    street1=validated.street1,
                    street2=validated.street2 or "",
                    city=validated.city,
                    state=validated.state,
                    zip=validated.zip,
                    country=validated.country,
                    phone=address.phone,
                    email=address.email,
                    is_residential=getattr(validated, 'residential', True),
                )
                logger.info("Address validated successfully")
            else:
                logger.warning(f"Address validation failed: {result.messages}")

        except Exception as e:
            logger.error(f"Address validation error: {str(e)}")
            result = ValidationResult(
                is_valid=False,
                messages=[str(e)],
                original_address=address,
            )

        return result

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

        # Create or retrieve tracker
        tracker = self.client.tracker.create(
            tracking_code=tracking_number,
            carrier=carrier.lower()
        )

        # Get latest tracking detail
        latest_detail = None
        if tracker.tracking_details and len(tracker.tracking_details) > 0:
            latest_detail = tracker.tracking_details[0]

        return {
            "carrier": tracker.carrier or carrier.upper(),
            "tracking_number": tracker.tracking_code,
            "status": tracker.status or "unknown",
            "status_date": latest_detail.datetime if latest_detail else None,
            "status_details": latest_detail.message if latest_detail else "",
            "location": f"{latest_detail.tracking_location.city}, {latest_detail.tracking_location.state}" if latest_detail and latest_detail.tracking_location else "",
            "eta": tracker.est_delivery_date,
        }
