from collections import deque
from threading import Lock
from time import monotonic
from fastapi import HTTPException
from app.core.config import get_settings

_attempts = {}
_lock = Lock()


def check_login(ip: str, email: str):
    settings = get_settings()
    now = monotonic()
    with _lock:
        for key in list(_attempts):
            while _attempts[key] and now - _attempts[key][0] > settings.login_attempt_window_seconds:
                _attempts[key].popleft()
            if not _attempts[key]:
                del _attempts[key]
        for key, limit in ((ip, settings.login_attempt_limit * 8), ((ip, email), settings.login_attempt_limit)):
            attempts = _attempts.setdefault(key, deque())
            if len(attempts) >= limit or len(_attempts) > 10000:
                raise HTTPException(429, "Muitas tentativas de acesso. Aguarde alguns minutos.", headers={"Retry-After":str(settings.login_attempt_window_seconds)})
        _attempts[ip].append(now)
        _attempts[(ip, email)].append(now)


def login_succeeded(ip, email):
    with _lock:
        _attempts.pop((ip, email), None)
