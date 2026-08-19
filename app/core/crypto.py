"""
Symmetric encryption for anything that must never sit in the DB in
plaintext — currently just Discord webhook URLs. Uses Fernet (AES-128-CBC
+ HMAC) keyed from DISCORD_WEBHOOK_ENCRYPTION_KEY.

The key in .env.example is a placeholder and is NOT a valid Fernet key —
generate a real one with `Fernet.generate_key()` before enabling live
Discord delivery, or this will raise at import time.
"""
import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _derive_fernet_key(raw_key: str) -> bytes:
    # Accepts any string and derives a valid 32-byte urlsafe-base64 Fernet
    # key from it, so a human-chosen passphrase in .env still works.
    digest = hashlib.sha256(raw_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    settings = get_settings()
    return Fernet(_derive_fernet_key(settings.discord_webhook_encryption_key))


def encrypt_webhook_url(raw_url: str) -> str:
    return _get_fernet().encrypt(raw_url.encode()).decode()


def decrypt_webhook_url(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()
