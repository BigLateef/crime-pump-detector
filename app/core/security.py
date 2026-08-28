"""
Security primitives: password hashing, JWT issuance/verification, and
cryptographically secure invite code generation.

Design choices tied directly to spec requirements:
- Argon2id for password hashing (memory-hard, current best practice)
- Invite codes are generated with `secrets` (CSPRNG), never `random`
- Only the SHA-256 hash of an invite code is ever persisted or compared —
  the raw code is returned once, to the admin, at creation time
- JWTs are short-lived access tokens + longer-lived refresh tokens, both
  signed with SECRET_KEY (HS256); refresh rotation is handled at the
  endpoint layer (Phase 2 API), not here
"""
import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

settings = get_settings()
_hasher = PasswordHasher()

# Unambiguous alphabet: no 0/O, 1/I/L confusion
_CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL")


def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw_password)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001 — malformed hash, treat as failed verify
        return False


def generate_invite_code(length: int = 9) -> str:
    """
    Returns a code like 'K7M4-XP9Q' — cryptographically random, grouped for
    readability. `length` counts alphanumeric characters, not dashes.
    """
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
    mid = len(raw) // 2
    return f"{raw[:mid]}-{raw[mid:]}" if len(raw) > 4 else raw


def hash_invite_code(code: str) -> str:
    normalized = code.replace("-", "").upper().encode()
    return hashlib.sha256(normalized).hexdigest()


def hash_identifier(value: str) -> str:
    """Used for ip_hash / user_agent_hash — never store raw IP/UA."""
    return hashlib.sha256(value.encode()).hexdigest()


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired tokens — caller handles it."""
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
