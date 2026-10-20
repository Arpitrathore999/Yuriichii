# --------------------------------------------------------------------------------
#  Elara © 2026
#  core/quotly.py — 📱 Quote Generation Engine (QuotLy API)
# --------------------------------------------------------------------------------

from __future__ import annotations

import base64
import os
from typing import Optional

import aiohttp

from core.bot import app


# ── API endpoints (fallback chain) ────────────────────────────────────────────
# Public LyoSU quote API. It returns {"image": "<base64>", "type": "quote"}.
# Public instances are best-effort and their uptime is not guaranteed.
QUOTE_APIS = [
    "https://quote.yuri.ly/quote/generate",
]


def _entity_type(e) -> str:
    t = str(e.type).lower()
    for prefix in ("messageentitytype.", "message_entity_type."):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return t


def convert_entities(entities) -> list[dict]:
    """Convert pyrogram entities → QuotLy entity dicts."""
    if not entities:
        return []
    mapping = {
        "bold": "bold",
        "italic": "italic",
        "underline": "underline",
        "strikethrough": "strikethrough",
        "spoiler": "spoiler",
        "code": "code",
        "pre": "pre",
        "blockquote": "blockquote",
        "text_link": "text_link",
        "url": "url",
        "mention": "mention",
        "text_mention": "text_mention",
        "hashtag": "hashtag",
        "cashtag": "cashtag",
        "bot_command": "bot_command",
        "email": "email",
        "phone_number": "phone_number",
    }
    out = []
    for e in entities:
        etype = _entity_type(e)
        qt = mapping.get(etype)
        if not qt:
            continue
        item = {"type": qt, "offset": int(e.offset), "length": int(e.length)}
        if getattr(e, "url", None):
            item["url"] = e.url
        if getattr(e, "user", None):
            u = e.user
            item["user"] = {
                "id": int(u.id),
                "name": u.first_name or "",
                "username": u.username or "",
            }
        out.append(item)
    return out


async def _avatar_data_uri(user_id: int) -> Optional[str]:
    """Download user PFP → base64 data URI. Returns None if no PFP."""
    try:
        async for photo in app.get_chat_photos(user_id, limit=1):
            path = await app.download_media(photo.file_id)
            if not path:
                return None
            try:
                with open(path, "rb") as f:
                    raw = f.read()
            finally:
                try:
                    os.remove(path)
                except Exception:
                    pass
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None
    return None


async def build_message_dict(msg, *, include_reply: bool = False) -> dict:
    """Convert a pyrogram Message → QuotLy message dict."""
    sender = msg.from_user
    name = "Unknown"
    if sender:
        name = sender.first_name or sender.username or str(sender.id)

    avatar_uri = None
    if sender:
        avatar_uri = await _avatar_data_uri(sender.id)

    text = msg.text or msg.caption or ""
    entities = convert_entities(msg.entities or msg.caption_entities)

    from_obj = {
        "id": int(sender.id) if sender else 0,
        "name": name,
        "username": (sender.username if sender else "") or "",
    }
    if avatar_uri:
        from_obj["photo"] = {"url": avatar_uri}

    data = {
        "entities": entities,
        "avatar": bool(avatar_uri),
        "from": from_obj,
        "text": text,
    }

    if include_reply and msg.reply_to_message:
        r = msg.reply_to_message
        rs = r.from_user
        rname = "Unknown"
        if rs:
            rname = rs.first_name or rs.username or str(rs.id)
        rtext = r.text or r.caption or ""
        rdata = {
            "entities": convert_entities(r.entities or r.caption_entities),
            "from": {
                "id": int(rs.id) if rs else 0,
                "name": rname,
                "username": (rs.username if rs else "") or "",
            },
            "text": rtext,
        }
        data["replyMessage"] = rdata

    return data


async def generate_quote_png(
    messages: list[dict],
    *,
    bg_color: str = "#1b1429",
    text_color: str = "#ffffff",
    reply_color: str = "#3b3b3b",
    scale: int = 2,
    width: int = 512,
    height: int = 768,
) -> Optional[bytes]:
    """Call a public LyoSU-compatible quote API and return PNG bytes."""
    payload = {
        "type": "quote",
        "format": "png",
        "backgroundColor": bg_color,
        "width": width,
        "height": height,
        "scale": scale,
        "messages": messages,
    }
    timeout = aiohttp.ClientTimeout(total=45, connect=10)
    headers = {"User-Agent": "ElaraQuoteBot/1.0", "Accept": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            for url in QUOTE_APIS:
                try:
                    async with session.post(url, json=payload) as resp:
                        if resp.status != 200:
                            body = (await resp.text())[:300]
                            print(f"[QUOTE API] {url} HTTP {resp.status}: {body}", flush=True)
                            continue

                        # Some compatible APIs return JSON/base64; .png endpoints may return image bytes.
                        content_type = (resp.headers.get("Content-Type") or "").lower()
                        if content_type.startswith("image/"):
                            raw = await resp.read()
                            if raw.startswith(b"\x89PNG\r\n\x1a\n"):
                                return raw
                            print(f"[QUOTE API] {url} returned non-PNG image ({content_type})", flush=True)
                            continue

                        try:
                            data = await resp.json(content_type=None)
                        except Exception as e:
                            body = (await resp.text())[:300]
                            print(f"[QUOTE API] {url} invalid JSON: {e}; body={body}", flush=True)
                            continue

                        if data.get("error"):
                            print(f"[QUOTE API] {url} API error: {data.get('error')}", flush=True)
                            continue

                        # LyoSU public API uses `image`; older forks sometimes wrap it in `result`.
                        img = data.get("image")
                        if not img and isinstance(data.get("result"), dict):
                            img = data["result"].get("image")
                        if not isinstance(img, str) or not img:
                            print(f"[QUOTE API] {url} response missing image; keys={list(data)[:10]}", flush=True)
                            continue

                        if img.startswith("data:"):
                            img = img.split(",", 1)[1]
                        try:
                            decoded = base64.b64decode(img, validate=True)
                        except Exception as e:
                            print(f"[QUOTE API] {url} invalid base64 image: {e}", flush=True)
                            continue
                        if decoded.startswith(b"\x89PNG\r\n\x1a\n"):
                            return decoded
                        print(f"[QUOTE API] {url} image payload was not PNG", flush=True)
                except Exception as e:
                    print(f"[QUOTE API] {url} failed: {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"[QUOTE API] session failed: {type(e).__name__}: {e}", flush=True)
    return None


def png_to_webp(png_bytes: bytes) -> Optional[bytes]:
    """Convert PNG → WebP for sticker output."""
    try:
        from io import BytesIO
        from PIL import Image
        im = Image.open(BytesIO(png_bytes)).convert("RGBA")
        out = BytesIO()
        im.save(out, format="WEBP")
        return out.getvalue()
    except Exception:
        return None


def crop_to_strip(png_bytes: bytes) -> bytes:
    """Basic smart-crop: keep center vertical strip."""
    try:
        from io import BytesIO
        from PIL import Image
        im = Image.open(BytesIO(png_bytes))
        w, h = im.size
        new_w = int(w * 0.65)
        x = (w - new_w) // 2
        im2 = im.crop((x, 0, x + new_w, h))
        out = BytesIO()
        im2.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png_bytes
