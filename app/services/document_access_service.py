from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentVisibility
from app.models.team import Team, team_members
from app.models.user import User, UserRole


class InvalidDocumentScope(ValueError):
    pass


class DocumentAccessService:
    @staticmethod
    def accessible_clause(user: User):
        team_ids = select(team_members.c.team_id).where(team_members.c.user_id == user.id)
        return or_(
            Document.user_id == user.id,
            and_(
                Document.organization_id == user.organization_id,
                Document.visibility == DocumentVisibility.ORGANIZATION,
            ),
            and_(
                Document.organization_id == user.organization_id,
                Document.visibility == DocumentVisibility.TEAM,
                Document.team_id.in_(team_ids),
            ),
        )

    def get_accessible(
        self, db: Session, document_id: int, user: User
    ) -> Document | None:
        return db.scalar(
            select(Document).where(
                Document.id == document_id, self.accessible_clause(user)
            )
        )

    def validate_scope(
        self,
        db: Session,
        user: User,
        visibility: DocumentVisibility,
        team_id: int | None,
    ) -> int | None:
        if visibility == DocumentVisibility.PRIVATE:
            return None
        if visibility == DocumentVisibility.ORGANIZATION:
            return None
        if team_id is None:
            raise InvalidDocumentScope("Escolha uma equipe para compartilhar o documento.")
        team = db.scalar(
            select(Team).where(
                Team.id == team_id, Team.organization_id == user.organization_id
            )
        )
        if team is None:
            raise InvalidDocumentScope("Equipe não encontrada nesta organização.")
        if user.role != UserRole.IT_ADMIN and user.id not in team.member_ids:
            raise InvalidDocumentScope("Você só pode compartilhar com uma equipe da qual participa.")
        return team.id
