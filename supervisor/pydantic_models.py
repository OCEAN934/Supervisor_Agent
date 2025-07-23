from pydantic import BaseModel, HttpUrl
from typing import List, Optional


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class UserChatHistory(BaseModel):
    session_id: str
    history: List[ChatMessage]


class Company(BaseModel):
    name: str
    website: HttpUrl


class AgentInput(BaseModel):
    chat_data: UserChatHistory
    companies: List[Company]


class HackerNewsArticle(BaseModel):
    id: str
    author: str
    url: HttpUrl
    created_at: str
    num_comments: int
    title: str


class CompanyInfo(BaseModel):
    text_content: str  # summary from website
    links: Optional[List[HttpUrl]] = []
    hn_articles: List[HackerNewsArticle]
    video_summary: Optional[str] = ""


class CompanyScrapedData(BaseModel):
    name: str
    website: HttpUrl
    info: CompanyInfo


class PiggyBank(BaseModel):
    companies: List[CompanyScrapedData]
