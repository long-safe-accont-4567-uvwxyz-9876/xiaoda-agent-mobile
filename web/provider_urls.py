from __future__ import annotations

import re
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from core.app_exception import ProtocolError

_DANGEROUS_ESCAPES = re.compile(r"%(?:00|0a|0d|2f|5c)", re.IGNORECASE)
_SAFE_ENDPOINT = re.compile(r"^[A-Za-z0-9._~-]+$")


def _invalid_url() -> ProtocolError:
    return ProtocolError(
        "base_url 格式无效",
        code="INVALID_REQUEST",
        stage="validate",
        retryable=False,
        http_status=400,
    )


def normalize_provider_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise _invalid_url()
    raw = value.strip()
    if not raw or _DANGEROUS_ESCAPES.search(raw):
        raise _invalid_url()
    decoded = raw
    while True:
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    if any(ord(char) < 32 or ord(char) == 127 for char in decoded) or "\\" in decoded:
        raise _invalid_url()
    decoded_authority = decoded.split("://", 1)[-1].split("/", 1)[0]
    if "@" in decoded_authority:
        raise _invalid_url()
    try:
        parsed = urlsplit(decoded)
        port = parsed.port
    except ValueError as exc:
        raise _invalid_url() from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise _invalid_url()
    if parsed.username is not None or parsed.password is not None:
        raise _invalid_url()
    if parsed.query or parsed.fragment:
        raise _invalid_url()
    if port is not None and port < 1:
        raise _invalid_url()
    hostname = parsed.hostname.lower().rstrip(".")
    if not hostname:
        raise _invalid_url()
    host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{host}:{port}" if port is not None else host
    decoded_path = parsed.path or ""
    if "//" in decoded_path or any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise _invalid_url()
    original = urlsplit(raw)
    path = original.path.rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1"
    normalized = SplitResult(scheme, netloc, path, "", "")
    return urlunsplit(normalized)


def provider_endpoint(base_url: str, endpoint: str) -> str:
    segment = endpoint.strip().lstrip("/")
    if not segment or not _SAFE_ENDPOINT.fullmatch(segment):
        raise _invalid_url()
    return f"{normalize_provider_base_url(base_url)}/{segment}"


def validate_provider_base_url(value: str) -> str:
    from security.safe_outbound import prepare_provider_target

    return prepare_provider_target(value).url
