from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


ERROR_CODES = {
    400: "INVALID_REQUEST",
    401: "AUTHENTICATION_REQUIRED",
    403: "ACCESS_DENIED",
    404: "RESOURCE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "RESOURCE_CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "SERVER_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unavailable")


def error_payload(
    request: Request,
    *,
    status_code: int,
    message: str,
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": ERROR_CODES.get(status_code, "HTTP_ERROR"),
        "message": message,
        # Mantido para compatibilidade com os clientes da versão acadêmica.
        "detail": message,
        "request_id": request_id(request),
    }
    if errors:
        payload["errors"] = errors
    return payload


async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "A requisição não pôde ser concluída."
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(
            error_payload(request, status_code=exc.status_code, message=message)
        ),
        headers=exc.headers,
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_payload(
            request,
            status_code=422,
            message="Os dados enviados são inválidos.",
            errors=errors,
        ),
    )
