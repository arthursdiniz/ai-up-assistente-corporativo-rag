from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.permissions import get_current_user
from app.db.session import get_db
from app.models.auditor import AuditorAlert, AuditorReview, AuditorRun
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.auditor import (AlertDetail, AlertDocument, AlertKind, AlertPage, AlertRead, CorporateRule,
                                 ReviewCreate, ReviewRead, ReviewState, RunCreate, RunRead)
from app.services import auditor_service as service
from app.services.audit_service import AuditService
from app.services.document_access_service import DocumentAccessService


router = APIRouter(prefix="/auditor", tags=["Auditor documental"])
Database = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(get_current_user)]
LeftDocument = aliased(Document)
RightDocument = aliased(Document)


def historical_alert():
    return or_(LeftDocument.archived.is_(True),
        and_(AuditorAlert.kind != AlertKind.RELEVANT_CHANGE, RightDocument.archived.is_(True)),
        func.coalesce(LeftDocument.index_generation, "legacy") != AuditorAlert.left_generation,
        func.coalesce(RightDocument.index_generation, "legacy") != AuditorAlert.right_generation,
        LeftDocument.status != DocumentStatus.READY, RightDocument.status != DocumentStatus.READY,
        and_(AuditorAlert.valid_until.is_not(None), AuditorAlert.valid_until < date.today()))


def alert_query(user):
    return select(AuditorAlert, LeftDocument.original_filename, LeftDocument.version,
                  RightDocument.original_filename, RightDocument.version, historical_alert()).join(
        LeftDocument, LeftDocument.id == AuditorAlert.left_id).join(
        RightDocument, RightDocument.id == AuditorAlert.right_id).where(
        AuditorAlert.user_id == user.id, AuditorAlert.organization_id == user.organization_id,
        LeftDocument.organization_id == user.organization_id, RightDocument.organization_id == user.organization_id,
        DocumentAccessService.accessible_clause(user, LeftDocument),
        DocumentAccessService.accessible_clause(user, RightDocument))


def alert_read(row):
    alert, left_name, left_version, right_name, right_version, old = row
    documents = [AlertDocument(id=alert.left_id, name=left_name, version=left_version)]
    if alert.right_id != alert.left_id:
        documents.append(AlertDocument(id=alert.right_id, name=right_name, version=right_version))
    return AlertRead(id=alert.id, kind=alert.kind, state=alert.state, subject=alert.subject, explanation=alert.explanation,
                     documents=documents, evidence=alert.evidence, historical=old, detected_at=alert.detected_at)


def alert_row(db, user, alert_id, *, lock=False):
    query = alert_query(user).where(AuditorAlert.id == alert_id)
    row = db.execute(query.with_for_update(of=AuditorAlert) if lock else query).one_or_none()
    if row is None:
        raise HTTPException(404, "Alerta não encontrado.")
    return row


def detail(db, row):
    reviews = db.scalars(select(AuditorReview).where(AuditorReview.alert_id == row[0].id)
                         .order_by(AuditorReview.id.desc()).limit(100))
    return AlertDetail(**alert_read(row).model_dump(), reviews=[ReviewRead.model_validate(item) for item in reviews])


def alert_page(db, user, kind, state, q, include_historical, offset, limit, document_id=None):
    query = alert_query(user)
    if kind:
        query = query.where(AuditorAlert.kind == kind)
    if state:
        query = query.where(AuditorAlert.state == state)
    if not include_historical:
        query = query.where(~historical_alert())
    if document_id:
        query = query.where(AuditorAlert.left_id == document_id)
    if q.strip():
        term = q.strip()
        query = query.where(or_(AuditorAlert.subject.icontains(term, autoescape=True),
                               LeftDocument.original_filename.icontains(term, autoescape=True),
                               RightDocument.original_filename.icontains(term, autoescape=True)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AuditorAlert.detected_at.desc(), AuditorAlert.id.desc()).offset(offset).limit(limit))
    return AlertPage(total=total, items=[alert_read(row) for row in rows])


@router.post("/runs", response_model=RunRead, status_code=202)
def start_run(payload: RunCreate, user: Viewer, db: Database):
    return service.enqueue(db, user, payload.document_id, payload.previous_document_id)


