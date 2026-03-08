"""Simple CLI for generating llms.txt from a website URL."""

from __future__ import annotations

import argparse
import sys

from core.constants import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, MAX_DEPTH_CAP, MAX_PAGES_CAP
from core.errors import AppError, CrawlError
from core.url_input import build_url_attempts
from services.pipeline import is_connection_failure, run_generation_for_url


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate llms.txt from a website.")
    parser.add_argument("url", help="Website URL or domain (e.g., example.com)")
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        choices=range(0, MAX_DEPTH_CAP + 1),
        dest="max_depth",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        choices=range(1, MAX_PAGES_CAP + 1),
        dest="max_pages",
    )
    parser.add_argument("--output", type=str, default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        attempts_info = build_url_attempts(args.url)
        attempts = attempts_info.attempt_urls
        display_input = attempts_info.display_input
        has_explicit_scheme = attempts_info.has_explicit_scheme
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    last_error: CrawlError | None = None
    for attempt_index, attempt_url in enumerate(attempts):
        try:
            run_result = run_generation_for_url(
                resolved_url=attempt_url,
                max_depth=args.max_depth,
                max_pages=args.max_pages,
            )
            if args.output:
                with open(args.output, "w", encoding="utf-8") as output_file:
                    output_file.write(run_result.llms_txt)
            else:
                print(run_result.llms_txt)

            if run_result.failed_pages:
                print(
                    f"{len(run_result.failed_pages)} pages failed during extraction "
                    f"(discovered: {run_result.discovered_count}, processed: {run_result.processed_count}):",
                    file=sys.stderr,
                )
                for failed in run_result.failed_pages:
                    print(
                        f'- {failed["url"]} ({failed["code"]}): {failed["reason"]}',
                        file=sys.stderr,
                    )
            return 0
        except CrawlError as exc:
            last_error = exc
            should_retry_with_http = (
                not has_explicit_scheme
                and attempt_index == 0
                and len(attempts) > 1
                and is_connection_failure(exc)
            )
            if should_retry_with_http:
                print(f"Failed to reach {attempt_url}", file=sys.stderr)
                print(f"Retrying with {attempts[1]}...", file=sys.stderr)
                continue
            print(exc.message, file=sys.stderr)
            return 1
        except AppError as exc:
            print(exc.message, file=sys.stderr)
            return 1

    if last_error is not None:
        print(f"Could not connect to {display_input} using HTTPS or HTTP.", file=sys.stderr)
        return 1

    print("Generation failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
