from services.http_fetcher import shared_http_fetcher
from services.extractor import extract_page_metadata

url = "https://eurovisionworld.com/esc/san-marino-senhit-will-go-to-eurovision-2026-with-superstar/"

html = shared_http_fetcher.fetch_html(url)

print(extract_page_metadata(url, html))