from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserRead, UserUpdate
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
