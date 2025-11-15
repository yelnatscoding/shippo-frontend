"""Data models for Shippo Tool"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class Address(BaseModel):
    """Shipping address model"""
    name: str
    street1: str
    street2: Optional[str] = None
    city: str
    state: str
    zip: str
    country: str = "US"
    phone: Optional[str] = None
    email: Optional[str] = None
    is_residential: bool = True

class Parcel(BaseModel):
    """Package dimensions and weight"""
    length: float
    width: float
    height: float
    distance_unit: str = "in"  # "in" or "cm"
    weight: float
    mass_unit: str = "lb"  # "lb" or "kg"

class Rate(BaseModel):
    """Shipping rate from carrier"""
    object_id: str
    provider: str  # USPS, UPS, FedEx
    servicelevel_name: str
    servicelevel_token: str
    amount: float
    currency: str = "USD"
    estimated_days: Optional[int] = None
    duration_terms: Optional[str] = None
    shipment_id: Optional[str] = None  # Needed for EasyPost to purchase labels

    def __str__(self) -> str:
        days_str = f"{self.estimated_days} days" if self.estimated_days else self.duration_terms or "N/A"
        return f"{self.provider} {self.servicelevel_name}: ${self.amount} ({days_str})"

class ShippingLabel(BaseModel):
    """Generated shipping label"""
    tracking_number: str
    label_url: str
    carrier: str
    service: str
    cost: float
    created_at: datetime = Field(default_factory=datetime.now)
    local_path: Optional[str] = None

class ValidationResult(BaseModel):
    """Address validation result"""
    is_valid: bool
    messages: List[str] = Field(default_factory=list)
    original_address: Address
    validated_address: Optional[Address] = None
