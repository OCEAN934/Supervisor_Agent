# Updated YouTube scraper to support both 'review' and 'demo/test' videos.
# We'll default to 'review' in the test file.

import os
import re
import json
import asyncio
import httpx
from typing import List
from urllib.parse import urlparse
from pydantic import BaseModel
from pydantic_ai import Tool
from youtubesearchpython import VideosSearch
import yt_dlp

OLLAMA_HOST = "http://localhost:11434"
CHUNK_SIZE = 1000

class ProductInput(BaseModel):
    product_name: str
    focus: str = "review"  # Can be 'review' or 'demo'

class YTDLogger:
    def __init__(self, log_file): self.log_file = log_file
    def debug(self, msg): self._write(msg)
    def warning(self, msg): self._write(msg)
    def error(self, msg): self._write(msg)
    def _write(self, msg): open(self.log_file, 'a', encoding='utf-8').write(msg + '\n')

class VideoProcessor:
    @staticmethod
    def sanitize(name): return re.sub(r'[\\/*?:"<>|]', "", name).strip()

    @staticmethod
    def extract_text_from_vtt(vtt):
        lines = vtt.splitlines()
        return '\n'.join(
            re.sub(r'<[^>]+>', '', line).strip()
            for line in lines
            if line.strip() and '-->' not in line and not line.startswith(('WEBVTT', 'Kind:', 'Language:')) and '[Music]' not in line
        )

    def get_video_urls(self, query, focus, max_results=10):
        # Add "review" or "demo/test" flavor
        if focus == "review":
            full_query = f"{query} customer reviews OR experiences"
        else:
            full_query = f"{query} demo OR test OR walkthrough"

        results = VideosSearch(full_query, limit=max_results).result()['result']

        # For reviews, only include videos with 'review' in title
        if focus == "review":
            results = [r for r in results if "review" in r['title'].lower()]

        return [r['link'] for r in results]

    async def download_and_clean(self, video_url, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(video_url, download=False)
                title = self.sanitize(info.get('title', 'video'))
                base_path = os.path.join(output_dir, title)
                vtt_file = f"{base_path}.en.vtt"
                json_file = f"{base_path}.json"
                log_file = f"{base_path}.log"

            if os.path.exists(json_file):
                return

            ydl_opts = {
                'quiet': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'skip_download': True,
                'subtitleslangs': ['en'],
                'subtitlesformat': 'vtt',
                'outtmpl': base_path + '.%(ext)s',
                'logger': YTDLogger(log_file)
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            if os.path.exists(vtt_file):
                with open(vtt_file, 'r', encoding='utf-8') as f:
                    raw = f.read()
                cleaned = await clean_text_with_ollama(self.extract_text_from_vtt(raw))
            else:
                cleaned = ""

            with open(json_file, 'w', encoding='utf-8') as jf:
                json.dump({
                    "video_title": title,
                    "video_url": video_url,
                    "transcript": cleaned
                }, jf, indent=2, ensure_ascii=False)

            for f in [vtt_file, log_file]:
                if os.path.exists(f):
                    os.remove(f)

        except Exception as e:
            print(f"❌ Download failed: {e}")

class TranscriptSummarizer:
    def __init__(self, transcript_dir, product_name):
        self.dir = transcript_dir
        self.product = product_name.lower()

    def _load_transcripts(self):
        texts = []
        for f in os.listdir(self.dir):
            if f.endswith(".json"):
                with open(os.path.join(self.dir, f), 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                    transcript = data.get("transcript", "")
                    if transcript.strip():
                        texts.append(transcript.strip())
        return "\n\n".join(texts)

    def _chunk_text(self, text):
        return [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]

    async def _summarize_chunk(self, text):
        prompt = (
            f"Summarize the following transcript ONLY focusing on reviews and customer opinions about '{self.product}'. "
            "Extract key feedback, pros, cons, and general sentiment. Ignore unrelated content.\n\n"
            f"{text}"
        )
        try:
            response = httpx.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": "llama3",
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": "You are a market researcher specializing in product sentiment."},
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=None
            )
            return response.json()["message"]["content"].strip()
        except Exception as e:
            print("⚠️ Ollama summary error:", e)
            return ""

    async def summarize(self):
        text = self._load_transcripts()
        if not text:
            return {"summary": "No usable transcripts found."}

        chunks = self._chunk_text(text)
        partials = await asyncio.gather(*[self._summarize_chunk(chunk) for chunk in chunks if chunk.strip()])
        combined = "\n\n".join(partials)
        final = await self._summarize_chunk(combined)

        output_path = os.path.join(self.dir, "combined_summary.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "product_name": self.product,
                "summary": final
            }, f, indent=2, ensure_ascii=False)
        return {"transcripts_cleaned": True, "summary": final}

async def clean_text_with_ollama(raw_text: str) -> str:
    prompt = f"Clean this text by removing repeated or overlapping phrases. Keep only meaningful content:\n\n{raw_text}"
    try:
        response = httpx.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": "llama3",
                "stream": False,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=None
        )
        return response.json()["message"]["content"].strip()
    except Exception as e:
        print("⚠️ Ollama clean-text error:", e)
        return raw_text

async def run_video_processor(product_name: str, focus="review"):
    processor = VideoProcessor()
    base_dir = f"{VideoProcessor.sanitize(product_name)}_{focus}_captions"
    os.makedirs(base_dir, exist_ok=True)

    urls = processor.get_video_urls(product_name, focus=focus, max_results=10)
    await asyncio.gather(*(processor.download_and_clean(url, base_dir) for url in urls))

    summarizer = TranscriptSummarizer(transcript_dir=base_dir, product_name=product_name)
    return await summarizer.summarize()

@Tool
async def generate_product_summary(input: ProductInput):
    """Search YouTube for product demo/review videos, extract transcripts, and summarize key insights."""
    return await run_video_processor(input.product_name, focus=input.focus)
