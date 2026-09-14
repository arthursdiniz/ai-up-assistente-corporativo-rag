from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.user import UserRole


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.count("@") != 1:
        raise ValueError("E-mail inválido.")
    local, domain = normalized.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("E-mail inválido.")
    return normalized


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: UserRole = UserRole.USER
    team_ids: list[int] = Field(default_factory=list, max_length=50)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class InvitationRead(BaseModel):
    id: int
    email: str
    role: UserRole
    team_ids: list[int] = Field(default_factory=list)
    status: str
    expires_at: datetime
    created_at: datetime


class InvitationCreated(BaseModel):
    invitation: InvitationRead
    accept_path: str


class InvitationTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class InvitationInfo(BaseModel):
    organization_name: str
    email: str
    role: UserRole
    expires_at: datetime


class InvitationAcceptRequest(InvitationTokenRequest):
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Informe seu nome.")
        return normalized
