"""FastAPI 统一异常处理器。"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from core.app_exception import AppException, ProtocolError
from core.error_codes import ErrorCodeEnum
from utils.trace_context import get_trace_id, new_trace_id

_ERROR_PROTOCOL: dict[ErrorCodeEnum, tuple[str, str]] = {
    ErrorCodeEnum.E_AUTH001: ("AUTH_FAILED", "auth"),
    ErrorCodeEnum.E_AUTH002: ("AUTH_FAILED", "auth"),
    ErrorCodeEnum.E_AUTH003: ("AUTH_FAILED", "auth"),
    ErrorCodeEnum.E_AUTH004: ("AUTH_FAILED", "auth"),
    ErrorCodeEnum.E_TOOL001: ("TOOL_NOT_FOUND", "validate"),
    ErrorCodeEnum.E_TOOL002: ("INVALID_REQUEST", "validate"),
    ErrorCodeEnum.E_TOOL003: ("TIMEOUT", "probe"),
    ErrorCodeEnum.E_TOOL004: ("TOOL_FAILED", "probe"),
    ErrorCodeEnum.E_TOOL005: ("FORBIDDEN", "validate"),
    ErrorCodeEnum.E_TOOL006: ("FORBIDDEN", "validate"),
    ErrorCodeEnum.E_LLM001: ("INVALID_RESPONSE", "probe"),
    ErrorCodeEnum.E_LLM002: ("INVALID_REQUEST", "validate"),
    ErrorCodeEnum.E_LLM003: ("CONTENT_REJECTED", "validate"),
    ErrorCodeEnum.E_LLM004: ("TIMEOUT", "probe"),
    ErrorCodeEnum.E_LLM005: ("MODEL_NOT_FOUND", "discover"),
    ErrorCodeEnum.E_LLM006: ("AUTH_FAILED", "auth"),
    ErrorCodeEnum.E_LLM007: ("RATE_LIMITED", "probe"),
    ErrorCodeEnum.E_MEM001: ("MEMORY_READ_FAILED", "probe"),
    ErrorCodeEnum.E_MEM002: ("MEMORY_WRITE_FAILED", "probe"),
    ErrorCodeEnum.E_MEM003: ("MEMORY_NOT_FOUND", "validate"),
    ErrorCodeEnum.E_MEM004: ("STORAGE_FULL", "probe"),
    ErrorCodeEnum.E_NET001: ("TIMEOUT", "connect"),
    ErrorCodeEnum.E_NET002: ("CONNECTION_FAILED", "connect"),
    ErrorCodeEnum.E_NET003: ("DNS_FAILED", "dns"),
    ErrorCodeEnum.E_NET004: ("SSRF_BLOCKED", "validate"),
    ErrorCodeEnum.E_CFG001: ("CONFIG_MISSING", "validate"),
    ErrorCodeEnum.E_CFG002: ("CONFIG_INVALID", "validate"),
    ErrorCodeEnum.E_CFG003: ("CONFIG_LOAD_FAILED", "probe"),
    ErrorCodeEnum.E_DB001: ("DATABASE_CONNECTION_FAILED", "connect"),
    ErrorCodeEnum.E_DB002: ("DATABASE_QUERY_FAILED", "probe"),
    ErrorCodeEnum.E_DB003: ("DATABASE_MIGRATION_FAILED", "probe"),
    ErrorCodeEnum.E_DB004: ("DATABASE_WRITE_FAILED", "probe"),
    ErrorCodeEnum.E_RATE001: ("RATE_LIMITED", "validate"),
    ErrorCodeEnum.E_RATE002: ("RATE_LIMITED", "validate"),
    ErrorCodeEnum.E_RATE003: ("RATE_LIMITED", "validate"),
    ErrorCodeEnum.E_SYS001: ("RESOURCE_EXHAUSTED", "probe"),
    ErrorCodeEnum.E_SYS002: ("STORAGE_FULL", "probe"),
    ErrorCodeEnum.E_SYS003: ("INTERNAL_ERROR", "probe"),
    ErrorCodeEnum.E_SYS999: ("INTERNAL_ERROR", "probe"),
}


def _trace_id() -> str:
    return get_trace_id() or new_trace_id()


def build_error_body(
    *,
    code: str,
    message: str,
    stage: str,
    retryable: bool,
    detail: object | None = None,
    error_code: str | None = None,
    details: dict | None = None,
) -> dict:
    legacy_detail = message if detail is None else detail
    return {
        "ok": False,
        "data": None,
        "code": code,
        "message": message,
        "detail": legacy_detail,
        "stage": stage,
        "retryable": retryable,
        "trace_id": _trace_id(),
        "error": {"code": code, "message": message},
        "error_code": error_code or code,
        "details": details or {},
    }


def _from_error_code(error_code: ErrorCodeEnum) -> tuple[str, str]:
    return _ERROR_PROTOCOL.get(error_code, (error_code.code, "probe"))


def _from_http_exception(exc: HTTPException) -> tuple[str, str, bool]:
    detail = str(exc.detail).lower()
    if exc.status_code == 401:
        return "AUTH_FAILED", "auth", False
    if exc.status_code == 429:
        return "RATE_LIMITED", "validate", True
    if exc.status_code in {408, 504}:
        return "TIMEOUT", "connect", True
    if "ssrf" in detail or "安全检查" in detail:
        return "SSRF_BLOCKED", "validate", False
    if "tls" in detail or "ssl" in detail or "证书" in detail:
        return "TLS_FAILED", "tls", False
    if "dns" in detail or "解析" in detail:
        return "DNS_FAILED", "dns", True
    if "模型" in detail or "model" in detail:
        return "MODEL_NOT_FOUND", "discover", False
    if exc.status_code in {502, 503}:
        return "CONNECTION_FAILED", "connect", True
    if exc.status_code == 404:
        return "NOT_FOUND", "validate", False
    return "INVALID_REQUEST", "validate", False


async def _app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """处理 AppException 及其子类"""
    logger.warning(
        "web.app_exception",
        error_code=exc.error_code.code,
        message=exc.message,
        path=request.url.path,
        method=request.method,
    )
    code, stage = _from_error_code(exc.error_code)
    return JSONResponse(
        status_code=exc.error_code.http_status,
        content=build_error_body(
            code=code,
            message=exc.message,
            stage=stage,
            retryable=exc.error_code.retryable,
            error_code=exc.error_code.code,
            details=exc.details,
        ),
    )


async def _protocol_exception_handler(request: Request, exc: ProtocolError) -> JSONResponse:
    logger.warning(
        "web.protocol_exception",
        code=exc.code,
        stage=exc.stage,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=build_error_body(
            code=exc.code,
            message=exc.message,
            stage=exc.stage,
            retryable=exc.retryable,
            details=exc.details,
        ),
    )


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code, stage, retryable = _from_http_exception(exc)
    message = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_body(
            code=code,
            message=message,
            detail=exc.detail,
            stage=stage,
            retryable=retryable,
        ),
        headers=exc.headers,
    )


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [
        {key: value for key, value in item.items() if key != "input"}
        for item in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=build_error_body(
            code="INVALID_REQUEST",
            message="请求参数校验失败",
            detail=detail,
            stage="validate",
            retryable=False,
        ),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底处理所有未捕获异常。"""
    logger.exception(
        "web.unhandled_exception",
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )
    err = ErrorCodeEnum.E_SYS999
    return JSONResponse(
        status_code=err.http_status,
        content=build_error_body(
            code="INTERNAL_ERROR",
            message="内部错误",
            stage="probe",
            retryable=False,
            error_code=err.code,
            details={"exception_type": type(exc).__name__},
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    """向 FastAPI 注册统一异常处理器"""
    app.add_exception_handler(ProtocolError, _protocol_exception_handler)
    app.add_exception_handler(AppException, _app_exception_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    logger.info("web.error_handlers.registered")
