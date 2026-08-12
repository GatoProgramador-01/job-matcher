"""
DeepSeek LLM factory and pricing constants.
"""
import os
from langchain_openai import ChatOpenAI

# DeepSeek pricing
PRICE_PROMPT = 0.14 / 1_000_000
PRICE_COMPLETION = 1.10 / 1_000_000


def make_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        temperature=0,
    )
