"""llms.txt generation service skeleton."""

from __future__ import annotations

from core.constants import DESCRIPTION_MAX_CHARS
from core.errors import AppValidationError
from schemas import PageMetadata, SiteMetadata
from urllib.parse import urlsplit


def _format_page_line(page: PageMetadata) -> str:
    """Format one page entry as Markdown list item."""
    page_url = str(page.url).strip()
    page_title = (page.title or "").strip() or page_url
    page_description = (page.description or "").strip()
    if len(page_description) > DESCRIPTION_MAX_CHARS:
        truncated = page_description[:DESCRIPTION_MAX_CHARS].rstrip()
        last_space = truncated.rfind(" ")
        if last_space > 0:
            truncated = truncated[:last_space].rstrip()
        page_description = truncated + "…"

    line = f"- [{page_title}]({page_url})"
    if page_description:
        line += f": {page_description}"
    return line


def _normalize_url_for_match(url: str) -> str:
    """Normalize URL for section matching and deduplication."""
    parts = urlsplit(url.strip())
    normalized_path = (parts.path or "/").rstrip("/") or "/"
    normalized_query = parts.query
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{normalized_path}{('?' + normalized_query) if normalized_query else ''}"


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

    # Validate pages up front so payload issues fail clearly and early.
    for idx, page in enumerate(pages):
        if not isinstance(page, PageMetadata):
            raise AppValidationError(
                "Invalid page metadata entry.",
                details={"field": "pages", "index": idx},
            )

    # Place each unique page in exactly one inferred section.
    derived_sections: dict[str, list[PageMetadata]] = {}
    assigned_page_urls: set[str] = set()
    for page in pages:
        page_url = str(page.url).strip()
        normalized_page_url = _normalize_url_for_match(page_url)
        if normalized_page_url in assigned_page_urls:
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

    # Render inferred sections in deterministic order.
    sorted_section_names = sorted(
        derived_sections.keys(),
        key=lambda name: (-len(derived_sections[name]), name.lower()),
    )
    for section_name in sorted_section_names:
        markdown_lines.append(f"## {section_name}")
        for page in sorted(
            derived_sections[section_name],
            key=lambda p: ((p.title or "").strip().lower() or str(p.url).strip().lower()),
        ):
            markdown_lines.append(_format_page_line(page))
        markdown_lines.append("")

    return "\n".join(markdown_lines).strip() + "\n"
