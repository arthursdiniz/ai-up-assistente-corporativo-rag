"""Extract only rules with a literal span in the already extracted document."""
from datetime import date
from decimal import Decimal
import re
import unicodedata

from app.schemas.auditor import CorporateRule, RuleEvidence, RuleType


EXTRACTOR_VERSION = "pt-rules-1"
MAX_RULES = 80
MAX_CHARS = 180_000
MONEY = re.compile(r"R\$\s*(-?\d+(?:\.\d{3})*(?:,\d{1,2})?)(?!\d|[.,]\d)", re.I)
DEADLINE = re.compile(r"\b(\d+)\s*(dias?|horas?|meses|mês)\b(?:\s+(úteis|corridos?|corridas?))?", re.I)
PERCENT = re.compile(r"(?<!\w)(-?\d+(?:[,.]\d+)?)\s*%")
DATE = r"(?:\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})"
POLICY = re.compile(r"\b[A-Z]{2,12}-\d+[A-Z0-9-]*\b")
FIELDS = {
    "assunto": "subject", "departamento": "department", "setor": "department",
    "publico": "audience", "categoria": "audience", "responsavel": "responsible",
    "condicao": "condition", "excecao": "exception", "politica": "policy_id", "norma": "policy_id",
}


def normalize(value):
    if not value:
        return ""
    plain = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def decimal_text(raw):
    return format(Decimal(raw).normalize(), "f")


def parse_date(raw):
    try:
        if "/" not in raw:
            return date.fromisoformat(raw)
        day, month, year = map(int, raw.split("/"))
        return date(year, month, day)
    except ValueError:
        return None


def validity(text):
    pattern = rf"(?:vig[eê]ncia|vigora|vigente|v[aá]lid[ao])\s*(?::|de|a partir de)?\s*({DATE})?\s*(?:(?:a|at[eé])\s*({DATE}))?"
    match = re.search(pattern, text, re.I)
    if not match:
        return None, None, False
    raw_start, raw_end = match.groups()
    start = parse_date(raw_start) if raw_start else None
    end = parse_date(raw_end) if raw_end else None
    invalid = bool((raw_start and not start) or (raw_end and not end) or (start and end and start > end))
    return (None, None, True) if invalid else (start, end, False)


def fields(block):
    result = {}
    for match in re.finditer(r"(?:^|[\n;])\s*([\wçãéú]+):[ \t]*([^\n;]{1,240})", block, re.I):
        name = FIELDS.get(normalize(match[1]))
        if name and name not in result:
            result[name] = match[2].strip(" .")
    return result


