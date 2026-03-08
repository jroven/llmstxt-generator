# test_generator.py

from schemas import PageMetadata, SectionMetadata, SiteMetadata
from services.generator import generate_llms_txt

site = SiteMetadata(
    site_url="https://example.com",
    site_title="Example Site",
    summary="Example site used to test llms.txt generation.",
    sections=[
        SectionMetadata(heading="Docs", page_urls=["/docs", "/guide"]),
        SectionMetadata(heading="Blog", page_urls=["/blog"]),
        SectionMetadata(heading="About", page_urls=["/about"]),
    ],
)

pages = [
    PageMetadata(
        url="https://example.com/docs/getting-started",
        title="Getting Started",
        description="Introduction to the documentation.",
    ),
    PageMetadata(
        url="https://example.com/blog/launch",
        title="Launch Post",
        description="Announcing the launch.",
    ),
    PageMetadata(
        url="https://example.com/about",
        title="About",
        description="About the project.",
    ),
]

print(generate_llms_txt(pages, site))