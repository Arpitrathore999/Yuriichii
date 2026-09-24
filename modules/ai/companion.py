from groq import AsyncGroq
import config
from database.ai_history import get_history, save_exchange
from modules.ai.prompts import SYSTEM_PROMPT

_client = AsyncGroq(api_key=config.GROQ_API_KEY) if config.GROQ_API_KEY else None

async def chat(user_id: int, text: str) -> str:
    if not _client:
        return "⚠️ GROQ_API_KEY configured nahi hai."

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
        answer = (result.choices[0].message.content or "").strip()
        if not answer:
            return "😵 Elara ko reply nahi mila. Dobara try kar."
        await save_exchange(user_id, text, answer)
        return answer
    except Exception as e:
        # Print the real API/database error in deployment logs instead of
        # hiding every failure behind the same message.
        print(f"[AI ERROR] {type(e).__name__}: {e}", flush=True)
        return "😭 Elara ka brain thoda loading mein hai... dobara try kar."
