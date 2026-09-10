from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import get_current_user, require_roles
from app.db.session import get_db
from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User, UserRole
from app.schemas.organization import (
    OrganizationRead,
    OrganizationUpdate,
    TeamCreate,
    TeamMembersUpdate,
    TeamRead,
)
from app.services.audit_service import AuditService


router = APIRouter(prefix="/organizations", tags=["Organizações"])
admin_only = require_roles(UserRole.IT_ADMIN)
audit_service = AuditService()


def serialize_organization(
    db: Session,
    organization_id: int,
    *,
    visible_team_ids: set[int] | None = None,
    include_members: bool = True,
) -> OrganizationRead:
    organization = db.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .options(selectinload(Organization.teams).selectinload(Team.members))
    )
    if organization is None:
        raise HTTPException(404, "Organização não encontrada.")
    teams = [
        team
        for team in organization.teams
        if visible_team_ids is None or team.id in visible_team_ids
    ]
    return OrganizationRead(
        id=organization.id,
        name=organization.name,
        teams=[
            TeamRead(
                id=team.id,
                name=team.name,
                member_ids=team.member_ids if include_members else [],
                created_at=team.created_at,
            )
            for team in teams
        ],
    )


@router.get("/current", response_model=OrganizationRead)
def current_organization(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OrganizationRead:
    if user.role == UserRole.IT_ADMIN:
        return serialize_organization(db, user.organization_id)
    return serialize_organization(
        db,
        user.organization_id,
        visible_team_ids=set(user.team_ids),
        include_members=False,
    )


@router.patch("/current", response_model=OrganizationRead)
def update_organization(
    payload: OrganizationUpdate,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> OrganizationRead:
    organization = db.get(Organization, user.organization_id)
    if organization is None:
        raise HTTPException(404, "Organização não encontrada.")
    organization.name = payload.name
    audit_service.record(
        db, "UPDATE_ORGANIZATION", user.id, "organization", str(organization.id)
    )
    db.commit()
    return serialize_organization(db, organization.id)


@router.post("/teams", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> TeamRead:
    team = Team(organization_id=user.organization_id, name=payload.name)
    db.add(team)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe uma equipe com este nome.") from exc
    audit_service.record(db, "CREATE_TEAM", user.id, "team", str(team.id))
    db.commit()
    db.refresh(team)
    return TeamRead.model_validate(team)


@router.put("/teams/{team_id}/members", response_model=TeamRead)
def replace_team_members(
    team_id: int,
    payload: TeamMembersUpdate,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> TeamRead:
    team = db.scalar(
        select(Team)
        .where(Team.id == team_id, Team.organization_id == user.organization_id)
        .options(selectinload(Team.members))
    )
    if team is None:
        raise HTTPException(404, "Equipe não encontrada.")
    requested = set(payload.user_ids)
    members = list(
        db.scalars(
            select(User).where(
                User.organization_id == user.organization_id, User.id.in_(requested)
            )
        )
    ) if requested else []
    if {member.id for member in members} != requested:
        raise HTTPException(404, "Um dos usuários não pertence à organização.")
    team.members = members
    audit_service.record(
        db,
        "UPDATE_TEAM_MEMBERS",
        user.id,
        "team",
        str(team.id),
        details={"member_count": len(members)},
    )
    db.commit()
    db.refresh(team)
    return TeamRead.model_validate(team)
