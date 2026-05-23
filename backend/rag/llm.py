"""
LLM client — wraps Groq and Gemini APIs behind a single `complete()` call.
Provider is set via LLM_PROVIDER env var ("groq" or "gemini").
"""
import logging
from backend.config import (
    LLM_PROVIDER, GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
)

logger = logging.getLogger(__name__)


def complete(prompt: str, max_tokens: int = 1024, system: str = "") -> str:
    if LLM_PROVIDER == "gemini":
        return _gemini(prompt, max_tokens, system)
    return _groq(prompt, max_tokens, system)


def _groq(prompt: str, max_tokens: int, system: str) -> str:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def _gemini(prompt: str, max_tokens: int, system: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=system or None,
    )
    response = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": max_tokens, "temperature": 0.1},
    )
    return response.text.strip()
