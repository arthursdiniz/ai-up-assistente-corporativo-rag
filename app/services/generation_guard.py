import re


class GenerationGuard:
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
