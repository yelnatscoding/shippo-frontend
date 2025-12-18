"""Shippo API client wrapper"""

from shippo import Shippo
from shippo.models import components
from typing import Dict, List, Optional
import logging
import os
from .models import Address, Parcel, Rate, ShippingLabel, ValidationResult

logger = logging.getLogger(__name__)

class ShippoClient:
    """Wrapper around Shippo API"""

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

        # Initialize Shippo client with API key
        self.client = Shippo(api_key_header=self.api_key)

        mode = "TEST" if self.test_mode else "LIVE"
        logger.info(f"Initialized Shippo client in {mode} mode")

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

        # Create address objects
        address_from = components.AddressCreateRequest(**self._address_to_dict(from_address))
        address_to = components.AddressCreateRequest(**self._address_to_dict(to_address))
        parcel_obj = components.ParcelCreateRequest(**self._parcel_to_dict(parcel))

        # Create shipment request
        shipment_request = components.ShipmentCreateRequest(
            address_from=address_from,
            address_to=address_to,
            parcels=[parcel_obj],
            async_=False,  # Wait for rates
        )

        if carrier_accounts:
            shipment_request.carrier_accounts = carrier_accounts

        shipment = self.client.shipments.create(shipment_request)

        # Convert to Rate models
        rates = []
        for rate_data in shipment.rates:
            rate = Rate(
                object_id=rate_data.object_id,
                provider=rate_data.provider,
                servicelevel_name=rate_data.servicelevel.name,
                servicelevel_token=rate_data.servicelevel.token,
                amount=float(rate_data.amount),
                currency=rate_data.currency,
                estimated_days=rate_data.estimated_days,
                duration_terms=rate_data.duration_terms,
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

        transaction_request = components.TransactionCreateRequest(
            rate=rate_id,
            label_file_type=label_format,
            async_=False  # Wait for label generation
        )

        transaction = self.client.transactions.create(transaction_request)

        if transaction.status != "SUCCESS":
            error_msg = transaction.messages[0] if transaction.messages else "Unknown error"
            raise Exception(f"Label purchase failed: {error_msg}")

        # Handle rate being either a CoreRate object or a string ID
        if isinstance(transaction.rate, str):
            # If rate is just an ID, we don't have full details
            # We'll need to make reasonable defaults
            carrier = "Unknown"
            service = "Unknown"
            cost = 0.0
        else:
            # transaction.rate is a CoreRate object
            carrier = transaction.rate.provider
            service = transaction.rate.servicelevel_name
            cost = float(transaction.rate.amount)

        label = ShippingLabel(
            tracking_number=transaction.tracking_number,
            label_url=transaction.label_url,
            carrier=carrier,
            service=service,
            cost=cost,
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
        address_data["validate"] = True

        address_request = components.AddressCreateRequest(**address_data)
        validated = self.client.addresses.create(address_request)

        is_valid = validated.validation_results.is_valid
        messages = validated.validation_results.messages if hasattr(validated.validation_results, 'messages') else []

        result = ValidationResult(
            is_valid=is_valid,
            messages=[msg.text if hasattr(msg, 'text') else str(msg) for msg in messages],
            original_address=address,
        )

        if is_valid:
            # Create validated address from response
            result.validated_address = Address(
                name=address.name,
                street1=validated.street1,
                street2=validated.street2,
                city=validated.city,
                state=validated.state,
                zip=validated.zip,
                country=validated.country,
                phone=address.phone,
                email=address.email,
                is_residential=address.is_residential,
            )
            logger.info("Address validated successfully")
        else:
            logger.warning(f"Address validation failed: {result.messages}")

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

        tracking = self.client.tracking_status.get_status(carrier, tracking_number)

        return {
            "carrier": tracking.carrier,
            "tracking_number": tracking.tracking_number,
            "status": tracking.tracking_status.status,
            "status_date": tracking.tracking_status.status_date,
            "status_details": tracking.tracking_status.status_details,
            "location": tracking.tracking_status.location,
            "eta": tracking.eta,
        }
