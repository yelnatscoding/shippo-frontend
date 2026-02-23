# Gori/ShipBae API Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Gori Company (ShipBae) as a fifth shipping provider for rates, label purchase, and address validation.

**Architecture:** Direct REST client following the same pattern as existing providers (EasyshipClient, ShipEngineClient). OAuth 2.0 token cached in-memory with TTL. Wired into the parallel rate fetcher, label purchaser, and address validator via env-var gating.

**Tech Stack:** Python 3.12, requests, Pydantic v2, Vercel serverless functions

**Design Doc:** `docs/plans/2026-02-23-gori-shipbae-integration-design.md`

---

### Task 1: Create Gori client — token management

**Files:**
- Create: `shippo-frontend/lib/gori_client.py`

**Step 1: Create the client file with token management**

```python
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
```

**Step 2: Commit**

```bash
git add shippo-frontend/lib/gori_client.py
git commit -m "feat(gori): add GoriClient with OAuth token management"
```

---

### Task 2: Add get_rates method to GoriClient

**Files:**
- Modify: `shippo-frontend/lib/gori_client.py`

**Step 1: Add get_rates method after `_address_to_dict`**

```python
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
```

**Step 2: Commit**

```bash
git add shippo-frontend/lib/gori_client.py
git commit -m "feat(gori): add get_rates method"
```

---

### Task 3: Add purchase_label method to GoriClient

**Files:**
- Modify: `shippo-frontend/lib/gori_client.py`

**Step 1: Add purchase_label method after `get_rates`**

```python
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
```

**Step 2: Commit**

```bash
git add shippo-frontend/lib/gori_client.py
git commit -m "feat(gori): add purchase_label method"
```

---

### Task 4: Add validate_address method to GoriClient

**Files:**
- Modify: `shippo-frontend/lib/gori_client.py`

**Step 1: Add validate_address method after `purchase_label`**

```python
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
```

**Step 2: Commit**

```bash
git add shippo-frontend/lib/gori_client.py
git commit -m "feat(gori): add validate_address method"
```

---

### Task 5: Wire Gori into rates endpoint

**Files:**
- Modify: `shippo-frontend/api/rates.py:29-32` (add import)
- Modify: `shippo-frontend/api/rates.py:82-90` (add futures after easyship block)
- Modify: `shippo-frontend/api/rates.py:187-198` (add `_get_gori_rates` method after `_get_easyship_rates`)

**Step 1: Add import at line 32 (after easyship_client import)**

Add after `from easyship_client import EasyshipClient`:
```python
            from gori_client import GoriClient
```

**Step 2: Add futures block after the Easyship futures (after line 90)**

```python
                if os.environ.get('GORI_CLIENT_ID'):
                    futures[executor.submit(
                        self._get_gori_rates,
                        from_address, to_address, parcel, None
                    )] = ('gori', 'base')
                    futures[executor.submit(
                        self._get_gori_rates,
                        from_address, to_address, parcel, 'STANDARD'
                    )] = ('gori', 'signature')
```

**Step 3: Add `_get_gori_rates` method (after `_get_easyship_rates` at line 198)**

```python
    def _get_gori_rates(self, from_address, to_address, parcel, signature_confirmation):
        """Get rates from Gori (ShipBae)"""
        lib_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from gori_client import GoriClient
        client = GoriClient(
            client_id=os.environ['GORI_CLIENT_ID'],
            client_secret=os.environ['GORI_CLIENT_SECRET'],
            test_mode=os.environ.get('GORI_TEST_MODE', 'false').lower() == 'true'
        )
        rates = client.get_rates(from_address, to_address, parcel,
                                  signature_confirmation=signature_confirmation)
        return [self._serialize_rate(r) for r in rates]
```

**Step 4: Commit**

```bash
git add shippo-frontend/api/rates.py
git commit -m "feat(gori): wire Gori into parallel rate fetching"
```

---

### Task 6: Wire Gori into purchase endpoint

**Files:**
- Modify: `shippo-frontend/api/purchase.py:15` (add import)
- Modify: `shippo-frontend/api/purchase.py:58-61` (add elif branch)
- Modify: `shippo-frontend/api/purchase.py:165-174` (add `_purchase_gori_label` method)

**Step 1: Add import at line 15 (after easyship_client import)**

```python
from gori_client import GoriClient
```

**Step 2: Add elif branch at line 58-59 (before the `else: raise ValueError`)**

