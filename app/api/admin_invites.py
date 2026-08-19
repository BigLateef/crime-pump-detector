from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_admin
from app.core.rate_limit import is_rate_limited
from app.core.security import generate_invite_code, hash_invite_code
from app.models.user import Invite, User
from app.schemas.auth import InviteCreateRequest, InviteCreateResponse, InviteOut

router = APIRouter(prefix="/admin/invites", tags=["admin-invites"])
settings = get_settings()

# Frontend base URL used to build the registration link. In production this
# comes from an env var; hardcoded placeholder here since the frontend isn't
# built yet (Phase 6+).
_REGISTRATION_BASE_URL = "https://app.example.com/signup"


@router.post("", response_model=InviteCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: InviteCreateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Admin action, but still rate-limited (fail-closed) - an admin
    # session being scripted or compromised shouldn't be able to mint
    # unlimited invites just because it passed auth.
    await is_rate_limited(f"invite-create:{admin.id}", max_requests=20, window_seconds=60)

    raw_code = generate_invite_code(settings.invite_code_length)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)
        if body.expires_in_days
        else None
    )

    invite = Invite(
        code_hash=hash_invite_code(raw_code),
        created_by=admin.id,
        recipient_label=body.recipient_label,
        recipient_email=body.recipient_email,
        max_uses=body.max_uses,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    # The raw code is returned exactly once, here, to the admin. It is never
    # written to any log, and nothing else in the codebase can recover it
    # from code_hash.
    return InviteCreateResponse(
        id=invite.id,
        code=raw_code,
        registration_url=f"{_REGISTRATION_BASE_URL}?invite={raw_code}",
        max_uses=invite.max_uses,
        expires_at=invite.expires_at,
    )


@router.get("", response_model=list[InviteOut])
async def list_invites(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Invite).order_by(Invite.created_at.desc()))
    return result.scalars().all()


@router.post("/{invite_id}/revoke", response_model=InviteOut)
async def revoke_invite(
    invite_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Invite).where(Invite.id == invite_id))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found.")
    invite.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(invite)
    return invite
