"""
Token Tracker — calculates token metrics, costs, and cache savings for pipeline runs.
"""
from typing import Any


# DeepSeek API pricing per token
_PRICE_PER_PROMPT_TOKEN = 0.14 / 1_000_000      # $0.14 / 1M input tokens
_PRICE_PER_COMPLETION_TOKEN = 1.10 / 1_000_000  # $1.10 / 1M output tokens

# Estimated average tokens per extraction saved when hit from MongoDB cache
_ESTIMATED_PROMPT_PER_HIT = 500
_ESTIMATED_COMPLETION_PER_HIT = 50


class TokenTracker:
    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.saved_tokens: int = 0

    def add_llm_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += (prompt_tokens + completion_tokens)
        self.cache_misses += 1

    def add_cache_hit(self) -> None:
        self.cache_hits += 1
        self.saved_tokens += (_ESTIMATED_PROMPT_PER_HIT + _ESTIMATED_COMPLETION_PER_HIT)

    @property
    def estimated_cost_usd(self) -> float:
        cost = (
            (self.prompt_tokens * _PRICE_PER_PROMPT_TOKEN)
            + (self.completion_tokens * _PRICE_PER_COMPLETION_TOKEN)
        )
        return round(cost, 6)

    @property
    def estimated_saved_cost_usd(self) -> float:
        saved_prompt = self.cache_hits * _ESTIMATED_PROMPT_PER_HIT
        saved_completion = self.cache_hits * _ESTIMATED_COMPLETION_PER_HIT
        cost = (
            (saved_prompt * _PRICE_PER_PROMPT_TOKEN)
            + (saved_completion * _PRICE_PER_COMPLETION_TOKEN)
        )
        return round(cost, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "saved_tokens": self.saved_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_saved_cost_usd": self.estimated_saved_cost_usd,
        }


__all__ = ["TokenTracker"]
