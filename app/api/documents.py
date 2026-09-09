from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import get_current_user
from app.db.session import get_db
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentRead, DocumentSuggestions
from app.services.document_service import DocumentService, InvalidDocumentError


router = APIRouter(prefix="/documents", tags=["Documentos"])
repository = DocumentRepository()


def serialize_document(document: Document) -> DocumentRead:
    friendly_error = (
        "Não foi possível processar o documento. Consulte os logs para detalhes."
        if document.status == DocumentStatus.ERROR
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
    )


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRead:
    settings = get_settings()
    limit = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read(limit + 1)
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
        )
    except InvalidDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_document(document)


@router.get("", response_model=list[DocumentRead])
def list_documents(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[DocumentRead]:
    return [serialize_document(item) for item in repository.list_owned(db, current_user.id)]


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
    DocumentService(get_settings()).delete(db, document, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
