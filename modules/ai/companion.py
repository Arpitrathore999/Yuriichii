from groq import AsyncGroq
import config
from database.ai_history import get_history, save_exchange
from modules.ai.prompts import SYSTEM_PROMPT

_client = AsyncGroq(api_key=config.GROQ_API_KEY) if config.GROQ_API_KEY else None

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
            temperature=0.8,
        )
        answer = (result.choices[0].message.content or "").strip()
        if not answer:
            return "I'm here 😭 What happened?"
        await save_exchange(user_id, text, answer)
        return answer
    except Exception as e:
        print(f"[AI ERROR] {type(e).__name__}: {e}", flush=True)
        return "⚠️ AI is temporarily unavailable. Please try again in a moment."
