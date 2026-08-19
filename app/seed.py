"""
Bootstraps the very first admin account. Every other account must come
through the invite system — this script is the one deliberate exception,
since without an admin, no invite can ever be created.

Usage: docker compose exec api python -m app.seed
Reads ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_DISPLAY_NAME from the
environment, or falls back to interactive input for local dev.
"""
import asyncio
import getpass
import os

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserPreference


async def seed_admin() -> None:
    email = os.environ.get("ADMIN_EMAIL") or input("Admin email: ").strip()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password (min 10 chars): ")
    display_name = os.environ.get("ADMIN_DISPLAY_NAME") or "Admin"

    if len(password) < 10:
        raise SystemExit("Password must be at least 10 characters.")

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            print(f"User {email} already exists — not creating a duplicate.")
            return

        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            role="admin",
            status="active",
        )
        db.add(user)
        await db.flush()
        db.add(UserPreference(user_id=user.id))
        await db.commit()
        print(f"Created admin user: {email}")


if __name__ == "__main__":
    asyncio.run(seed_admin())
