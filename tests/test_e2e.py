from schemas import SiteMetadata
from services.crawler import crawl_site
from services.extractor import extract_page_metadata, fetch_html
from services.generator import generate_llms_txt

BASE_URL = "https://eurovisionworld.com"

# 1) Crawl a small set of pages from the seed URL.
urls = crawl_site(BASE_URL, max_depth=5, max_pages=60)
assert urls, "Crawler returned no URLs."

# 2) Fetch + extract metadata for each crawled page.
pages = []
for url in urls:
    html = fetch_html(url)
    pages.append(extract_page_metadata(url, html))

# 3) Generate final llms.txt Markdown.
site = SiteMetadata(
    site_url=BASE_URL,
    site_title="Eurovision World",
    summary="Latest Eurovision news, participants, songs, and results.",
    sections=[],
)
llms_txt = generate_llms_txt(pages, site)

# Basic end-to-end assertions.
assert llms_txt.startswith("# Eurovision World")
assert "## " in llms_txt
assert "- [" in llms_txt

print(llms_txt)
