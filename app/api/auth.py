from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.permissions import get_current_user
from app.core.security import create_access_token
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
    user = auth_service.authenticate(db, str(payload.email), payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos."
        )
    audit_service.record(db, "LOGIN", user.id, ip_address=request.client.host if request.client else None)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(str(user.id)), user=UserRead.model_validate(user)
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
    audit_service.record(
        db,
        "LOGOUT",
        current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return MessageResponse(detail="Sessão encerrada. Remova o token armazenado no navegador.")
