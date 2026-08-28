"""
Auth + invite redemption endpoints.

Invite validation and signup deliberately give identical "invalid or
expired invite" errors whether the code doesn't exist, is expired, is
revoked, or is already fully used — the spec requires never revealing
which case applies. Both endpoints are rate-limited per IP.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import is_rate_limited
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_identifier,
    hash_invite_code,
    hash_password,
    verify_password,
)
from app.models.user import Invite, InviteRedemption, User, UserPreference
from app.schemas.auth import (
    InviteValidateRequest,
    InviteValidateResponse,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenPairResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

INVITE_ERROR = "Invite code is invalid or expired."


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/invite/validate", response_model=InviteValidateResponse)
async def validate_invite(
    body: InviteValidateRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    if await is_rate_limited(f"invite-validate:{_client_ip(request)}", max_requests=10):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later.")

    invite = await _lookup_valid_invite(db, body.code)
    if invite is None:
        return InviteValidateResponse(valid=False)
    return InviteValidateResponse(valid=True, recipient_label=invite.recipient_label)


async def _lookup_valid_invite(db: AsyncSession, raw_code: str) -> Invite | None:
    code_hash = hash_invite_code(raw_code)
    result = await db.execute(select(Invite).where(Invite.code_hash == code_hash))
    invite = result.scalar_one_or_none()
    if invite is None:
        return None
    if invite.revoked_at is not None:
        return None
    if invite.expires_at is not None and invite.expires_at < datetime.now(timezone.utc):
        return None
    if invite.use_count >= invite.max_uses:
        return None
    return invite


@router.post("/signup", response_model=TokenPairResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if await is_rate_limited(f"signup:{_client_ip(request)}", max_requests=5):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later.")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered.")

    # Single transaction: re-validate the invite under lock, create the
    # user, increment use_count, and record the redemption atomically so
    # concurrent signups against the same single-use invite can't both win.
    async with db.begin_nested() if db.in_transaction() else db.begin():
        locked = await db.execute(
            select(Invite).where(Invite.code_hash == hash_invite_code(body.invite_code)).with_for_update()
        )
        invite = locked.scalar_one_or_none()
        if invite is None or invite.revoked_at is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, INVITE_ERROR)
        if invite.expires_at is not None and invite.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, INVITE_ERROR)
        if invite.use_count >= invite.max_uses:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, INVITE_ERROR)

        user = User(
            email=body.email,
            password_hash=hash_password(body.password),
            display_name=body.display_name,
            role="member",
            status="active",
        )
        db.add(user)
        await db.flush()  # populate user.id

        db.add(UserPreference(user_id=user.id))

        now = datetime.now(timezone.utc)
        invite.use_count += 1
        invite.last_used_at = now
        if invite.first_used_at is None:
            invite.first_used_at = now
        if invite.use_count >= invite.max_uses:
            invite.is_used = True

        db.add(
            InviteRedemption(
                invite_id=invite.id,
                user_id=user.id,
                ip_hash=hash_identifier(_client_ip(request)),
                user_agent_hash=hash_identifier(request.headers.get("user-agent", "")),
            )
        )

    await db.commit()
    return TokenPairResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenPairResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if await is_rate_limited(
        f"login:{_client_ip(request)}", max_requests=settings.login_rate_limit_per_minute
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later.")

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Constant-shape failure: don't reveal whether the email exists.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    if user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is not active.")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return TokenPairResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    import jwt as _jwt

    try:
        payload = decode_token(body.refresh_token)
    except _jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.")

    return TokenPairResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),  # rotated
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.status = "deleted"
    user.email = f"deleted-{user.id}@example.invalid"
    await db.commit()