```python
            elif provider == 'gori':
                label = self._purchase_gori_label(rate_id, label_format, signature_confirmation)
```

**Step 3: Add method at end of class (after `_purchase_easyship_label`)**

```python
    def _purchase_gori_label(self, rate_id, label_format, signature_confirmation=None):
        """Purchase label from Gori (ShipBae)"""
        client = GoriClient(
            client_id=os.environ['GORI_CLIENT_ID'],
            client_secret=os.environ['GORI_CLIENT_SECRET'],
            test_mode=os.environ.get('GORI_TEST_MODE', 'false').lower() == 'true'
        )
        return client.purchase_label(rate_id, label_format, signature_confirmation)
```

**Step 4: Commit**

```bash
git add shippo-frontend/api/purchase.py
git commit -m "feat(gori): wire Gori into label purchase"
```

---

### Task 7: Wire Gori into validate endpoint

**Files:**
- Modify: `shippo-frontend/api/validate.py:11-12` (add import)
- Modify: `shippo-frontend/api/validate.py:34-40` (add gori to auto-detect chain)
- Modify: `shippo-frontend/api/validate.py:43-48` (add elif branch)
- Add `_validate_with_gori` method after `_validate_with_easypost`

**Step 1: Add import at line 12 (after easypost_client import)**

```python
from gori_client import GoriClient
```

**Step 2: Add gori to the auto-detect chain (line 38-40, before the else raise)**

```python
                elif os.environ.get('GORI_CLIENT_ID'):
                    provider = 'gori'
```

**Step 3: Add elif branch at line 46-47 (before the else raise)**

```python
            elif provider == 'gori':
                result = self._validate_with_gori(address)
```

**Step 4: Add method after `_validate_with_easypost` (after line 113)**

```python
    def _validate_with_gori(self, address):
        """Validate with Gori (ShipBae)"""
        client = GoriClient(
            client_id=os.environ['GORI_CLIENT_ID'],
            client_secret=os.environ['GORI_CLIENT_SECRET'],
            test_mode=os.environ.get('GORI_TEST_MODE', 'false').lower() == 'true'
        )

        validation_result = client.validate_address(address)

        return {
            'is_valid': validation_result.is_valid,
            'messages': validation_result.messages,
            'original': self._serialize_address(validation_result.original_address),
            'suggested': self._serialize_address(validation_result.validated_address) if validation_result.validated_address else None
        }
```

**Step 5: Commit**

```bash
git add shippo-frontend/api/validate.py
git commit -m "feat(gori): wire Gori into address validation"
```

---

### Task 8: Update environment config

**Files:**
- Modify: `shippo-frontend/.env.example`

**Step 1: Add Gori env vars to .env.example (after EASYSHIP_API_KEY line)**

```
GORI_CLIENT_ID=your_gori_client_id_here
GORI_CLIENT_SECRET=your_gori_client_secret_here
GORI_TEST_MODE=false
```

**Step 2: Commit**

```bash
git add shippo-frontend/.env.example
git commit -m "feat(gori): add Gori env vars to .env.example"
```

---

### Task 9: Smoke test

**Step 1: Start the dev server**

```bash
cd shippo-frontend && vercel dev --listen 3000
```

**Step 2: Test rates endpoint with curl**

```bash
curl -X POST http://localhost:3000/api/rates \
  -H "Content-Type: application/json" \
  -d '{
    "from_address": {"name":"Test","street1":"1600 Amphitheatre Pkwy","city":"Mountain View","state":"CA","zip":"94043","country":"US"},
    "to_address": {"name":"Test","street1":"1 Infinite Loop","city":"Cupertino","state":"CA","zip":"95014","country":"US"},
    "parcel": {"length":10,"width":8,"height":6,"weight":2,"distance_unit":"in","mass_unit":"lb"}
  }'
```

Expected: Response includes `"gori": {"base": [...], "signature": [...]}` alongside existing providers.

**Step 3: Test address validation**

```bash
curl -X POST http://localhost:3000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "address": {"name":"Test","street1":"1600 Amphitheatre Pkwy","city":"Mountain View","state":"CA","zip":"94043","country":"US"},
    "provider": "gori"
  }'
```

Expected: `{"success": true, "data": {"is_valid": true, ...}}`

**Step 4: If tests pass, final commit**

```bash
git add -A
git commit -m "feat: complete Gori/ShipBae provider integration"
```
