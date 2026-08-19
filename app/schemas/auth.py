from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class InviteValidateRequest(BaseModel):
    code: str


class InviteValidateResponse(BaseModel):
    valid: bool
    recipient_label: str | None = None


class SignupRequest(BaseModel):
    invite_code: str
    email: EmailStr
    password: str = Field(min_length=10)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class InviteCreateRequest(BaseModel):
    recipient_label: str | None = None
    recipient_email: EmailStr | None = None
    max_uses: int = Field(default=1, ge=1, le=50)
    expires_in_days: int | None = Field(default=14, ge=1, le=365)


class InviteCreateResponse(BaseModel):
    id: str
    code: str  # shown once — never persisted or logged in raw form
    registration_url: str
    max_uses: int
    expires_at: datetime | None


class InviteOut(BaseModel):
    id: str
    recipient_label: str | None
    recipient_email: str | None
    max_uses: int
    use_count: int
    is_used: bool
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
