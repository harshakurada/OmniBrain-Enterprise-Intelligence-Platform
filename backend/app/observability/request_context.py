import contextvars
import uuid
from typing import Optional

_request_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def new_request_id() -> str:
    """Generates a fresh request id."""
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: Optional[str] = None) -> str:
    """Sets the current request id in context, generating one if omitted.
    Returns the id that was set.
    """
    resolved = request_id or new_request_id()
    _request_id_ctx_var.set(resolved)
    return resolved


def get_request_id() -> str:
    """Returns the current request id, or '-' if none has been set."""
    return _request_id_ctx_var.get()
