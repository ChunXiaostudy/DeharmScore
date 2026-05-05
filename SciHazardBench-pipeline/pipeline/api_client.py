"""异步 API 客户端: 并发控制 / 指数退避重试 / 结构化输出解析"""

import asyncio
import json
import logging
import re
from openai import AsyncOpenAI
from pipeline.config import API_BASE_URL, API_KEY, MODEL, MAX_RETRIES, DEFAULT_CONCURRENCY

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None
_semaphore: asyncio.Semaphore | None = None


def init_client(concurrency: int = DEFAULT_CONCURRENCY):
    global _client, _semaphore
    _client = AsyncOpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    _semaphore = asyncio.Semaphore(concurrency)


async def chat(
    system: str,
    user: str,
    temperature: float = 0.9,
    max_tokens: int = 4096,
    model: str | None = None,
) -> str:
    """单次 chat completion，带信号量 + 指数退避重试"""
    if _client is None:
        init_client()

    use_model = model or MODEL
    for attempt in range(MAX_RETRIES):
        try:
            async with _semaphore:
                resp = await _client.chat.completions.create(
                    model=use_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            wait = 2 ** (attempt + 1)
            logger.warning("API call failed (attempt %d/%d): %s — retry in %ds",
                           attempt + 1, MAX_RETRIES, e, wait)
            await asyncio.sleep(wait)

    logger.error("API call exhausted retries. system=%s... user=%s...",
                 system[:80], user[:80])
    return ""


REFUSAL_SENTINEL = "__REFUSED__"

_REFUSAL_PREFIXES = ("I'm sorry", "I can't", "I cannot", "I apologize", "Sorry,")


async def chat_json(
    system: str,
    user: str,
    temperature: float = 0.9,
    max_tokens: int = 4096,
    model: str | None = None,
) -> list | dict | str:
    """Returns parsed JSON, empty list on error, or REFUSAL_SENTINEL on model refusal."""
    raw = await chat(system, user, temperature, max_tokens, model=model)
    if not raw:
        return []

    if any(raw.startswith(p) for p in _REFUSAL_PREFIXES):
        prompt_preview = user.replace("\n", " ")[:300]
        logger.warning("REFUSED | prompt: %s | response: %s", prompt_preview, raw[:120])
        return REFUSAL_SENTINEL

    m = re.search(r"```(?:json)?\s*\n(.*?)```", raw, re.S)
    text = m.group(1) if m else raw
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("[") or line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        logger.warning("UNPARSEABLE | response: %s", raw[:200])
        return []
