"""llms.txt generation service skeleton."""

from __future__ import annotations

from urllib.parse import urlsplit

from core.errors import AppValidationError
from schemas import PageMetadata, SiteMetadata


def _is_absolute_http_url(url: str) -> bool:
    """Return True when URL is absolute and uses http/https."""
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _format_page_line(page: PageMetadata) -> str:
    """Format one page entry as Markdown list item."""
    page_url = str(page.url).strip()
    page_title = (page.title or "").strip() or page_url
    page_description = (page.description or "").strip()
    if len(page_description) > 200:
        truncated = page_description[:200].rstrip()
        last_space = truncated.rfind(" ")
        if last_space > 0:
            truncated = truncated[:last_space].rstrip()
        page_description = truncated + "…"

    line = f"- [{page_title}]({page_url})"
    if page_description:
        line += f" — {page_description}"
    return line


def _normalize_url_for_match(url: str) -> str:
    """Normalize URL for section matching and deduplication."""
    parts = urlsplit(url.strip())
    normalized_path = (parts.path or "/").rstrip("/") or "/"
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{normalized_path.lower()}"


def _infer_section_from_url(url: str) -> str:
    """Infer a humanized section name from the first URL path segment."""
    path = urlsplit(url).path.strip("/")
    if not path:
        return "Pages"
    first_segment = path.split("/", 1)[0].strip()
    if not first_segment:
        return "Pages"
    return first_segment.replace("-", " ").title()


def generate_llms_txt(pages: list[PageMetadata], site: SiteMetadata) -> str:
    """
    Build an llms.txt Markdown document from site and page metadata.

    Expected structure (high level):
    - H1 site title
    - Summary blockquote
    - H2 sections
    - Link lists per section

    Args:
        pages: Page-level metadata entries (url, title, description).
        site: Site-level metadata (title, summary, sections).

    Returns:
        A Markdown string in llms.txt format.
    """
    if not isinstance(site, SiteMetadata):
        raise AppValidationError("Invalid site payload.", details={"field": "site"})
    if not isinstance(pages, list):
        raise AppValidationError("Invalid pages payload.", details={"field": "pages"})

    site_url = str(site.site_url).strip()
    if not site_url or not _is_absolute_http_url(site_url):
        raise AppValidationError(
            "site.site_url must be an absolute http(s) URL.",
            details={"field": "site.site_url", "value": site_url},
        )

    # Validate pages up front so payload issues fail clearly and early.
    for idx, page in enumerate(pages):
        if not isinstance(page, PageMetadata):
            raise AppValidationError(
                "Invalid page metadata entry.",
                details={"field": "pages", "index": idx},
            )
        page_url = str(page.url).strip()
        if not page_url or not _is_absolute_http_url(page_url):
            raise AppValidationError(
                "Each page must include an absolute http(s) URL.",
                details={"field": "pages.url", "index": idx, "value": page_url},
            )

    # Build deterministic section containers from configured site sections.
    configured_sections: dict[str, list[PageMetadata]] = {}
    section_lookup_by_url: dict[str, list[str]] = {}
    for idx, section in enumerate(site.sections):
        section_name = (section.heading or "").strip()
        if not section_name:
            raise AppValidationError(
                "Section heading cannot be empty.",
                details={"field": "site.sections.heading", "index": idx},
            )

        configured_sections.setdefault(section_name, [])
        for section_url in section.page_urls:
            section_page_url = str(section_url).strip()
            if not section_page_url:
                continue
            normalized_section_url = _normalize_url_for_match(section_page_url)
            if section_name not in section_lookup_by_url.setdefault(normalized_section_url, []):
                section_lookup_by_url[normalized_section_url].append(section_name)

    # Place each unique page in exactly one section.
    # Priority: configured section match -> URL-derived section.
    derived_sections: dict[str, list[PageMetadata]] = {}
    assigned_page_urls: set[str] = set()
    for page in pages:
        page_url = str(page.url).strip()
        normalized_page_url = _normalize_url_for_match(page_url)
        if normalized_page_url in assigned_page_urls:
            continue

        matched_sections = section_lookup_by_url.get(normalized_page_url, [])
        if matched_sections:
            # Keep configured behavior, but avoid duplicates across sections.
            configured_sections[matched_sections[0]].append(page)
            assigned_page_urls.add(normalized_page_url)
            continue

        inferred_section = _infer_section_from_url(page_url)
        derived_sections.setdefault(inferred_section, []).append(page)
        assigned_page_urls.add(normalized_page_url)

    site_title = (site.site_title or "").strip() or "Site Title"
    site_summary = (site.summary or "").strip() or "Site summary goes here."

    markdown_lines: list[str] = [
        f"# {site_title}",
        "",
        f"> {site_summary}",
        "",
    ]

    # Merge configured and inferred sections and render in deterministic order.
    all_sections: dict[str, list[PageMetadata]] = {}
    for section_name, section_pages in configured_sections.items():
        all_sections.setdefault(section_name, []).extend(section_pages)
    for section_name, section_pages in derived_sections.items():
        all_sections.setdefault(section_name, []).extend(section_pages)

    sorted_section_names = sorted(
        all_sections.keys(),
        key=lambda name: (-len(all_sections[name]), name.lower()),
    )
    for section_name in sorted_section_names:
        markdown_lines.append(f"## {section_name}")
        for page in sorted(
            all_sections[section_name],
            key=lambda p: ((p.title or "").strip().lower() or str(p.url).strip().lower()),
        ):
            markdown_lines.append(_format_page_line(page))
        markdown_lines.append("")

    return "\n".join(markdown_lines).strip() + "\n"
