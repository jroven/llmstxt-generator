"""Shared project constants."""

from __future__ import annotations

DEFAULT_MAX_DEPTH = 1
DEFAULT_MAX_PAGES = 20
MAX_PAGES_CAP = 200
MAX_DEPTH_CAP = 5

JOB_POLL_INTERVAL_MS = 300
JOB_RETENTION_SECONDS = 30 * 60
MAX_STORED_JOBS = 200

FETCH_TIMEOUT_SECONDS = 6.0
FETCH_RETRIES = 1
FETCH_MAX_HTML_BYTES = 2_000_000
FETCH_MAX_RETRY_AFTER_SECONDS = 3.0
FETCH_MAX_BACKOFF_SECONDS = 2.0
HTTP_USER_AGENT = "llms-txt-generator/0.1"

DESCRIPTION_MAX_CHARS = 200

# Query params used for pagination-style listing pages.
PAGINATION_QUERY_KEYS = ("page", "p", "offset")

# Crawl-time denylist to reduce auth/account/system URL noise.
CRAWL_DENY_PATH_PREFIXES = ("/auth/", "/account/", "/admin/", "/cms/", "/login", "/register", "/logout")
CRAWL_DENY_QUERY_KEYS = ("next", "redirect", "return_to", "destination")
