from groq import AsyncGroq
import config
from database.ai_history import get_history, save_exchange
from modules.ai.prompts import SYSTEM_PROMPT

_client = AsyncGroq(api_key=config.GROQ_API_KEY) if config.GROQ_API_KEY else None

# Current Groq production fallback. The old llama-3.3-70b-versatile ID can be unavailable
# for some projects/tiers after its deprecation on August 16, 2026.
FALLBACK_MODEL = "openai/gpt-oss-120b"

async def chat(user_id: int, text: str) -> str:
    if not _client:
        return "⚠️ GROQ_API_KEY is not configured."

    history = await get_history(user_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": text},
    ]

    try:
        result = await _client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages,
            max_tokens=220,
            temperature=0.9,
        )
    except Exception as first_error:
        # If the configured model was retired/unavailable, retry once with a current model.
        model_name = str(config.GROQ_MODEL or "")
        if model_name != FALLBACK_MODEL and any(
            word in str(first_error).lower()
            for word in ("model", "not found", "unavailable", "decommissioned", "deprecated")
        ):
            try:
                result = await _client.chat.completions.create(
                    model=FALLBACK_MODEL,
                    messages=messages,
                    max_tokens=220,
                    temperature=0.9,
                )
            except Exception:
                return "⚠️ The AI model is unavailable right now. Please check your GROQ_MODEL setting."
        else:
            return "⚠️ Elara couldn't process your message right now. Please try again."

    answer = (result.choices[0].message.content or "").strip()
    if not answer:
        return "⚠️ Elara returned an empty response. Please try again."
    await save_exchange(user_id, text, answer)
    return answer
