from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=BCRYPT_MAX_BYTES)

    @field_validator("password")
    @classmethod
    def fits_bcrypt(cls, value: str) -> str:
        if len(value.encode()) > BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
