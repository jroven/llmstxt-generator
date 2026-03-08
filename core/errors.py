"""Shared application exception types and error payload helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppError(Exception):
    """Base app exception with enough metadata for API responses."""

    message: str
    code: str = "app_error"
    http_status: int = 500
    details: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        """Convert exception into a stable API error payload."""
        payload: dict[str, Any] = {"error": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class AppValidationError(AppError):
    """Raised for invalid client input."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "validation_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            http_status=422,
            details=details or {},
        )


class CrawlError(AppError):
    """Raised when crawling cannot proceed for a non-validation reason."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "crawl_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            http_status=502,
            details=details or {},
        )