@router.get("/runs", response_model=list[RunRead])
def list_runs(user: Viewer, db: Database, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000)):
    query = select(AuditorRun).order_by(AuditorRun.created_at.desc(), AuditorRun.id.desc()).offset(offset).limit(limit)
    return service.visible_runs(db, user, query)


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str, user: Viewer, db: Database):
    runs = service.visible_runs(db, user, select(AuditorRun).where(AuditorRun.id == run_id))
    if not runs:
        raise HTTPException(404, "Auditoria não encontrada.")
    return runs[0]


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
def cancel_run(run_id: str, user: Viewer, db: Database):
    runs = service.visible_runs(db, user, select(AuditorRun).where(AuditorRun.id == run_id).with_for_update())
    if not runs:
        raise HTTPException(404, "Auditoria não encontrada.")
    run = runs[0]
    if run.status in service.ACTIVE_STATES:
        run.status, run.stage = "cancelled", "Cancelada"
        AuditService().record(db, "CANCEL_DOCUMENT_AUDIT", user.id, "auditor_run", run.id)
    db.commit()
    return run


@router.get("/alerts", response_model=AlertPage)
def alerts(user: Viewer, db: Database, kind: AlertKind | None = None, state: ReviewState | None = None,
           q: str = Query("", max_length=200), include_historical: bool = False,
           offset: int = Query(0, ge=0, le=10000), limit: int = Query(20, ge=1, le=100)):
    return alert_page(db, user, kind, state, q, include_historical, offset, limit)


@router.get("/alerts/export")
def export_alerts(user: Viewer, db: Database, kind: AlertKind | None = None, state: ReviewState | None = None,
                  q: str = Query("", max_length=200), include_historical: bool = False,
                  offset: int = Query(0, ge=0, le=10000)):
    page = alert_page(db, user, kind, state, q, include_historical, offset, 100)
    return JSONResponse({**page.model_dump(mode="json"), "offset": offset, "limit": 100},
                        headers={"Content-Disposition": 'attachment; filename="ai-up-auditor.json"'})


@router.get("/alerts/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: int, user: Viewer, db: Database):
    return detail(db, alert_row(db, user, alert_id))


@router.get("/alerts/{alert_id}/evidence", response_model=list[CorporateRule])
def get_evidence(alert_id: int, user: Viewer, db: Database):
    return alert_read(alert_row(db, user, alert_id)).evidence


@router.post("/alerts/{alert_id}/reviews", response_model=AlertDetail)
def review_alert(alert_id: int, payload: ReviewCreate, user: Viewer, db: Database):
    row = alert_row(db, user, alert_id, lock=True)
    alert = row[0]
    last = db.scalar(select(AuditorReview).where(AuditorReview.alert_id == alert.id).order_by(AuditorReview.id.desc()).limit(1))
    if not last or (last.state, last.justification) != (payload.state, payload.justification):
        alert.state = payload.state
        db.add(AuditorReview(alert_id=alert.id, user_id=user.id, state=payload.state, justification=payload.justification))
        AuditService().record(db, "REVIEW_DOCUMENT_AUDIT", user.id, "auditor_alert", str(alert.id), details={"state": payload.state})
    db.commit()
    return detail(db, alert_row(db, user, alert_id))


@router.get("/documents/{document_id}/versions", response_model=list[AlertDocument])
def versions(document_id: int, user: Viewer, db: Database):
    query = service.allowed_documents(user).where(Document.status == DocumentStatus.READY)
    anchor = db.execute(query.with_only_columns(Document.user_id, Document.original_filename, Document.version)
                        .where(Document.id == document_id)).one_or_none()
    if anchor is None:
        raise HTTPException(404, "Documento não encontrado.")
    rows = db.execute(query.with_only_columns(Document.id, Document.original_filename, Document.version)
                      .where(Document.user_id == anchor.user_id, Document.original_filename == anchor.original_filename,
                             Document.version < anchor.version).order_by(Document.version.desc()).limit(50))
    return [AlertDocument(id=key, name=name, version=version) for key, name, version in rows]


@router.get("/documents/{document_id}/changes", response_model=AlertPage)
def changes(document_id: int, user: Viewer, db: Database,
            offset: int = Query(0, ge=0, le=10000), limit: int = Query(20, ge=1, le=100)):
    if db.scalar(service.allowed_documents(user).with_only_columns(Document.id).where(Document.id == document_id)) is None:
        raise HTTPException(404, "Documento não encontrado.")
    return alert_page(db, user, AlertKind.RELEVANT_CHANGE, None, "", True, offset, limit, document_id)
