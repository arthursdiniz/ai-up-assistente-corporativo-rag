from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.permissions import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.services.login_limiter import check_login, login_succeeded
from pydantic import BaseModel, Field
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import MessageResponse
from app.schemas.user import UserRead
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["Autenticação"])
auth_service = AuthService()
audit_service = AuditService()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = request.client.host if request.client else "local"
    check_login(ip, payload.email)
    user = auth_service.authenticate(db, str(payload.email), payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos."
        )
    login_succeeded(ip, payload.email)
    audit_service.record(db, "LOGIN", user.id, ip_address=request.client.host if request.client else None)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(str(user.id), token_version=user.token_version), user=UserRead.model_validate(user)
    )


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    current_user.token_version += 1
    audit_service.record(
        db,
        "LOGOUT",
        current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return MessageResponse(detail="Sessões encerradas.")


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


@router.post("/password", response_model=MessageResponse)
def change_password(payload: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Senha atual incorreta.")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    audit_service.record(db, "CHANGE_PASSWORD", user.id)
    db.commit()
    return MessageResponse(detail="Senha alterada. Entre novamente.")
