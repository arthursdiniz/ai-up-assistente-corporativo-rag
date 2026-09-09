import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    page: int | None
    chunk_index: int
    sheet: str | None = None


class ChunkingService:
    def __init__(self, chunk_size: int, overlap: int) -> None:
        if overlap >= chunk_size:
            raise ValueError("O overlap deve ser menor que o tamanho do chunk.")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, sections: list[dict]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        for section in sections:
            text = self._normalize(section.get("text", ""))
            if not text:
                continue
            start = 0
            while start < len(text):
                tentative_end = min(start + self.chunk_size, len(text))
                end = self._natural_break(text, start, tentative_end)
                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunks.append(
                        TextChunk(
                            text=chunk_text,
                            page=section.get("page"),
                            sheet=section.get("sheet"),
                            chunk_index=len(chunks),
                        )
                    )
                if end >= len(text):
                    break
                start = max(end - self.overlap, start + 1)
        return chunks

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.replace("\x00", " ").replace("\r\n", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _natural_break(text: str, start: int, end: int) -> int:
        if end >= len(text):
            return len(text)
        search_from = start + ((end - start) // 2)
        candidates = [text.rfind(separator, search_from, end) for separator in ("\n", ". ", " ")]
        best = max(candidates)
        return best + 1 if best > start else end
