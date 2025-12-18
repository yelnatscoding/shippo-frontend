"""Utility functions"""

import os
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/shippo_tool.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def download_label(label_url: str, tracking_number: str, output_dir: str = "labels") -> str:
    """
    Download shipping label PDF from Shippo URL

    Args:
        label_url: Temporary URL to label PDF
        tracking_number: Tracking number for filename
        output_dir: Directory to save label

    Returns:
        Local path to saved label
    """
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{tracking_number}_{timestamp}.pdf"
    filepath = os.path.join(output_dir, filename)

    # Download label
    logger.info(f"Downloading label from {label_url}")
    response = requests.get(label_url, timeout=30)
    response.raise_for_status()

    # Save to file
    with open(filepath, 'wb') as f:
        f.write(response.content)

    logger.info(f"Label saved to {filepath}")
    return filepath

def format_address_for_display(address: dict) -> str:
    """Format address for pretty printing"""
    lines = [
        address.get('name', ''),
        address.get('street1', ''),
    ]
    if address.get('street2'):
        lines.append(address['street2'])

    city_line = f"{address.get('city', '')}, {address.get('state', '')} {address.get('zip', '')}"
    lines.append(city_line)
    lines.append(address.get('country', 'US'))

    return '\n'.join(filter(None, lines))

def calculate_dimensional_weight(length: float, width: float, height: float,
                                 unit: str = "in") -> float:
    """
    Calculate dimensional weight (used by carriers for pricing)

    Args:
        length, width, height: Package dimensions
        unit: "in" (inches) or "cm" (centimeters)

    Returns:
        Dimensional weight in pounds
    """
    if unit == "cm":
        # Convert to inches
        length = length / 2.54
        width = width / 2.54
        height = height / 2.54

    # Standard divisor for domestic US shipments
    dim_weight = (length * width * height) / 166
    return round(dim_weight, 2)

def validate_zip_code(zip_code: str) -> bool:
    """Validate US ZIP code format"""
    import re
    # 5 digits or 5+4 format
    pattern = r'^\d{5}(-\d{4})?$'
    return bool(re.match(pattern, zip_code))
