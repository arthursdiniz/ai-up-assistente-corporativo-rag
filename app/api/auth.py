from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import BootstrapRequest, BootstrapStatus, LoginRequest, TokenResponse
from app.schemas.common import MessageResponse
from app.schemas.user import UserRead
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.bootstrap_service import (
    BootstrapAlreadyCompleted,
    BootstrapForbidden,
    BootstrapService,
    BootstrapUnavailable,
)
from app.services.login_limiter import check_login, login_succeeded
from app.services.session_service import SessionService


router = APIRouter(prefix="/auth", tags=["Autenticação"])
auth_service = AuthService()
audit_service = AuditService()
settings = get_settings()
session_service = SessionService(settings)
bootstrap_service = BootstrapService(settings)


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=session_service.cookie_name,
        value=raw_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="strict",
        path="/api/auth",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=session_service.cookie_name,
        path="/api/auth",
        secure=settings.app_env != "development",
        httponly=True,
        samesite="strict",
    )


@router.get("/bootstrap", response_model=BootstrapStatus)
def bootstrap_status(db: Session = Depends(get_db)) -> BootstrapStatus:
    return BootstrapStatus(
        required=bootstrap_service.is_required(db),
        available=bootstrap_service.is_available(),
        token_required=bootstrap_service.token_required(),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_first_admin(
    payload: BootstrapRequest,
    request: Request,
    response: Response,
    bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
    db: Session = Depends(get_db),
) -> TokenResponse:
    if not bootstrap_service.is_required(db):
        raise HTTPException(
            status_code=409, detail="A configuração inicial já foi concluída."
        )
    try:
        bootstrap_service.validate_access(
            request.client.host if request.client else None, bootstrap_token
        )
        result = bootstrap_service.create_first_admin(
            db,
            name=payload.name,
            email=payload.email,
            password=payload.password,
            ip_address=request.client.host if request.client else None,
        )
    except BootstrapAlreadyCompleted as exc:
        raise HTTPException(
            status_code=409, detail="A configuração inicial já foi concluída."
        ) from exc
    except BootstrapForbidden as exc:
        raise HTTPException(status_code=403, detail="Configuração inicial não autorizada.") from exc
    except BootstrapUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Defina BOOTSTRAP_TOKEN para habilitar a configuração inicial neste ambiente.",
        ) from exc
    set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(
        access_token=create_access_token(
            str(result.user.id), token_version=result.user.token_version
        ),
        user=UserRead.model_validate(result.user),
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ip = request.client.host if request.client else "local"
    check_login(ip, payload.email)
    user = auth_service.authenticate(db, str(payload.email), payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos."
        )
    login_succeeded(ip, payload.email)
    audit_service.record(db, "LOGIN", user.id, ip_address=request.client.host if request.client else None)
    refresh_token = session_service.issue(db, user.id)
    db.commit()
    set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=create_access_token(str(user.id), token_version=user.token_version), user=UserRead.model_validate(user)
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    refreshed = session_service.rotate(
        db, request.cookies.get(session_service.cookie_name)
    )
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Entre novamente.",
        )
    user, refresh_token = refreshed
    db.commit()
    set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=create_access_token(
            str(user.id), token_version=user.token_version
        ),
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    current_user.token_version += 1
    session_service.revoke_all(db, current_user.id)
    audit_service.record(
        db,
        "LOGOUT",
        current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    clear_refresh_cookie(response)
    return MessageResponse(detail="Sessões encerradas.")


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


@router.post("/password", response_model=MessageResponse)
def change_password(
    payload: PasswordChange,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Senha atual incorreta.")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    session_service.revoke_all(db, user.id)
    audit_service.record(db, "CHANGE_PASSWORD", user.id)
    db.commit()
    clear_refresh_cookie(response)
    return MessageResponse(detail="Senha alterada. Entre novamente.")
