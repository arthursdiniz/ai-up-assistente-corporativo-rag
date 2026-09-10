"""Bounded local jobs with persisted status, replay and cooperative cancellation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event, Lock, RLock
from time import monotonic

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.chat import Chat
from app.models.generation import Generation
from app.models.user import User
from app.services.rag_service import RAGService, GenerationCancelled
from app.services.llm.base import LLMUnavailableError


@dataclass
class RunningGeneration:
    cancel: Event = field(default_factory=Event)
    lock: RLock = field(default_factory=RLock)
    text: str = ""
    committed: bool = False
    created: float = field(default_factory=monotonic)


_states = {}
_state_lock = Lock()
_executor = None


def submit(generation_id):
    global _executor
    with _state_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=get_settings().generation_workers, thread_name_prefix="ai-up")
        for key in list(_states):
            if monotonic() - _states[key].created > 3600:
                _states.pop(key)
        state = _states.setdefault(generation_id, RunningGeneration())
    _executor.submit(run, generation_id, state)


def get_state(generation_id):
    return _states.get(generation_id)


def run(generation_id, state):
    with SessionLocal() as db:
        job = db.get(Generation, generation_id)
        if not job or job.status == "cancelled":
            return
        job.status, job.stage = "running", "Interpretando a pergunta"
        db.commit()
        def emit(kind, value):
            if state.cancel.is_set():
                raise GenerationCancelled()
            if kind == "delta":
                with state.lock:
                    state.text += value
            elif kind == "stage":
                job.stage = value
                db.commit()
        try:
            user = db.get(User, job.user_id)
            chat = db.get(Chat, job.chat_id)
            if not user or not user.active or not chat:
                raise GenerationCancelled()
            service = RAGService(get_settings())
            result = service.ask(db, chat, user, job.question, emit=emit,
                cancelled=state.cancel.is_set, retry_message_id=job.retry_message_id,
                final_lock=state.lock, committed=lambda:setattr(state, "committed", True))
            with state.lock:
                job.status, job.stage = "done", "Concluído"
                job.result = result.model_dump(mode="json")
                db.commit()
        except GenerationCancelled:
            db.rollback()
            job = db.get(Generation, generation_id)
            if job:
                job.status, job.stage = "cancelled", "Cancelado"
                db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Generation, generation_id)
            if job:
                job.status, job.stage = "error", "Não foi possível concluir"
                job.error = str(exc) if isinstance(exc, LLMUnavailableError) else "Não foi possível concluir. Verifique o diagnóstico, reduza o escopo ou tente novamente."
                db.commit()


def shutdown():
    global _executor
    for state in list(_states.values()):
        state.cancel.set()
    if _executor:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
