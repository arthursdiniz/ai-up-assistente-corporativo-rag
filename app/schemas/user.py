from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole


class UserBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    role: UserRole = UserRole.USER

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.count("@") != 1:
            raise ValueError("E-mail inválido.")
        local, domain = normalized.split("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("E-mail inválido.")
        return normalized


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role: UserRole | None = None
    active: bool | None = None

    @field_validator("name", "role", "active", mode="before")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("O valor não pode ser nulo.")
        if isinstance(value, str) and not value.strip():
            raise ValueError("Informe um valor válido.")
        return value.strip() if isinstance(value, str) else value


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    active: bool
    created_at: datetime
    updated_at: datetime
    organization_id: int
    team_ids: list[int] = Field(default_factory=list)
