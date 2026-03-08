
from services.crawler import crawl_site
print(crawl_site("https://eurovisionworld.com/", max_depth=2, max_pages=50))
