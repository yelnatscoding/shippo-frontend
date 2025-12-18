"""
Shared configuration for API endpoints
"""

# Default sender address (hardcoded for simplicity)
DEFAULT_SENDER = {
    "name": "JunQ Trading Technology Inc.",
    "street1": "2755 E Philadelphia St",
    "city": "Ontario",
    "state": "CA",
    "zip": "91761",
    "country": "US",
    "phone": "+19178650776",
    "email": "gao@junqmarket.com"
}

# Provider timeout (8 seconds to stay under Vercel's 10 second limit)
PROVIDER_TIMEOUT = 8

# Rate cache TTL (5 minutes)
RATE_CACHE_TTL = 300
