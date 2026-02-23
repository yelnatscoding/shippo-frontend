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
            json={"client_id": self.client_id, "client_secret": self.client_secret},
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
