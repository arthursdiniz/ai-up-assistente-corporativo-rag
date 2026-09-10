import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chats import router as chats_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.users import router as users_router
from app.api.organizations import router as organizations_router
from app.core.config import get_settings
from app.core.cors import configure_cors
from app.core.errors import error_payload, http_error_handler, validation_error_handler


settings = get_settings()
logger = logging.getLogger("ai_up")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.resolved_upload_dir.mkdir(parents=True, exist_ok=True)
    settings.resolved_chroma_dir.mkdir(parents=True, exist_ok=True)
    from sqlalchemy import select
    from app.db.session import SessionLocal
    from app.models.document import Document, DocumentStatus
    from app.models.generation import Generation
    from app.services.generation_service import shutdown
    with SessionLocal() as db:
        for job in db.scalars(select(Generation).where(Generation.status.in_(["queued", "running"]))):
            job.status, job.stage, job.error = "error", "Execução interrompida", "O aplicativo foi reiniciado. Envie a pergunta novamente."
        for document in db.scalars(select(Document).where(Document.status.in_([DocumentStatus.UPLOADED, DocumentStatus.PROCESSING]))):
            document.status = DocumentStatus.READY if document.index_generation else DocumentStatus.ERROR
            document.processing_stage = "Processamento interrompido"
            document.error_message = "O aplicativo foi reiniciado. Use Reprocessar para continuar."
        db.commit()
    yield
    shutdown()


app = FastAPI(
    title=settings.app_name,
    description="Assistente corporativo local com RAG e fontes verificáveis.",
    version="0.1.0",
    lifespan=lifespan,
)
configure_cors(app, settings)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request.state.request_id = uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Erro não tratado em %s (%s), request_id=%s",
        request.url.path,
        type(exc).__name__,
        request.state.request_id,
    )
    return JSONResponse(
        status_code=500,
        content=error_payload(
            request,
            status_code=500,
            message="Erro interno do servidor.",
        ),
        headers={
            "X-Request-ID": request.state.request_id,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Cache-Control": "no-store",
        },
    )


app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(chats_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(organizations_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
