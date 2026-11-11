"""Apply current permissions to stored evidence without changing retention."""
from sqlalchemy import select

from app.models.document import Document
from app.models.user import User
from app.services.document_access_service import DocumentAccessService


CONTEXT_IDS = "_context_document_ids"
OWNED_CONTEXT_IDS = "_owned_context_document_ids"
RESTRICTED_ANSWER = "Resposta indisponível porque o acesso a uma fonte foi revogado."


def message_dependencies(message):
    return set((message.metrics or {}).get(CONTEXT_IDS, [])) | {
        source.document_id for source in message.sources if source.document_id is not None
    }


def _document_permissions(db, user, ids):
    if not ids:
        return {}
    user = db.get(User, user.id, populate_existing=True)
    if not user or not user.active:
        return dict.fromkeys(ids, False)
    return dict(db.execute(select(Document.id, DocumentAccessService.accessible_clause(user))
                           .where(Document.id.in_(ids))).all())


def denied_documents(db, user, ids, *, required_ids=()):
    permissions = _document_permissions(db, user, ids)
    return {key for key, allowed in permissions.items() if not allowed} | (set(required_ids) - permissions.keys())


def blocked_messages(db, user, messages):
    dependencies = {message.id: message_dependencies(message) for message in messages}
    permissions = _document_permissions(db, user, set().union(*dependencies.values()))
    blocked = set()
    for message in messages:
        ids = dependencies[message.id]
        owned = (message.metrics or {}).get(OWNED_CONTEXT_IDS)
        # Older snapshots have no reliable distinction between own and shared
        # deleted documents. Keep their retention behavior until a policy is approved.
        required = ids - set(owned) if owned is not None else set()
        if any(not permissions.get(key, key not in required) for key in ids):
            blocked.add(message.id)
    return blocked


def public_metrics(metrics):
    if metrics is None:
        return None
    return {key: value for key, value in metrics.items() if key not in (CONTEXT_IDS, OWNED_CONTEXT_IDS)}
