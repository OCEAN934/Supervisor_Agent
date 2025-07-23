import sys
import os
import json
import asyncio
import httpx
from typing import List
from dotenv import load_dotenv
from pydantic_models import CompanyScrapedData, PiggyBank
from access import WebsiteExtractor
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_pull_tools.website_scraper_tool import scrape_company_website
from data_pull_tools.hacker_news_tool import hn_scrape_tool
from data_pull_tools.youtube_scraper_tool import generate_product_summary
from prompts import system_message

# ✅ Load environment variables
load_dotenv()

# ------------------------------
# PROMPT BUILDER
# ------------------------------
def generate_llama_prompt(chat_data, company_data) -> str:
    session = chat_data[0] if chat_data else {}
    messages = session.get("messages", [])

    chat_text = ""
    for msg in messages:
        role = msg.get("role", "")
        question = msg.get("question", "")
        answer = msg.get("answer", "")
        if role == "user" and answer:
            chat_text += f"User: {answer}\n"
        elif role == "assistant" and question:
            chat_text += f"Assistant: {question}\n"

    companies = company_data[0].get("companies", [])
    formatted = [f"{c['name']} - {c.get('website', '')}" for c in companies]

    return (
        f"User chat history:\n{chat_text}\n\n"
        f"Companies:\n{chr(10).join(formatted)}\n\n"
        "Return matched company details in strict JSON format per the PiggyBank schema.\n"
        "Each company must include:\n"
        "- name\n"
        "- website\n"
        "- info: { text_content, links, video_summary, hn_articles }\n\n"
        "**Important:** Use all three tools — website scraper, YouTube summary, and Hacker News — for each company. "
        "Do not leave `hn_articles` or `video_summary` empty unless absolutely no content exists after scraping. "
        "Make an effort to query Hacker News by brand name and use any matches."
    )

# ------------------------------
# AGENT ANALYSIS ENTRYPOINT (Ollama direct call)
# ------------------------------
async def analyze_chat_and_scrape(chat_data, company_data) -> List[CompanyScrapedData]:
    prompt = generate_llama_prompt(chat_data, company_data)
    content_chunks = []

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", "http://localhost:11434/api/chat", json={
                "model": "llama3",
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ]
            }) as response:

                print("\n=== Streaming Ollama Response ===")
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                content = data["message"]["content"]
                                content_chunks.append(content)
                                print(content, end="", flush=True)
                        except json.JSONDecodeError:
                            continue

        # Join all content chunks
        full_content = "".join(content_chunks).strip()

        # 💾 Save final structured response to JSON file (for inspection or reuse)
        with open("piggy_bank.json", "w", encoding="utf-8") as f:
            f.write(full_content)

        if not content_chunks:
            raise ValueError("No valid message content found in Ollama stream.")

        # 🧹 Clean codeblock markers
        if full_content.startswith("```json") or full_content.startswith("```"):
            full_content = full_content.strip("`").strip()
            full_content = full_content.replace("json", "").strip()

        # 🧠 Parse final result
        parsed = json.loads(full_content)

        if "companies" not in parsed:
            raise ValueError("Parsed content missing 'companies' field.")

        return PiggyBank(companies=[CompanyScrapedData(**c) for c in parsed["companies"]]).companies

    except Exception as e:
        raise RuntimeError(f"Failed to process Ollama response: {e}")
