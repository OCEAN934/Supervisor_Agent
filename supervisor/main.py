import asyncio
from utils import analyze_chat_and_scrape
from pydantic_models import PiggyBank
import json
import logging
logging.getLogger("absl").setLevel(logging.ERROR)


async def main():
    try:
        # Load input files
        with open("chatbot_db.chat_sessions.json", "r", encoding="utf-8") as chat_file:
            chat_data = json.load(chat_file)

        with open("companies.json", "r", encoding="utf-8") as company_file:
            company_data = json.load(company_file)

        # Analyze and scrape
        piggy_bank: PiggyBank = await analyze_chat_and_scrape(
            chat_data=chat_data,
            company_data=company_data
        )

        # Output to terminal
        print("\n\n====== FINAL OUTPUT (PiggyBank) ======\n")
        print(piggy_bank.model_dump_json(indent=2, ensure_ascii=False))

        # ✅ Save clean JSON to file
        with open("piggy_bank.json", "w", encoding="utf-8") as out_file:
            json.dump(piggy_bank.model_dump(), out_file, indent=2, ensure_ascii=False)

    except Exception as e:
        print(f"❌ Error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())
