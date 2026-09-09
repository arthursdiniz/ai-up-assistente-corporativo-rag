import re


class GenerationGuard:
    """Restores exact identifiers that a small local model may mistype."""

    _IDENTIFIER = re.compile(
        r"\b(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+\b",
        re.IGNORECASE,
    )

    @classmethod
    def preserve_shared_identifiers(
        cls,
        answer: str,
        question: str,
        context_texts: list[str],
    ) -> str:
        context = "\n".join(context_texts)
        identifiers = {
            match.group(0)
            for match in cls._IDENTIFIER.finditer(question)
            if re.search(rf"\b{re.escape(match.group(0))}\b", context, re.IGNORECASE)
        }
        corrected = answer
        for identifier in sorted(identifiers, key=len, reverse=True):
            if re.search(rf"\b{re.escape(identifier)}\b", corrected, re.IGNORECASE):
                continue
            prefix = re.escape(identifier.split("-", 1)[0])
            corrected, replacements = re.subn(
                rf"\b{prefix}-[A-Z0-9-]+\b",
                identifier,
                corrected,
                count=1,
                flags=re.IGNORECASE,
            )
            if replacements == 0:
                corrected = f"**{identifier}:** {corrected}"
        return corrected

    @staticmethod
    def limit_list_items(answer: str, maximum: int) -> str:
        """Enforces compact list tasks even when the local model over-generates."""
        lines = answer.splitlines()
        item_count = 0
        kept: list[str] = []
        for line in lines:
            if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line):
                item_count += 1
                if item_count > maximum:
                    break
            kept.append(line)
        return "\n".join(kept).rstrip()
