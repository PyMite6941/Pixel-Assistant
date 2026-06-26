"""
Startup password protection for Pixel Assistant.
Hash stored in .env as PIXEL_PASSWORD_HASH + PIXEL_PASSWORD_SALT.
Uses PBKDF2-HMAC-SHA256 (stdlib, no extra deps).
"""
import getpass
import hashlib
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).parent.parent.parent
ENV_FILE  = BASE_DIR / ".env"


def _hash(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return dk.hex()


def has_password() -> bool:
    load_dotenv(ENV_FILE, override=True)
    return bool(os.getenv("PIXEL_PASSWORD_HASH"))


def set_password(password: str) -> None:
    ENV_FILE.touch(exist_ok=True)
    salt = secrets.token_hex(16)
    h    = _hash(password, salt)
    set_key(str(ENV_FILE), "PIXEL_PASSWORD_HASH", h)
    set_key(str(ENV_FILE), "PIXEL_PASSWORD_SALT", salt)


def verify_password(password: str) -> bool:
    load_dotenv(ENV_FILE, override=True)
    stored_hash = os.getenv("PIXEL_PASSWORD_HASH", "")
    stored_salt = os.getenv("PIXEL_PASSWORD_SALT", "")
    if not stored_hash or not stored_salt:
        return True
    return _hash(password, stored_salt) == stored_hash


def clear_password() -> None:
    set_key(str(ENV_FILE), "PIXEL_PASSWORD_HASH", "")
    set_key(str(ENV_FILE), "PIXEL_PASSWORD_SALT", "")


def prompt_login() -> bool:
    """Prompt for password on startup. Returns True if access granted."""
    if not has_password():
        return True
    for attempt in range(3):
        pw = getpass.getpass("Pixel password: ")
        if verify_password(pw):
            return True
        remaining = 2 - attempt
        if remaining:
            print(f"Wrong password. {remaining} attempt(s) left.")
    print("Access denied.")
    return False
