# app/services/openai_service.py
import logging
from typing import Any, Dict, List, Optional
from functools import lru_cache
from openai import OpenAI

from config import settings


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    """
    Singleton-style OpenAI client so we don't recreate it everywhere.
    """
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def run_text_analysis(
    *,
    system_prompt: str,
    user_payload: Dict[str, Any],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Generic helper for calling a chat/completions model and returning raw content string.

    - system_prompt: instructions for the assistant
    - user_payload: arbitrary dict sent as the user message (we JSON-encode it)
    - model: override model if needed; otherwise uses default from settings
    - temperature: override temperature if needed
    """
    client = get_openai_client()

    m = model or settings.OPENAI_TEXT_MODEL
    t = settings.OPENAI_TEMPERATURE if temperature is None else temperature

    import json

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload)},
    ]

    completion = client.chat.completions.create(
        model=m,
        messages=messages,
        temperature=t,
    )

    return completion.choices[0].message.content or ""
