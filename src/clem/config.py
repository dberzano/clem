"""Credentials and cache locations.

Credentials: env CLEM_USERNAME / CLEM_PASSWORD win, else ~/.config/clem/config.toml:
    username = "..."
    password = "..."
"""
import os
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo

from .errors import ClemError

BASE_URL = "https://www.espace-citoyens.net/thoiry/espace-citoyens/"
CONFIG_PATH = Path.home() / ".config" / "clem" / "config.toml"
SESSION_PATH = Path.home() / ".cache" / "clem" / "session.json"
RESULT_CACHE_PATH = SESSION_PATH.with_name("reservations.json")
RESULT_CACHE_TTL_SECONDS = 2 * 60 * 60
RESERVATION_TIMEZONE = ZoneInfo("Europe/Paris")


def load_credentials(config_path: Path = CONFIG_PATH) -> tuple[str, str]:
    username = os.environ.get("CLEM_USERNAME")
    password = os.environ.get("CLEM_PASSWORD")
    if not (username and password) and config_path.is_file():
        data = tomllib.loads(config_path.read_text())
        username = username or data.get("username")
        password = password or data.get("password")
    if not (username and password):
        raise ClemError(
            "config",
            f"Missing credentials: set CLEM_USERNAME/CLEM_PASSWORD or create {config_path}",
        )
    return username, password
