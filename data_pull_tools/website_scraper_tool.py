import os
os.environ["OLLAMA_HOST"] = "http://localhost:11434"

import json
import asyncio
import httpx
from typing import List
from urllib.parse import urlparse, urljoin
from collections import deque
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl
from pydantic_ai import Tool

load_dotenv()

# ----------------------------
# Pydantic Models
# ----------------------------
class ScraperInput(BaseModel):
    url: HttpUrl
    max_pages: int = 5

class ScraperOutput(BaseModel):
    text_content: str
    links: List[HttpUrl]
    summary_text: str

class WebsiteContent(BaseModel):
    url: str
    company_name: str
    text_content: List[str]
    links: List[str]

# ----------------------------
# Scraper Logic
# ----------------------------
class CompanyWebsiteScraper:
    def __init__(self):
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--log-level=3")

    def _extract_domain_as_company(self, url: str) -> str:
        hostname = urlparse(url).hostname or ""
        parts = hostname.replace("www.", "").split(".")
        return parts[0] if parts else "unknown"

    def extract_website_content(self, url: str) -> WebsiteContent:
        driver = webdriver.Chrome(service=Service(), options=self.options)
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        try:
            container = driver.find_element(By.TAG_NAME, "main")
        except:
            container = driver.find_element(By.TAG_NAME, "body")

        all_elements = container.find_elements(By.XPATH, ".//*")
        unique_texts = set()
        visible_texts = []

        for elem in all_elements:
          try:
            if elem.is_displayed():
               text = elem.text.strip()
               if text and text not in unique_texts:
                  visible_texts.append(text)
                  unique_texts.add(text)
          except:
            continue

        all_links = driver.find_elements(By.TAG_NAME, 'a')
        links = {
            a.get_attribute('href')
            for a in all_links
            if a.get_attribute('href') and a.get_attribute('href').startswith("http")
        }

        driver.quit()

        return WebsiteContent(
            url=url,
            company_name=self._extract_domain_as_company(url),
            text_content=visible_texts,
            links=list(links)
        )

    def crawl_website(self, base_url: str, max_pages: int = 5) -> List[WebsiteContent]:
        visited = set()
        to_visit = deque([base_url])
        scraped_data = []

        while to_visit and len(visited) < max_pages:
            current_url = to_visit.popleft()
            if current_url in visited:
                continue

            try:
                print(f"🌐 Scraping: {current_url}")
                content = self.extract_website_content(current_url)
                scraped_data.append(content)
                visited.add(current_url)

                base_domain = urlparse(base_url).netloc
                for link in content.links:
                    if not link:
                        continue
                    parsed = urlparse(link)
                    full_url = link if parsed.netloc else urljoin(base_url, link)
                    if urlparse(full_url).netloc == base_domain and full_url not in visited:
                        to_visit.append(full_url)

            except Exception as e:
                print(f"❌ Error scraping {current_url}: {e}")
                continue

        return scraped_data

# ----------------------------
# Ollama Summary Helper (via HTTP)
# ----------------------------
def summarize_texts_ollama(scraped_data: List[WebsiteContent]) -> str:
    combined_text = "\n".join(" ".join(page.text_content) for page in scraped_data)[:12000]

    prompt = f"""
You are a company analyst. Carefully analyze the extracted content from a company’s website and write a clear, multi-line summary including:

1. What the company does and its target market
2. Its key products, categories, or services
3. Any mention of values, sustainability, certifications, or mission
4. Notable features about distribution, partnerships, or innovation

Ensure the summary is at least 5-7 lines long and coherent.
Avoid bullets. Just write a structured paragraph.

Text:
{combined_text}
"""

    try:
        response = httpx.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        result = response.json()
        return result["message"]["content"].strip()
    except Exception as e:
        print("⚠️ Ollama HTTP error:", e)
        return "Summary generation failed."

# ----------------------------
# Tool Entrypoint
# ----------------------------
@Tool
async def scrape_company_website(input_data: ScraperInput) -> ScraperOutput:
    """Scrapes a company's website and returns a structured summary with links."""
    scraper = CompanyWebsiteScraper()
    pages = scraper.crawl_website(str(input_data.url), input_data.max_pages)
    summary = summarize_texts_ollama(pages)

    links: List[HttpUrl] = []
    for p in pages:
        for l in p.links:
            try:
                links.append(HttpUrl(l))
            except:
                continue

    return ScraperOutput(
        text_content="\n".join(" ".join(p.text_content) for p in pages),
        links=links,
        summary_text=summary
    )
