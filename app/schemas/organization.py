from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Informe um nome com pelo menos dois caracteres.")
        return normalized


class TeamUpdate(TeamCreate):
    pass


class TeamMembersUpdate(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=500)


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    member_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class OrganizationRead(BaseModel):
    id: int
    name: str
    teams: list[TeamRead] = Field(default_factory=list)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Informe um nome com pelo menos dois caracteres.")
        return normalized
