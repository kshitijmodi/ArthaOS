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


def complete(prompt: str, max_tokens: int = 1024, system: str = "",
             history: list[dict] | None = None) -> str:
    if LLM_PROVIDER == "gemini":
        return _gemini(prompt, max_tokens, system, history)
    return _groq(prompt, max_tokens, system, history)


def _groq(prompt: str, max_tokens: int, system: str,
          history: list[dict] | None = None) -> str:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    for turn in (history or []):
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def _gemini(prompt: str, max_tokens: int, system: str,
            history: list[dict] | None = None) -> str:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=system or None,
    )
    # Build history for Gemini
    chat_history = []
    for turn in (history or []):
        role = "user" if turn.get("role") == "user" else "model"
        content = turn.get("content", "")
        if content:
            chat_history.append({"role": role, "parts": [content]})
    chat = model.start_chat(history=chat_history)
    response = chat.send_message(
        prompt,
        generation_config={"max_output_tokens": max_tokens, "temperature": 0.1},
    )
    return response.text.strip()
