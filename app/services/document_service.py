from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
import logging
import re
import uuid
import zipfile

from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.services.audit_service import AuditService
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import ExtractionService
from app.services.vector_store_service import VectorStoreService


logger = logging.getLogger(__name__)


class InvalidDocumentError(ValueError):
    pass


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
        if not self._matches_content(extension, content):
            raise InvalidDocumentError("O conteúdo do arquivo não corresponde ao formato informado.")
        safe_name = re.sub(r"[^\w.() -]", "_", original_name, flags=re.UNICODE)[:255]
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
        self, db: Session, user: User, original_filename: str, content: bytes, ip_address: str | None
    ) -> Document:
        safe_original, file_type = self.validate(original_filename, content)
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

        self.process(db, document)
        db.refresh(document)
        return document

    def process(self, db: Session, document: Document) -> None:
        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        db.commit()
        try:
            sections = self.extractor.extract(Path(document.file_path), document.file_type)
            chunks = self.chunker.split(sections)
            if not chunks:
                raise RuntimeError("Nenhum trecho textual válido foi criado.")
            embeddings = EmbeddingService(self.settings).embed_documents(
                [chunk.text for chunk in chunks]
            )
            VectorStoreService(self.settings.resolved_chroma_dir).add_document(
                document.id,
                document.user_id,
                document.original_filename,
                chunks,
                embeddings,
            )
            document.status = DocumentStatus.READY
            document.processed_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:
            db.rollback()
            try:
                VectorStoreService(self.settings.resolved_chroma_dir).delete_document(document.id)
            except Exception as cleanup_error:
                logger.warning(
                    "Não foi possível limpar vetores após erro do documento %s: %s",
                    document.id,
                    cleanup_error,
                )
            failed = db.get(Document, document.id)
            if failed is not None:
                failed.status = DocumentStatus.ERROR
                failed.error_message = str(exc)[:2000]
                self.audit.record(
                    db,
                    "PROCESS_DOCUMENT_ERROR",
                    failed.user_id,
                    "document",
                    str(failed.id),
                    details={"error": str(exc)[:1000]},
                )
                db.commit()

    def delete(self, db: Session, document: Document, user_id: int) -> None:
        VectorStoreService(self.settings.resolved_chroma_dir).delete_document(document.id)
        path = Path(document.file_path).resolve()
        upload_root = self.settings.resolved_upload_dir.resolve()
        if path.is_relative_to(upload_root):
            path.unlink(missing_ok=True)
        self.audit.record(db, "DELETE_DOCUMENT", user_id, "document", str(document.id))
        db.delete(document)
        db.commit()
