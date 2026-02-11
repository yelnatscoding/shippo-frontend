"""Configuration loader"""

import os
import yaml
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Bot configuration from YAML file"""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

    def _get_env_value(self, env_key: str) -> str:
        """Get value from environment variable"""
        return os.getenv(env_key, "")

    @property
    def bot_token(self) -> str:
        env_key = self._config.get("discord", {}).get("bot_token_env", "DISCORD_BOT_TOKEN")
        return self._get_env_value(env_key)

    @property
    def database_url(self) -> str:
        env_key = self._config.get("database", {}).get("url_env", "POSTGRES_URL")
        return self._get_env_value(env_key)

    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def calendar(self) -> Dict[str, Any]:
        return self._config.get("calendar", {})

    @property
    def shipping(self) -> Dict[str, Any]:
        return self._config.get("shipping", {})

    @property
    def drive(self) -> Dict[str, Any]:
        return self._config.get("drive", {})

    @property
    def ai_chat(self) -> Dict[str, Any]:
        return self._config.get("ai_chat", {})

    def get_email_password(self, env_key: str) -> str:
        return self._get_env_value(env_key)
