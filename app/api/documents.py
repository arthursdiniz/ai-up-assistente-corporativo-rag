from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import get_current_user
from app.db.session import get_db
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentRead, DocumentSuggestions, DocumentUpdate
from app.services.document_service import DocumentService, InvalidDocumentError, DuplicateDocumentError


router = APIRouter(prefix="/documents", tags=["Documentos"])
repository = DocumentRepository()


def serialize_document(document: Document) -> DocumentRead:
    friendly_error = (
        document.error_message
        if document.error_message
        else None
    )
    return DocumentRead(
        id=document.id,
        original_filename=document.original_filename,
        file_type=document.file_type,
        status=document.status,
        status_message=friendly_error,
        created_at=document.created_at,
        processed_at=document.processed_at,
        size_bytes=document.size_bytes, category=document.category, version=document.version,
        archived=document.archived, progress=document.progress, processing_stage=document.processing_stage,
        chunk_count=document.chunk_count, warnings=document.warnings or [],
        needs_reindex=document.index_version != DocumentService.index_version(get_settings()),
    )


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRead:
    settings = get_settings()
    limit = settings.max_upload_size_mb * 1024 * 1024
    content = file.file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail="Arquivo excede o tamanho permitido.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    try:
        document = DocumentService(settings).create_and_process(
            db,
            current_user,
            file.filename,
            content,
            request.client.host if request.client else None,
            process=not settings.background_processing,
        )
    except DuplicateDocumentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if settings.background_processing:
        background_tasks.add_task(DocumentService.process_in_background, document.id)
    return serialize_document(document)


@router.get("", response_model=list[DocumentRead])
def list_documents(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    q: str = Query(default="", max_length=200), offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    category: str = Query(default="", max_length=80), document_status: DocumentStatus | None = None,
    archived: bool | None = None,
) -> list[DocumentRead]:
    query = select(Document).where(Document.user_id == current_user.id)
    if q.strip():
        query = query.where(Document.original_filename.icontains(q.strip(), autoescape=True))
    if category.strip():
        query = query.where(Document.category.icontains(category.strip(), autoescape=True))
    if document_status is not None:
        query = query.where(Document.status == document_status)
    if archived is not None:
        query = query.where(Document.archived == archived)
    return [serialize_document(item) for item in db.scalars(query.order_by(Document.created_at.desc(), Document.id.desc()).offset(offset).limit(limit))]


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRead:
    document = repository.get_owned(db, document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return serialize_document(document)


@router.get("/{document_id}/suggestions", response_model=DocumentSuggestions)
def suggestions(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentSuggestions:
    document = repository.get_owned(db, document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    name = document.original_filename
    return DocumentSuggestions(
        suggestions=[
            f'Resuma os pontos mais importantes de "{name}".',
            f'Quais prazos e valores aparecem em "{name}"?',
            f'Há riscos ou obrigações relevantes em "{name}"?',
            f'Quais diferenças existem entre "{name}" e os outros documentos?',
            f'Onde estão as informações mais importantes de "{name}"?',
        ]
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    document = repository.get_owned(db, document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if document.status in (DocumentStatus.UPLOADED, DocumentStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="Aguarde o processamento antes de excluir.")
    DocumentService(get_settings()).delete(db, document, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def owned(db, document_id, user_id):
    document = repository.get_owned(db, document_id, user_id)
    if not document:
        raise HTTPException(404, "Documento não encontrado.")
    return document


@router.patch("/{document_id}", response_model=DocumentRead)
def update_document(document_id: int, payload: DocumentUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = owned(db, document_id, user.id)
    if payload.category is not None:
        if not payload.category.strip():
            raise HTTPException(422, "Informe uma categoria.")
        document.category = payload.category.strip()
    if payload.archived is not None:
        document.archived = payload.archived
    db.commit()
    return serialize_document(document)


@router.post("/{document_id}/reprocess", response_model=DocumentRead)
def reprocess(document_id: int, background_tasks: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = owned(db, document_id, user.id)
    if document.status in (DocumentStatus.PROCESSING, DocumentStatus.UPLOADED):
        raise HTTPException(409, "O documento já está na fila.")
    document.status = DocumentStatus.UPLOADED
    document.progress = 0
    document.processing_stage = "Aguardando reprocessamento"
    db.commit()
    background_tasks.add_task(DocumentService.process_in_background, document.id)
    return serialize_document(document)


@router.get("/{document_id}/preview")
def preview(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=300), page: int | None = Query(None, ge=1)):
    document = owned(db, document_id, user.id)
    sections = document.sections or []
    if page is not None:
        sections = [section for section in sections if section.get("page") == page]
    return {"document":serialize_document(document), "sections":sections[offset:offset+limit], "total":len(sections)}


@router.get("/{document_id}/file")
def download(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = owned(db, document_id, user.id)
    path = Path(document.file_path).resolve()
    if not path.is_relative_to(get_settings().resolved_upload_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Arquivo original indisponível.")
    return FileResponse(path, filename=document.original_filename, headers={"X-Content-Type-Options":"nosniff", "Cache-Control":"no-store"})


@router.get("/{document_id}/pages/{page}")
def render_page(document_id: int, page: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    import pymupdf
    document = owned(db, document_id, user.id)
    path = Path(document.file_path).resolve()
    if document.file_type.upper() != "PDF" or not path.is_relative_to(get_settings().resolved_upload_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "PDF indisponível.")
    try:
        with pymupdf.open(path) as pdf:
            if page < 1 or page > len(pdf) or pdf.needs_pass:
                raise HTTPException(404, "Página indisponível.")
            original = pdf[page - 1]
            scale = min(1.5, 1600 / max(original.rect.width, original.rect.height, 1))
            image = original.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
        return Response(image, media_type="image/png", headers={"Cache-Control":"no-store", "X-Content-Type-Options":"nosniff"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Não foi possível renderizar esta página. Baixe o original para conferir.")
