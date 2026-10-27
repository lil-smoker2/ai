from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import MIN_PASSWORD_LENGTH


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    terms_accepted: bool

    @field_validator("terms_accepted")
    @classmethod
    def must_accept_terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Terms and privacy acknowledgement are required")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    # ID token (credential) obtained from Google Identity Services.
    credential: str = Field(min_length=32, max_length=8192)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    currency: str
    country: str
    timezone: str
    is_student: bool | None
    onboarded: bool
    created_at: datetime


class OnboardingUpdate(BaseModel):
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    country: str | None = Field(default=None, max_length=60)
    timezone: str | None = Field(default=None, max_length=60)
    is_student: bool | None = None
    onboarded: bool | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
