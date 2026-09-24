import logging
from groq import AsyncGroq
import config
from database.ai_history import get_history, save_exchange
from modules.ai.prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)
_client = AsyncGroq(api_key=config.GROQ_API_KEY) if config.GROQ_API_KEY else None


async def chat(user_id: int, text: str) -> str:
    if not config.GROQ_API_KEY:
        return "⚠️ AI is not configured yet. Please add GROQ_API_KEY to the bot environment."

    try:
        history = await get_history(user_id)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": text},
        ]

        result = await _client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages,
            max_tokens=220,
            temperature=0.9,
        )
        answer = (result.choices[0].message.content or "").strip()
        if not answer:
            return "⚠️ Elara received an empty AI response. Please try again."

        try:
            await save_exchange(user_id, text, answer)
        except Exception:
            log.exception("Failed to save AI history")

        return answer
    except Exception as exc:
        log.exception("Elara AI request failed: %s", exc)
        error = str(exc).lower()
        if "authentication" in error or "api key" in error or "401" in error:
            return "⚠️ Elara AI is unavailable because the Groq API key is invalid or missing."
        if "model" in error and ("not found" in error or "404" in error):
            return f"⚠️ The configured AI model '{config.GROQ_MODEL}' is unavailable."
        if "rate" in error or "429" in error:
            return "⚠️ Elara is temporarily rate-limited by the AI service. Please try again shortly."
        return "⚠️ Elara could not reach the AI service right now. Please try again."
