from .website_scraper_tool import scrape_company_website
from .youtube_scraper_tool import generate_product_summary

# 🧼 Patch around HN tool to avoid db_utils import error
try:
    from .hacker_news_tool import hn_scrape_tool
except ImportError:
    print("⚠️ Skipping hn_scrape_tool import due to db_utils dependency")
    hn_scrape_tool = None

__all__ = ["scrape_company_website", "generate_product_summary", "hn_scrape_tool"]
