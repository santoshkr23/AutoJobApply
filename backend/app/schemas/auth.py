from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    accept_terms: bool
    accept_privacy: bool

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.strip().lower()


class EmailIn(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.strip().lower()


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetPasswordIn(TokenIn):
    new_password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class DeleteAccountIn(BaseModel):
    password: str | None = Field(default=None, max_length=128)
    confirm: str  # must equal "DELETE"


class MessageOut(BaseModel):
    message: str


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    email_verified: bool
    onboarding_step: int
    onboarding_completed: bool
    has_password: bool
    created_at: datetime
    plan: str = "free"


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str
    token: str | None = None  # only returned to API clients that send X-Return-Token: 1
