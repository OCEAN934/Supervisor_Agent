import sys
import os
import json
import httpx
from typing import Tuple
from prompts import system_message
from pydantic_models import PiggyBank
from utils import analyze_chat_and_scrape

# ✅ Add UNGLI directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ✅ Manual Ollama-based response
async def run_llama_agent(prompt: str) -> PiggyBank:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "llama3",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ]
                }
            )
            result = response.json()
            output = json.loads(result["message"]["content"])
            return PiggyBank(**output)
    except Exception as e:
        raise RuntimeError(f"Ollama agent failed: {e}")

# --- Utility: Load Input JSONs ---
def load_inputs(
    chat_path: str = "chatbot_db.chat_sessions.json",
    company_path: str = "companies.json"
) -> Tuple[list, list]:
    with open(chat_path, "r", encoding="utf-8") as f:
        chat_data = json.load(f)
    with open(company_path, "r", encoding="utf-8") as f:
        company_data = json.load(f)
    return chat_data, company_data

# --- Entrypoint for Programmatic Calls ---
async def smart_scrape_companies() -> PiggyBank:
    try:
        chat_data, company_data = load_inputs()
        # 🧠 Get prompt from utils
        from utils import generate_llama_prompt
        prompt = generate_llama_prompt(chat_data, company_data)
        return await run_llama_agent(prompt)
    except FileNotFoundError as fnf:
        raise RuntimeError(f"Missing file: {fnf}")
    except Exception as e:
        raise RuntimeError(f"Internal Error: {str(e)}")
