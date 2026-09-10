from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
import logging
import re
import uuid
import zipfile
import hashlib
import threading

from PIL import Image
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.services.audit_service import AuditService
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import ExtractionError, ExtractionService
from app.services.vector_store_service import VectorStoreService


logger = logging.getLogger(__name__)
_processing_lock = threading.Lock()


class InvalidDocumentError(ValueError):
    pass


class DuplicateDocumentError(InvalidDocumentError):
    def __init__(self, document):
        self.document_id = document.id
        super().__init__(f"Este arquivo já está na biblioteca: {document.original_filename}.")


EXTENSION_TYPES = {
    ".pdf": "PDF",
    ".txt": "TXT",
    ".docx": "DOCX",
    ".xlsx": "XLSX",
    ".png": "IMAGE",
    ".jpg": "IMAGE",
    ".jpeg": "IMAGE",
}


class DocumentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = DocumentRepository()
        self.audit = AuditService()
        self.extractor = ExtractionService(settings)
        self.chunker = ChunkingService(settings.chunk_size, settings.chunk_overlap)

    def validate(self, filename: str, content: bytes) -> tuple[str, str]:
        original_name = Path(filename.replace("\\", "/")).name
        if not original_name or original_name in {".", ".."}:
            raise InvalidDocumentError("Nome de arquivo inválido.")
        extension = Path(original_name).suffix.lower()
        file_type = EXTENSION_TYPES.get(extension)
        if file_type is None:
            raise InvalidDocumentError("Formato de arquivo não suportado.")
        if not content:
            raise InvalidDocumentError("O arquivo está vazio.")
        if len(content) > self.settings.max_upload_size_mb * 1024 * 1024:
            raise InvalidDocumentError("Arquivo excede o tamanho permitido.")
        if not self._matches_content(extension, content):
            raise InvalidDocumentError("O conteúdo do arquivo não corresponde ao formato informado.")
        safe_name = re.sub(r"[^\w.() -]", "_", Path(original_name).stem, flags=re.UNICODE)[:240] + extension
        return safe_name, file_type

    @staticmethod
    def _matches_content(extension: str, content: bytes) -> bool:
        if extension == ".pdf":
            return content.startswith(b"%PDF-")
        if extension == ".png":
            signature_matches = content.startswith(b"\x89PNG\r\n\x1a\n")
            return signature_matches and DocumentService._is_valid_image(content)
        if extension in {".jpg", ".jpeg"}:
            signature_matches = content.startswith(b"\xff\xd8\xff")
            return signature_matches and DocumentService._is_valid_image(content)
        if extension == ".txt":
            if b"\x00" in content[:4096]:
                return False
            try:
                content.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    content.decode("cp1252")
                except UnicodeDecodeError:
                    return False
            return True
        if extension in {".docx", ".xlsx"}:
            try:
                with zipfile.ZipFile(BytesIO(content)) as archive:
                    if sum(item.file_size for item in archive.infolist()) > 200 * 1024 * 1024:
                        return False
                    names = set(archive.namelist())
            except zipfile.BadZipFile:
                return False
            marker = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
            return marker in names
        return False

    @staticmethod
    def _is_valid_image(content: bytes) -> bool:
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except Exception:
            return False
        return True

    def create_and_process(
        self, db: Session, user: User, original_filename: str, content: bytes, ip_address: str | None,
        *, process: bool = True,
    ) -> Document:
        safe_original, file_type = self.validate(original_filename, content)
        content_hash = hashlib.sha256(content).hexdigest()
        existing = db.scalar(select(Document).where(Document.user_id == user.id, Document.content_hash == content_hash))
        if existing:
            raise DuplicateDocumentError(existing)
        version = (db.scalar(select(func.max(Document.version)).where(Document.user_id == user.id, Document.original_filename == safe_original)) or 0) + 1
        extension = Path(safe_original).suffix.lower()
        internal_name = f"{uuid.uuid4().hex}{extension}"
        upload_root = self.settings.resolved_upload_dir
        upload_root.mkdir(parents=True, exist_ok=True)
        path = (upload_root / internal_name).resolve()
        if not path.is_relative_to(upload_root.resolve()):
            raise InvalidDocumentError("Caminho de arquivo inválido.")
        path.write_bytes(content)

        document = Document(
            user_id=user.id,
            filename=internal_name,
            original_filename=safe_original,
            file_type=file_type,
            file_path=str(path),
            status=DocumentStatus.UPLOADED,
            content_hash=content_hash,
            size_bytes=len(content),
            version=version,
        )
        try:
            db.add(document)
            db.flush()
            self.audit.record(
                db,
                "UPLOAD_DOCUMENT",
                user.id,
                "document",
                str(document.id),
                details={"filename": safe_original, "file_type": file_type},
                ip_address=ip_address,
            )
            db.commit()
            db.refresh(document)
        except Exception:
            db.rollback()
            path.unlink(missing_ok=True)
            raise

        if process:
            self.process(db, document)
        db.refresh(document)
        return document

    def process(self, db: Session, document: Document) -> None:
        # One local index writer avoids CPU saturation and overlapping replacements.
        with _processing_lock:
            self._process(db, document)

    def _process(self, db: Session, document: Document) -> None:
        previous_generation = document.index_generation
        generation = uuid.uuid4().hex
        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        document.processing_stage = "Extraindo texto"
        document.progress = 10
        db.commit()
        try:
            sections = self.extractor.extract(Path(document.file_path), document.file_type)
            document.processing_stage = "Preparando busca"
            document.progress = 40
            db.commit()
            embedding_service = EmbeddingService(self.settings)
            token_limit = min(self.settings.chunk_token_limit, embedding_service.max_tokens)
            chunker = ChunkingService(self.settings.chunk_size, self.settings.chunk_overlap,
                token_counter=embedding_service.token_count, token_limit=token_limit,
                token_overlap=min(self.settings.chunk_token_overlap, token_limit // 3))
            chunks = chunker.split(sections)
            if not chunks:
                raise RuntimeError("Nenhum trecho textual válido foi criado.")
            document.processing_stage = "Criando índice"
            document.progress = 60
            db.commit()
            embeddings = embedding_service.embed_documents(
                [chunk.text for chunk in chunks]
            )
            VectorStoreService(self.settings.resolved_chroma_dir).add_document(
                document.id,
                document.user_id,
                document.original_filename,
                chunks,
                embeddings,
                generation=generation,
            )
            document.status = DocumentStatus.READY
            document.processed_at = datetime.now(UTC)
            document.index_generation = generation
            document.index_version = self.index_version(self.settings)
            document.sections = sections
            document.warnings = self.extractor.warnings
            document.progress = 100
            document.processing_stage = "Pronto"
            document.chunk_count = len(chunks)
            document.size_bytes = Path(document.file_path).stat().st_size
            document.content_hash = hashlib.sha256(Path(document.file_path).read_bytes()).hexdigest()
            for previous in db.scalars(select(Document).where(Document.user_id == document.user_id,
                    Document.original_filename == document.original_filename,
                    Document.version < document.version)):
                previous.archived = True
            db.commit()
            try:
                VectorStoreService(self.settings.resolved_chroma_dir).discard_generation(document.id, generation, keep=True)
            except Exception:
                logger.warning("Limpeza de índice antigo pendente para documento %s", document.id)
        except Exception as exc:
            db.rollback()
            try:
                VectorStoreService(self.settings.resolved_chroma_dir).discard_generation(document.id, generation)
            except Exception as cleanup_error:
                logger.warning(
                    "Não foi possível limpar vetores após erro do documento %s: %s",
                    document.id,
                    cleanup_error,
                )
            failed = db.get(Document, document.id)
            if failed is not None:
                failed.status = DocumentStatus.READY if previous_generation else DocumentStatus.ERROR
                failed.index_generation = previous_generation
                failed.processing_stage = "Reprocessamento falhou; versão anterior mantida" if previous_generation else "Falha no processamento"
                failed.error_message = str(exc)[:500] if isinstance(exc, (InvalidDocumentError, ExtractionError)) else "Não foi possível preparar a busca. Verifique o diagnóstico e tente reprocessar."
                self.audit.record(
                    db,
                    "PROCESS_DOCUMENT_ERROR",
                    failed.user_id,
                    "document",
                    str(failed.id),
                    details={"error_type": type(exc).__name__},
                )
                db.commit()

    @staticmethod
    def index_version(settings):
        return f"tokens-v2:{settings.embedding_provider}:{settings.embedding_model}:{settings.chunk_token_limit}:{settings.chunk_token_overlap}"

    @staticmethod
    def process_in_background(document_id):
        from app.db.session import SessionLocal
        from app.core.config import get_settings
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if document:
                DocumentService(get_settings()).process(db, document)

    def delete(self, db: Session, document: Document, user_id: int) -> None:
        VectorStoreService(self.settings.resolved_chroma_dir).delete_document(document.id)
        path = Path(document.file_path).resolve()
        upload_root = self.settings.resolved_upload_dir.resolve()
        if path.is_relative_to(upload_root):
            path.unlink(missing_ok=True)
        self.audit.record(db, "DELETE_DOCUMENT", user_id, "document", str(document.id))
        db.delete(document)
        db.commit()
