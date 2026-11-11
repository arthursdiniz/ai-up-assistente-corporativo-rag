import re


class GenerationGuard:
    _literal = re.compile(r"(?<!\w)[A-Z]{2,}-\d+\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|R\$\s*\d[\d.,]*\d|R\$\s*\d|\b\d+(?:[.,]\d+)?\s*%")

    @classmethod
    def has_unsupported_literal(cls, answer, chunks):
        """Flag exact-literal mismatches in a cited sentence or list line."""
        def literals(text):
            return {re.sub(r"\s+", "", value).casefold() for value in cls._literal.findall(text)}

        by_citation = {chunk.citation: literals(chunk.text) for chunk in chunks}
        for claim in re.split(r"\n+|(?<=[.!?])\s+(?!\[\d+\])", answer):
            refs = [by_citation.get(int(ref), set()) for ref in re.findall(r"\[(\d+)\]", claim)]
            if refs and literals(claim) - set().union(*refs):
                return True
        return False
    @staticmethod
    def preserve_shared_identifiers(answer: str, question: str, context_texts: list[str]) -> str:
        """Preserve the output; never guess a replacement for a factual identifier."""
        return answer

    @staticmethod
    def limit_list_items(answer: str, maximum: int) -> str:
        lines = answer.splitlines()
        kept, count = [], 0
        for line in lines:
            if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line):
                count += 1
                if count > maximum:
                    break
            kept.append(line)
        return "\n".join(kept).rstrip()
