"""Configuration management for Shippo Tool"""

import os
from pathlib import Path
from typing import Optional
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

class SenderAddress(BaseModel):
    """Default sender address configuration"""
    name: str = "Your Company"
    street1: str = ""
    street2: Optional[str] = None
    city: str = ""
    state: str = ""
    zip: str = ""
    country: str = "US"
    phone: Optional[str] = None
    email: Optional[str] = None

class Preferences(BaseModel):
    """User preferences"""
    auto_select_cheapest: bool = False
    label_format: str = "PDF"  # PDF, PNG, or ZPL
    default_carrier: Optional[str] = None  # USPS, UPS, FedEx

class Config(BaseModel):
    """Main configuration"""
    api_key: str = Field(default_factory=lambda: os.getenv("EASYPOST_API_KEY", ""))
    test_mode: bool = Field(default_factory=lambda: os.getenv("EASYPOST_TEST_MODE", "true").lower() == "true")
    default_sender: SenderAddress = Field(default_factory=SenderAddress)
    preferences: Preferences = Field(default_factory=Preferences)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """Load configuration from file"""
        if config_path is None:
            config_path = Path.cwd() / "config.yaml"

        config_data = {}
        if config_path.exists():
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}

        return cls(**config_data)

    def validate_api_key(self) -> bool:
        """Check if API key is configured"""
        return bool(self.api_key and self.api_key != "")

# Global config instance
config = Config.load()
