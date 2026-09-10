from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.permissions import get_current_user
from app.models.user import User
from app.services.diagnostics import inspect_services


router = APIRouter(tags=["Saúde"])


@router.get("/health", summary="Verifica a aplicação e o banco")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return {"status": "degraded", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}


@router.get("/health/details")
def details(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return inspect_services(db)
