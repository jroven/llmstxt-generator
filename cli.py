"""Simple CLI for generating llms.txt from a website URL."""

from __future__ import annotations

import argparse
import sys

from core.errors import AppError, CrawlError
from core.url_input import build_url_attempts
from main import _is_connection_failure, _run_generation_for_url


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate llms.txt from a website.")
    parser.add_argument("url", help="Website URL or domain (e.g., example.com)")
    parser.add_argument("--max-depth", type=int, default=1, dest="max_depth")
    parser.add_argument("--max-pages", type=int, default=20, dest="max_pages")
    parser.add_argument("--output", type=str, default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        attempts, display_input, has_explicit_scheme = build_url_attempts(args.url)
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    last_error: CrawlError | None = None
    for attempt_index, attempt_url in enumerate(attempts):
        try:
            llms_txt, discovered_count, processed_count, failed_pages = _run_generation_for_url(
                resolved_url=attempt_url,
                max_depth=args.max_depth,
                max_pages=args.max_pages,
            )
            if args.output:
                with open(args.output, "w", encoding="utf-8") as output_file:
                    output_file.write(llms_txt)
            else:
                print(llms_txt)

            if failed_pages:
                print(
                    f"{len(failed_pages)} pages failed during extraction "
                    f"(discovered: {discovered_count}, processed: {processed_count}):",
                    file=sys.stderr,
                )
                for failed in failed_pages:
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
                and _is_connection_failure(exc)
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