def extract_rules(document_id, version, sections):
    rules = []
    scanned = 0
    for section_index, section in enumerate(sections):
        text = section.get("text", "")
        for match in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", text):
            block = match[0].rstrip()
            scanned += len(block)
            if scanned > MAX_CHARS or len(rules) >= MAX_RULES:
                return rules[:MAX_RULES], True
            defaults = fields(block) if len(block) <= 1800 else {}
            block_validity = validity(block) if len(block) <= 1800 else (None, None, False)
            sentences = re.finditer(r"[^\n]+?(?=\.(?:\s+[A-ZÁÉÍÓÚÇ]|\s*$)|$|\n)", block, re.M)
            for sentence_match in sentences:
                sentence = sentence_match[0].strip().lstrip(". ")
                if not sentence or len(sentence) > 1600:
                    continue
                label = normalize(sentence.split(":", 1)[0]) if ":" in sentence else ""
                if label in FIELDS:
                    continue
                extracted = classify(sentence)
                if not extracted:
                    continue
                start, end, invalid = validity(sentence)
                if not (start or end or invalid):
                    start, end, invalid = block_validity
                meta = dict(defaults)
                for key, pattern in {
                    "exception": r"\b(?:exceto|salvo|exceção)\s+([^.;\n]{1,180})",
                    "condition": r"\b(?:desde que|somente se|quando)\s+([^.;\n]{1,180})",
                    "department": r"\b(?:departamento|setor|equipe)\s+(?:de\s+)?([^,.;:\n]{1,80}?)(?=\s+(?:deve|tem|pode|é)|[,.;:]|$)",
                    "audience": r"\bpara\s+(estagiários|terceirizados|efetivos|temporários|aprendizes|gestores)\b",
                    "responsible": r"\b(?:aprovado|validado|assinado)\s+por\s+([^,.;\n]{1,80})",
                }.items():
                    found = re.search(pattern, sentence, re.I)
                    if found:
                        meta[key] = found[1].strip()
                code = POLICY.search(sentence)
                if code and "policy_id" not in meta:
                    meta["policy_id"] = code[0]
                kind, value, unit, subject = extracted
                if not subject and kind == RuleType.VALIDITY:
                    subject = "Vigência da norma"
                if not subject and not meta.get("subject"):
                    continue
                target = subject[:240] if subject else None
                subject = meta.pop("subject", None) or subject
                constraint = None
                if value is not None:
                    normalized = normalize(sentence)
                    constraint = "minimum" if re.search(r"\b(?:minimo|minima|pelo menos)\b", normalized) else (
                        "maximum" if re.search(r"\b(?:limite|teto|maximo|maxima|ate)\b", normalized) else "exact")
                uncertainty = []
                if invalid:
                    uncertainty.append("Vigência inválida ou invertida no texto")
                elif not start and not end:
                    uncertainty.append("Vigência não localizada")
                if not meta.get("department") and not meta.get("audience"):
                    uncertainty.append("Público ou departamento não localizado")
                if unit in {"dia", "hora", "mes"}:
                    uncertainty.append("Prazo sem indicação de dias úteis ou corridos")
                # Include the contiguous qualifiers when the rule inherits them from the block.
                inherited = bool(defaults or any(block_validity)) and len(block) <= 1800
                excerpt = block if inherited else sentence
                offset = match.start() if inherited else match.start() + block.index(sentence, sentence_match.start())
                evidence = RuleEvidence(document_id=document_id, version=version, section_index=section_index,
                    page=section.get("page"), sheet=section.get("sheet"), location=section.get("location"),
                    start=offset, end=offset + len(excerpt), excerpt=excerpt)
                rules.append(CorporateRule(kind=kind, subject=subject[:240], target=target, action=sentence[:400], value=value,
                                           unit=unit, constraint=constraint, valid_from=start, valid_until=end, uncertainty=uncertainty,
                                           evidence=evidence, **meta))
                if len(rules) >= MAX_RULES:
                    return rules, True
    return rules, False


def classify(sentence):
    start, end, invalid = validity(sentence)
    if re.match(r"^\s*(?:vig[eê]ncia|v[aá]lid[ao]|vigora|vigente)\b", sentence, re.I) and (start or end or invalid):
        return RuleType.VALIDITY, None, None, ""
    for kind, pattern in ((RuleType.FINANCIAL_LIMIT, MONEY), (RuleType.DEADLINE, DEADLINE), (RuleType.PERCENTAGE, PERCENT)):
        match = pattern.search(sentence)
        if not match:
            continue
        normalized = normalize(sentence)
        cues = {
            RuleType.FINANCIAL_LIMIT: r"\b(?:limite|teto|maximo|minimo|valor|reembolso|pagamento|multa|ate|custa)\b",
            RuleType.DEADLINE: r"\b(?:prazo|entrega|resposta|antecedencia|deve|vencimento|ate|em)\b",
            RuleType.PERCENTAGE: r"\b(?:percentual|taxa|desconto|multa|percentagem|limite|aliquota|reajuste)\b",
        }
        if not re.search(cues[kind], normalized):
            continue
        raw = match[1]
        if kind == RuleType.FINANCIAL_LIMIT:
            value, unit = decimal_text(raw.replace(".", "").replace(",", ".")), "BRL"
        elif kind == RuleType.PERCENTAGE:
            value, unit = decimal_text(raw.replace(",", ".")), "%"
        else:
            unit = {"d": "dia", "h": "hora", "m": "mes"}[normalize(match[2])[0]]
            qualifier = normalize(match[3])
            if qualifier:
                unit += "_uteis" if qualifier == "uteis" else "_corridos"
            value = decimal_text(raw)
        subject = sentence[:match.start()].strip(" :-–=")
        subject = re.sub(r"\b(?:é|será|de|em|até|para|a|no máximo|no mínimo)\s*$", "", subject, flags=re.I).strip()
        return kind, value, unit, subject
    prohibition = re.search(r"\b(?:é\s+proibido|é\s+vedado|não\s+(?:deve|pode)|proíbe)\s+(.+)", sentence, re.I)
    obligation = re.search(r"\b(?:é\s+obrigatório|deve[m]?|obriga)\s+(.+)", sentence, re.I)
    if prohibition:
        return RuleType.PROHIBITION, None, None, prohibition[1]
    if obligation:
        return RuleType.OBLIGATION, None, None, obligation[1]
    return None
