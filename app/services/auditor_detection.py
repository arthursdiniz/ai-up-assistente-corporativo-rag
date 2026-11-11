from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from app.schemas.auditor import AlertKind, CorporateRule, RuleType
from app.services.auditor_rules import normalize


DETECTOR_VERSION = "compare-pt-1"
ALIASES = {"teto": "limite", "maximo": "limite", "maxima": "limite", "restituicao": "reembolso",
           "ressarcimento": "reembolso", "ressarcir": "reembolso", "reembolsar": "reembolso",
           "enviar": "entregar", "envio": "entregar", "entrega": "entregar",
           "submeter": "entregar", "prazo": "prazo", "periodo": "prazo"}
STOP = set("a o as os para por com de do da dos das ao em e que no na se sera deve valor limite prazo regra norma maximo minimo".split())


@dataclass(frozen=True)
class Finding:
    kind: AlertKind
    subject: str
    explanation: str
    evidence: tuple[CorporateRule, ...]


def terms(value):
    return {term for raw in normalize(value).split()
            if (term := ALIASES.get(raw, ALIASES.get(raw.rstrip("s"), raw.rstrip("s")))) not in STOP
            and len(term) >= 3 and not term.isdecimal()}


def lexical_similarity(left, right):
    a, b = terms(left.subject), terms(right.subject)
    x, y = terms(left.target), terms(right.target)
    subject = len(a & b) / len(a | b) if a and b else 0.0
    if x and y:
        target = len(x & y) / len(x | y)
        return min(subject, target) if subject else target
    return subject


def similar(left, right, semantic_score):
    if left.policy_id and normalize(left.policy_id) == normalize(right.policy_id) and lexical_similarity(left, right) >= 0.34:
        return 1.0
    lexical = lexical_similarity(left, right)
    if lexical >= 0.8:
        return lexical
    if lexical >= 0.34 and semantic_score >= 0.82:
        return 0.8
    return lexical


def different_scope(left, right):
    for name in ("department", "audience"):
        a, b = normalize(getattr(left, name)), normalize(getattr(right, name))
        if a and b and a != b:
            general = {"todos", "todas", "geral", "toda empresa", "todos os colaboradores"}
            if a not in general and b not in general and not terms(a) & terms(b):
                return True
    # An explicit special case may coexist with a general rule.
    if bool(left.exception) != bool(right.exception):
        return True
    return False


def scope_uncertain(left, right):
    return any(normalize(getattr(left, name)) != normalize(getattr(right, name))
               for name in ("department", "audience", "condition", "exception"))


def overlap(left, right):
    start = max(left.valid_from or date.min, right.valid_from or date.min)
    end = min(left.valid_until or date.max, right.valid_until or date.max)
    return start <= end


def effective(rule, as_of):
    return (not rule.valid_from or rule.valid_from <= as_of) and (not rule.valid_until or rule.valid_until >= as_of)


def comparable(left, right):
    opposing = {left.kind, right.kind} == {RuleType.OBLIGATION, RuleType.PROHIBITION}
    return opposing or left.kind == right.kind


def different_value(left, right):
    if left.kind == RuleType.VALIDITY:
        return (left.valid_from, left.valid_until) != (right.valid_from, right.valid_until)
    if left.kind != right.kind:
        return True
    if left.value is None or right.value is None:
        return False
    if {left.constraint, right.constraint} == {"minimum", "maximum"} and left.unit == right.unit:
        minimum, maximum = (left, right) if left.constraint == "minimum" else (right, left)
        return Decimal(minimum.value) > Decimal(maximum.value)
    return (left.value, left.unit, left.constraint) != (right.value, right.unit, right.constraint)


def describe(rule):
    if rule.value is not None:
        return f"{rule.value} {rule.unit}"
    if rule.kind == RuleType.VALIDITY:
        return f"{rule.valid_from or 'início não identificado'} a {rule.valid_until or 'fim não identificado'}"
    return rule.action


def compare_rules(left, right, as_of, semantic_score=0.0):
    if not comparable(left, right) or different_scope(left, right) or not overlap(left, right):
        return None
    if not effective(left, as_of) or not effective(right, as_of) or not different_value(left, right):
        return None
    if left.kind == RuleType.VALIDITY and not (left.policy_id and normalize(left.policy_id) == normalize(right.policy_id)):
        return None
    confidence = similar(left, right, semantic_score)
    if confidence < 0.5:
        return None
    uncertain = confidence < 0.8 or scope_uncertain(left, right) or any(
        "inválida" in item for rule in (left, right) for item in rule.uncertainty)
    if left.unit != right.unit and left.value is not None and right.value is not None:
        uncertain = True
    if left.kind == RuleType.VALIDITY:
        uncertain = True
    if left.constraint != right.constraint and {left.constraint, right.constraint} != {"minimum", "maximum"}:
        uncertain = True
    explanation = f"Os trechos indicam {describe(left)} e {describe(right)} para assuntos relacionados."
    if uncertain:
        return Finding(AlertKind.NEEDS_CLARIFICATION, left.subject,
                       explanation + " Confirme a equivalência de escopo, unidade, redação e vigência.", (left, right))
    dates_known = any(rule.valid_from or rule.valid_until for rule in (left, right))
    suffix = " As vigências identificadas podem se sobrepor." if dates_known else " A vigência não foi confirmada nos dois documentos."
    return Finding(AlertKind.POSSIBLE_CONTRADICTION, left.subject, explanation + suffix, (left, right))


def outdated(rules, as_of):
    seen = set()
    for rule in rules:
        key = (rule.evidence.section_index, rule.evidence.start, rule.valid_until)
        if rule.valid_until and rule.valid_until < as_of and key not in seen:
            seen.add(key)
            yield Finding(AlertKind.POSSIBLE_OUTDATED, rule.subject,
                          f"O trecho informa vigência até {rule.valid_until:%d/%m/%Y}. Verifique se há norma substituta.", (rule,))


def compare_versions(previous, current):
    matched = set()
    for new in current:
        candidates = []
        for index, old in enumerate(previous):
            if index in matched or not comparable(old, new) or different_scope(old, new):
                continue
            score = lexical_similarity(old, new)
            if score >= 0.34:
                score = max(score, SequenceMatcher(None, normalize(old.target or old.subject), normalize(new.target or new.subject)).ratio())
            if score >= 0.8:
                candidates.append((score, index))
        if not candidates:
            yield Finding(AlertKind.RELEVANT_CHANGE, new.subject,
                          "Regra localizada na versão nova sem equivalente reconhecido na anterior.", (new,))
            continue
        _, index = max(candidates, key=lambda item: (item[0], -item[1]))
        matched.add(index)
        old = previous[index]
        fields = ("kind", "value", "unit", "constraint", "valid_from", "valid_until", "department",
                  "audience", "responsible", "condition", "exception")
        if any(getattr(old, name) != getattr(new, name) for name in fields):
            yield Finding(AlertKind.RELEVANT_CHANGE, new.subject,
                          f"Regra alterada entre versões: {describe(old)} → {describe(new)}. Confira os trechos e qualificadores.", (old, new))
    for index, old in enumerate(previous):
        if index not in matched:
            yield Finding(AlertKind.RELEVANT_CHANGE, old.subject,
                          "Regra da versão anterior sem equivalente reconhecido na nova. Confirme se houve remoção.", (old,))
