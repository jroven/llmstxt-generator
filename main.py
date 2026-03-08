"""ASGI entrypoint for the llms.txt generator application."""

from __future__ import annotations

from api.app import app
from services.pipeline import is_connection_failure as _is_connection_failure
from services.pipeline import run_generation as _run_generation
from services.pipeline import run_generation_for_url as _run_generation_for_url

__all__ = ["app", "_is_connection_failure", "_run_generation", "_run_generation_for_url"]

