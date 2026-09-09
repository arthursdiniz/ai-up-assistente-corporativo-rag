from io import BytesIO
from pathlib import Path
import shutil

import pymupdf
from docx import Document as DocxDocument
from openpyxl import load_workbook
from PIL import Image
import pytesseract

from app.core.config import Settings


class ExtractionError(RuntimeError):
    pass


class ExtractionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    def extract(self, path: Path, file_type: str) -> list[dict]:
        handlers = {
            "PDF": self._extract_pdf,
            "TXT": self._extract_txt,
            "DOCX": self._extract_docx,
            "XLSX": self._extract_xlsx,
            "IMAGE": self._extract_image,
        }
        try:
            sections = handlers[file_type](path)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(f"Falha ao extrair {file_type}: {exc}") from exc
        if not any(section.get("text", "").strip() for section in sections):
            raise ExtractionError("Nenhum texto foi encontrado no documento.")
        return sections

    @staticmethod
    def _extract_txt(path: Path) -> list[dict]:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        return [{"text": text, "page": None}]

    def _extract_pdf(self, path: Path) -> list[dict]:
        sections: list[dict] = []
        with pymupdf.open(path) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                text = page.get_text("text").strip()
                if len(text) < 40:
                    text = self._ocr_pdf_page(page)
                sections.append({"text": text, "page": page_number})
        return sections

    def _ocr_pdf_page(self, page: pymupdf.Page) -> str:
        self._ensure_tesseract()
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang="por").strip()

    @staticmethod
    def _extract_docx(path: Path) -> list[dict]:
        document = DocxDocument(path)
        lines = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                values = [cell.text.strip() for cell in row.cells]
                if any(values):
                    lines.append(" | ".join(values))
        return [{"text": "\n".join(lines), "page": None}]

    @staticmethod
    def _extract_xlsx(path: Path) -> list[dict]:
        workbook = load_workbook(path, read_only=True, data_only=True)
        sections: list[dict] = []
        try:
            for sheet in workbook.worksheets:
                rows: list[str] = []
                for row in sheet.iter_rows(values_only=True):
                    values = [str(value).strip() for value in row if value is not None]
                    if values:
                        rows.append(" | ".join(values))
                sections.append({"text": "\n".join(rows), "page": None, "sheet": sheet.title})
        finally:
            workbook.close()
        return sections

    def _extract_image(self, path: Path) -> list[dict]:
        self._ensure_tesseract()
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image, lang="por")
        return [{"text": text, "page": None}]

    def _ensure_tesseract(self) -> None:
        configured = self.settings.tesseract_cmd
        if configured and Path(configured).is_file():
            return
        if shutil.which("tesseract"):
            return
        raise ExtractionError(
            "Tesseract não encontrado. Instale-o ou configure TESSERACT_CMD no arquivo .env."
        )
