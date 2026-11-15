"""Application errors.

Each error carries a stable code for API consumers and a clear message. Messages are in Spanish
because they are returned to the API user, who asks the questions in Spanish. The mapping to HTTP
status codes is done in the API layer (api.py).
"""


class AppError(Exception):
    code = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsafeQueryError(AppError):
    """The SQL is not a single read query over the allowed tables."""

    code = "QUERY_NOT_ALLOWED"


class QueryExecutionError(AppError):
    """The SQL was valid but failed when it ran (for example, a column that does not exist)."""

    code = "QUERY_FAILED"


class QueryTimeoutError(AppError):
    code = "QUERY_TIMEOUT"


class DatabaseUnavailableError(AppError):
    code = "DB_UNAVAILABLE"


class LLMUnavailableError(AppError):
    """The LLM provider cannot be reached, rejects the key or has run out of quota."""

    code = "LLM_UNAVAILABLE"


class LLMTimeoutError(AppError):
    code = "LLM_TIMEOUT"


class LLMInvalidOutputError(AppError):
    """The LLM answered with something unusable: invalid JSON, or a cut-off or blocked answer."""

    code = "LLM_INVALID_OUTPUT"
