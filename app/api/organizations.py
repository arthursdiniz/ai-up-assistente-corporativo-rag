from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import get_current_user, require_roles
from app.db.session import get_db
from app.models.organization import Organization
from app.models.document import Document, DocumentVisibility
from app.models.invitation import Invitation
from app.models.team import Team
from app.models.user import User, UserRole
from app.schemas.organization import (
    OrganizationRead,
    OrganizationUpdate,
    TeamCreate,
    TeamMembersUpdate,
    TeamRead,
    TeamUpdate,
)
from app.schemas.invitation import InvitationCreate, InvitationCreated, InvitationRead
from app.services.audit_service import AuditService
from app.services.invitation_service import InvitationService
from app.core.config import get_settings


router = APIRouter(prefix="/organizations", tags=["Organizações"])
admin_only = require_roles(UserRole.IT_ADMIN)
audit_service = AuditService()
invitation_service = InvitationService(get_settings())


def serialize_invitation(invitation: Invitation) -> InvitationRead:
    return InvitationRead(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        team_ids=invitation.team_ids,
        status=invitation_service.status(invitation),
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


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


@router.patch("/teams/{team_id}", response_model=TeamRead)
def update_team(
    team_id: int,
    payload: TeamUpdate,
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
    previous_name = team.name
    team.name = payload.name
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe uma equipe com este nome.") from exc
    audit_service.record(
        db,
        "UPDATE_TEAM",
        user.id,
        "team",
        str(team.id),
        details={"from": previous_name, "to": team.name},
    )
    db.commit()
    db.refresh(team)
    return TeamRead.model_validate(team)


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: int,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> Response:
    team = db.scalar(
        select(Team).where(
            Team.id == team_id, Team.organization_id == user.organization_id
        )
    )
    if team is None:
        raise HTTPException(404, "Equipe não encontrada.")
    affected = db.execute(
        update(Document)
        .where(
            Document.organization_id == user.organization_id,
            Document.team_id == team.id,
        )
        .values(visibility=DocumentVisibility.PRIVATE, team_id=None)
    ).rowcount
    audit_service.record(
        db,
        "DELETE_TEAM",
        user.id,
        "team",
        str(team.id),
        details={"name": team.name, "documents_made_private": affected or 0},
    )
    db.delete(team)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.get("/invitations", response_model=list[InvitationRead])
def list_invitations(
    user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> list[InvitationRead]:
    invitations = list(
        db.scalars(
            select(Invitation)
            .where(Invitation.organization_id == user.organization_id)
            .options(selectinload(Invitation.teams))
            .order_by(Invitation.created_at.desc(), Invitation.id.desc())
            .limit(100)
        )
    )
    return [serialize_invitation(invitation) for invitation in invitations]


@router.post(
    "/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    payload: InvitationCreate,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> InvitationCreated:
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise HTTPException(409, "Já existe uma conta com este e-mail.")
    requested_team_ids = set(payload.team_ids)
    teams = list(
        db.scalars(
            select(Team).where(
                Team.organization_id == user.organization_id,
                Team.id.in_(requested_team_ids),
            )
        )
    ) if requested_team_ids else []
    if {team.id for team in teams} != requested_team_ids:
        raise HTTPException(404, "Uma das equipes não pertence à organização.")
    previous = list(
        db.scalars(
            select(Invitation)
            .where(
                Invitation.organization_id == user.organization_id,
                Invitation.email == payload.email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .with_for_update()
        )
    )
    for invitation in previous:
        invitation.revoked_at = datetime.now(UTC)
    invitation, raw_token = invitation_service.create(
        db,
        organization_id=user.organization_id,
        created_by_id=user.id,
        email=payload.email,
        role=payload.role,
        teams=teams,
    )
    db.commit()
    db.refresh(invitation)
    return InvitationCreated(
        invitation=serialize_invitation(invitation),
        accept_path=f"/invite.html#{raw_token}",
    )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: int,
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> Response:
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.organization_id == user.organization_id,
        )
    )
    if invitation is None:
        raise HTTPException(404, "Convite não encontrado.")
    if invitation_service.status(invitation) != "PENDING":
        raise HTTPException(409, "Somente convites pendentes podem ser revogados.")
    invitation.revoked_at = datetime.now(UTC)
    audit_service.record(
        db, "REVOKE_INVITATION", user.id, "invitation", str(invitation.id)
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
