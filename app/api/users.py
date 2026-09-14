from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.document import Document
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserDeactivate, UserRead, UserUpdate
from app.services.audit_service import AuditService
from app.services.session_service import SessionService


router = APIRouter(prefix="/users", tags=["Usuários"])
repository = UserRepository()
audit_service = AuditService()
session_service = SessionService(get_settings())
admin_only = require_roles(UserRole.IT_ADMIN)


@router.get("", response_model=list[UserRead])
def list_users(
    current_user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> list[User]:
    return repository.list(db, current_user.organization_id)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    current_user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> User:
    email = str(payload.email).lower()
    if repository.get_by_email(db, email):
        raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail.")
    user = User(
        name=payload.name.strip(),
        email=email,
        role=payload.role,
        organization_id=current_user.organization_id,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    audit_service.record(db, "CREATE_USER", current_user.id, "user", str(user.id))
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/deactivate", response_model=UserRead)
def deactivate_user(
    user_id: int,
    payload: UserDeactivate,
    current_user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(
        select(User)
        .where(
            User.id == user_id,
            User.organization_id == current_user.organization_id,
        )
        .with_for_update()
    )
    if user is None:
        raise HTTPException(404, "Usuário não encontrado.")
    if user.id == current_user.id:
        raise HTTPException(409, "Você não pode desativar seu próprio usuário.")
    if not user.active:
        return user
    if user.role == UserRole.IT_ADMIN:
        administrator_count = db.scalar(
            select(func.count(User.id)).where(
                User.organization_id == current_user.organization_id,
                User.role == UserRole.IT_ADMIN,
                User.active.is_(True),
            )
        ) or 0
        if administrator_count <= 1:
            raise HTTPException(409, "Mantenha pelo menos um administrador ativo.")
    document_count = db.scalar(
        select(func.count(Document.id)).where(Document.user_id == user.id)
    ) or 0
    target = None
    if payload.transfer_document_owner_id is not None:
        target = db.scalar(
            select(User).where(
                User.id == payload.transfer_document_owner_id,
                User.organization_id == current_user.organization_id,
                User.active.is_(True),
            )
        )
        if target is None or target.id == user.id:
            raise HTTPException(422, "Escolha outro usuário ativo da organização.")
    if document_count and target is None:
        raise HTTPException(
            409,
            "Este usuário possui documentos. Escolha quem receberá a propriedade antes de desativá-lo.",
        )
    if target is not None and document_count:
        db.execute(
            update(Document)
            .where(Document.user_id == user.id)
            .values(user_id=target.id)
        )
        audit_service.record(
            db,
            "TRANSFER_DOCUMENTS",
            current_user.id,
            "user",
            str(user.id),
            details={"target_user_id": target.id, "document_count": document_count},
        )
    user.active = False
    user.token_version += 1
    session_service.revoke_all(db, user.id)
    audit_service.record(
        db,
        "USER_BLOCKED",
        current_user.id,
        "user",
        str(user.id),
        details={"active": False, "documents_transferred": document_count},
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == current_user.organization_id,
        )
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.id == current_user.id and payload.active is False:
        raise HTTPException(status_code=409, detail="Você não pode desativar seu próprio usuário.")
    if payload.active is False:
        document_count = db.scalar(
            select(func.count(Document.id)).where(Document.user_id == user.id)
        ) or 0
        if document_count:
            raise HTTPException(
                409,
                "Transfira os documentos ao desativar este usuário.",
            )
    if user.role == UserRole.IT_ADMIN and (payload.active is False or payload.role not in (None, UserRole.IT_ADMIN)):
        administrators = list(
            db.scalars(
                select(User)
                .where(
                    User.organization_id == current_user.organization_id,
                    User.role == UserRole.IT_ADMIN,
                    User.active.is_(True),
                )
                .order_by(User.id)
                .with_for_update()
            )
        )
        if len(administrators) <= 1 and user.active:
            raise HTTPException(409, "Mantenha pelo menos um administrador ativo.")
    previous_active = user.active
    previous_role = user.role
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user, field, value.strip() if field == "name" else value)
    if "active" in changes or "role" in changes:
        user.token_version += 1
        session_service.revoke_all(db, user.id)
    event_recorded = False
    if "active" in changes and user.active != previous_active:
        audit_service.record(
            db,
            "USER_UNBLOCKED" if user.active else "USER_BLOCKED",
            current_user.id,
            "user",
            str(user.id),
            details={"active": user.active},
        )
        event_recorded = True
    if "role" in changes and user.role != previous_role:
        audit_service.record(
            db,
            "USER_ROLE_CHANGED",
            current_user.id,
            "user",
            str(user.id),
            details={"from": previous_role.value, "to": user.role.value},
        )
        event_recorded = True
    remaining_fields = [field for field in changes if field not in {"active", "role"}]
    if remaining_fields or not event_recorded:
        audit_service.record(
            db,
            "UPDATE_USER",
            current_user.id,
            "user",
            str(user.id),
            details={"fields": remaining_fields},
        )
    db.commit()
    db.refresh(user)
    return user
