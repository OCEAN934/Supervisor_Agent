# hacker_news_tool.py

import asyncio
import httpx
from pydantic import BaseModel, HttpUrl
from typing import List
from pydantic_ai import Tool
from datetime import datetime, timezone
from dotenv import load_dotenv
from rapidfuzz import fuzz
import re

load_dotenv()

# INPUT schema
class HNScrapeInput(BaseModel):
    company: str

# OUTPUT schema for each article
class HackerNewsArticle(BaseModel):
    id: str
    author: str
    url: HttpUrl
    created_at: str
    num_comments: int
    title: str

# TOOL output schema
class HNScrapeOutput(BaseModel):
    hn_articles: List[HackerNewsArticle]

# Helper: require company name to be a full phrase match in title
def company_name_in_title(company: str, title: str) -> bool:
    pattern = re.compile(rf'\b{re.escape(company)}\b', re.IGNORECASE)
    return bool(pattern.search(title))

# ✅ Raw logic exposed for testing/debugging
async def hn_scrape_logic(input: HNScrapeInput) -> HNScrapeOutput:
    company = input.company.strip()
    url = f"https://hn.algolia.com/api/v1/search?query={company}&tags=story"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        print(f"❌ Error fetching Hacker News data for {company}: {e}")
        return HNScrapeOutput(hn_articles=[])

    hits = data.get("hits", [])
    articles = []
    fuzzy_threshold = 70  # more permissive

    for post in hits:
        try:
            title = post.get("title") or post.get("story_title") or ""
            if not title:
                continue

            fuzzy_score = fuzz.token_set_ratio(company.lower(), title.lower())
            if fuzzy_score < fuzzy_threshold:
                continue

            if not company_name_in_title(company, title):
                continue

            articles.append(HackerNewsArticle(
                id=post.get("objectID", ""),
                author=post.get("author", ""),
                url=post.get("url") or f"https://news.ycombinator.com/item?id={post.get('objectID', '')}",
                created_at=post.get("created_at", ""),
                num_comments=post.get("num_comments", 0),
                title=title
            ))
        except Exception as parse_err:
            print(f"⚠️ Skipping malformed post: {parse_err}")
            continue

    return HNScrapeOutput(hn_articles=articles)

# ✅ Tool-wrapped version used by the agent
@Tool
async def hn_scrape_tool(input: HNScrapeInput) -> HNScrapeOutput:
    """Searches Hacker News for articles mentioning a given company."""
    return await hn_scrape_logic(input)
