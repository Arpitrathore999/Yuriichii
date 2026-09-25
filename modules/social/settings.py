from database.mongo import social_settings

DEFAULT_CAPTIONS = {'hug': ['🫂 <b>{a} ᴊᴜsᴛ ʜᴜɢs {b} ᴛɪɢʜᴛʟʏ...</b>\n<i>"Yeah... you\'re not escaping this one. 😏❤️"</i>',
         '🫂 <b>A ʟɪᴛᴛʟᴇ ʜᴜɢ? Nᴏᴘᴇ. {a} ɪs ɴᴏᴛ ʟᴇᴛᴛɪɴɢ ɢᴏ ᴏғ {b}. 🥰💕</b>\n<i>"Stay right here."</i>',
         '🤗 <b>{a} ᴊᴜsᴛ ғᴏᴜɴᴅ ᴛʜᴇ ᴘᴇʀғᴇᴄᴛ ᴇxᴄᴜsᴇ ᴛᴏ ʜᴏʟᴅ {b} ᴄʟᴏsᴇ. 🫶🏻</b>'],
 'kiss': ['💋 <b>Oᴏᴘs... {a} ᴊᴜsᴛ sᴛᴏʟᴇ ᴀ ᴋɪss ғʀᴏᴍ {b}.</b>\n'
          '<i>"Don\'t look at me like that... you\'ll make me do it again. 😘"</i>',
          '😘 <b>Tʜᴀᴛ ᴡᴀs sᴜᴘᴘᴏsᴇᴅ ᴛᴏ ʙᴇ ᴀ ǫᴜɪᴄᴋ ᴋɪss...</b>\n<i>"Well, that didn\'t go as planned. 🤭❤️"</i>',
          '💋 <b>{a} ᴊᴜsᴛ ʟᴇғᴛ {b} ᴡɪᴛʜ ᴀ ᴋɪss ᴀɴᴅ ᴀ ʟᴏᴛ ᴏғ ǫᴜᴇsᴛɪᴏɴs. 😏</b>'],
 'bite': ['😲 <b>{a} ᴊᴜsᴛ ʙɪᴛ {b}... ᴀɴᴅ ᴅɪᴅɴ\'ᴛ ᴇᴠᴇɴ ᴀᴘᴏʟᴏɢɪᴢᴇ.</b>\n<i>"You looked too tempting. 🤭"</i>',
          '🧛 <b>{b} ᴡᴀs ᴊᴜsᴛ ᴍɪɴᴅɪɴɢ ᴛʜᴇɪʀ ᴏᴡɴ ʙᴜsɪɴᴇss...</b>\n<i>Then {a} happened. 😭</i>',
          '😏 <b>Wᴀʀɴɪɴɢ: {a} ʜᴀs ᴅᴇᴠᴇʟᴏᴘᴇᴅ {b} ʟᴏᴏᴋs ᴛᴏᴏ ᴛᴀsᴛʏ. 🫦</b>'],
 'slap': ['👋 <b>{b} ᴊᴜsᴛ ʀᴇᴄᴇɪᴠᴇᴅ ᴀ ʟɪᴛᴛʟᴇ ʀᴇᴀʟɪᴛʏ ᴄʜᴇᴄᴋ ғʀᴏᴍ {a}. 💥</b>',
          '👋 <b>{a} sᴀɪᴅ "ᴡᴀᴋᴇ ᴜᴘ."</b>\n<i>{b} ᴜɴᴅᴇʀsᴛᴏᴏᴅ ᴛʜɪs ᴛɪᴍᴇ. 😭</i>',
          '💥 <b>Sʟᴏᴡ ᴅᴏᴡɴ. Nᴏ ʀᴇғᴜɴᴅs.</b>'],
 'kick': ['🦵 <b>{a} ᴊᴜsᴛ sᴇɴᴛ {b} ᴏɴ ᴀ ᴏɴᴇ-ᴡᴀʏ ᴛʀɪᴘ ᴛᴏ ᴛʜᴇ ғʟᴏᴏʀ. 🚀😭</b>',
          '💥 <b>{b} ᴡᴀs ᴛᴏᴏ ᴄʟᴏsᴇ... {a} ғɪxᴇᴅ ᴛʜᴀᴛ.</b>',
          '🦵 <b>Kɪᴄᴋ!</b>\n<i>"Nothing personal, babe. 😭❤️"</i>'],
 'cuddle': ['🫶 <b>{a} ᴊᴜsᴛ ᴄʟᴀɪᴍᴇᴅ {b} ғᴏʀ ᴀ ᴄᴜᴅᴅʟᴇ.</b>\n'
            '<i>"Come here... you\'re mine for the next few hours. 🫶🏻"</i>',
            '🧸 <b>Cᴜᴅᴅʟᴇ ᴍᴏᴅᴇ: Aᴄᴛɪᴠᴀᴛᴇᴅ. 💕</b>\n<i>{a} × {b} = ᴛᴏᴏ ᴄᴜᴛᴇ.</i>',
            '🤗 <b>Nᴏ ᴡᴏʀᴅs. Jᴜsᴛ {a} ᴀɴᴅ {b} ᴇɴᴊᴏʏɪɴɢ ᴛʜᴇ ᴍᴏᴍᴇɴᴛ. 🫂</b>'],
 'pat': ['🫳 <b>{a} ɢᴇɴᴛʟʏ ᴘᴀᴛᴛᴇᴅ {b}\'s ʜᴇᴀᴅ. 🥰💕</b>\n<i>"Good job, cutie."</i>',
         '🐾 <b>Pᴀᴛ ᴘᴀᴛ...</b>\n<i>{a} ʜᴀs ᴅᴇᴄɪᴅᴇᴅ {b} ɪs ᴛᴏᴏ ᴄᴜᴛᴇ ᴛᴏ ʟᴇᴀᴠᴇ ᴀʟᴏɴᴇ. 🤭</i>',
         "🫶🏻 <b>{a}'s ᴘᴀᴛᴛɪɴɢ ʜᴀs ᴜɴʟᴏᴄᴋᴇᴅ ᴘʀᴇᴍɪᴜᴍ ᴄᴜᴛᴇɴᴇss. ✨</b>"],
 'highfive': ['✋ <b>{a} ʜɪɢʜ-ғɪᴠᴇs {b} ʟɪᴋᴇ ᴛʜᴇʏ ᴊᴜsᴛ ᴡᴏɴ ᴛʜᴇ ʟᴏᴛᴛᴇʀʏ. 🔥</b>',
              '✋💥 <b>Hɪɢʜ ғɪᴠᴇ!</b>\n<i>Tʜᴀᴛ sʟᴀᴘ ᴡᴀs ʟᴏᴜᴅᴇʀ ᴛʜᴀɴ ᴛʜᴇɪʀ ᴄʜᴀᴛ. 😂</i>',
              '✨ <b>{a} + {b} = ᴅᴀɴɢᴇʀᴏᴜs ɢᴏᴏᴅ ᴛᴇᴀᴍᴡᴏʀᴋ. 🤝❤️</b>'],
 'flirt': ['😏 <b>{a} ᴊᴜsᴛ ᴅʀᴏᴘᴘᴇᴅ sᴏᴍᴇ sᴇʀɪᴏᴜs ғʟɪʀᴛ ᴏɴ {b}.</b>\n'
           '<i>"Are you always this attractive, or is today special? 👀❤️"</i>',
           '👀 <b>{a} ᴡᴀs ʟᴏᴏᴋɪɴɢ ᴀᴛ {b}...</b>\n<i>"Why are you making it so hard to behave? 😏"</i>',
           "💘 <b>Fʟɪʀᴛɪɴɢ ᴡɪᴛʜ {b} ʜᴀs ʙᴇᴇɴ ᴀᴅᴅᴇᴅ ᴛᴏ {a}'s ᴅᴀɪʟʏ sᴄʜᴇᴅᴜʟᴇ. 😌</b>"],
 'love': ['❤️ <b>Lᴏᴠᴇ Cʜᴇᴄᴋ</b> ❤️\n'
          '<b>{a} × {b}</b>\n'
          '💕 <b>Cᴏᴍᴘᴀᴛɪʙɪʟɪᴛʏ: {pct}%</b>\n'
          '<i>"Okay... this is getting suspiciously romantic. 👀💗"</i>',
          '💗 <b>Hᴇᴀʀᴛ Sʏɴᴄ Cᴏᴍᴘʟᴇᴛᴇᴅ</b>\n'
          '<b>{a} ❤️ {b}</b>\n'
          '✨ <b>Mᴀᴛᴄʜ: {pct}%</b>\n'
          '<i>"The chemistry is doing a little too much. 😏"</i>',
          '💞 <b>Lᴏᴠᴇ Aʟᴇʀᴛ!</b>\n'
          '<b>{a} + {b} = {pct}%</b>\n'
          '<i>"Someone\'s heart is definitely acting suspicious. 🤭❤️"</i>'],
 'crush': ['💘 <b>Sᴇᴄʀᴇᴛ Cʀᴜsʜ Dᴇᴛᴇᴄᴛᴇᴅ... 👀</b>\n'
           "<b>{a}'s sᴇᴄʀᴇᴛ ᴄʀᴜsʜ ɪs {b}!</b> 💕\n"
           '💘 <b>Cʀᴜsʜ Lᴇᴠᴇʟ: {pct}%</b>\n'
           '<i>"Don\'t tell them... this is supposed to be a secret. 🤫❤️"</i>',
           "👀 <b>Wᴇ ᴊᴜsᴛ ᴜɴᴄᴏᴠᴇʀᴇᴅ {a}'s sᴇᴄʀᴇᴛ...</b>\n"
           "💗 <b>Iᴛ's {b}!</b>\n"
           '✨ <b>Cʀᴜsʜ Pᴏᴡᴇʀ: {pct}%</b>\n'
           '<i>"Your secret is out. Oops. 🤭"</i>',
           '💌 <b>Sᴇᴄʀᴇᴛ ᴄʀᴜsʜ ᴘᴇɴᴅɪɴɢ ғᴏʀ {a}...</b>\n'
           '💞 <b>{b}</b>\n'
           '💘 <b>Hᴇᴀʀᴛ ʟᴇᴠᴇʟ: {pct}%</b>\n'
           '<i>"The heart knows something the brain doesn\'t. 😏❤️"</i>'],
 'couple': ["💞 <b>Tᴏᴅᴀʏ's Cᴜᴛᴇsᴛ Cᴏᴜᴘʟᴇ</b> 💞\n"
            '<b>{a} × {b}</b>\n'
            '💘 <b>Mᴀᴛᴄʜ: {pct}%</b>\n'
            '<i>"Okay... someone explain this chemistry. 👀❤️"</i>',
            '💗 <b>Cᴏᴜᴘʟᴇ Aʟᴇʀᴛ!</b>\n'
            '<b>{a} 💕 {b}</b>\n'
            '✨ <b>Lᴏᴠᴇ Sʏɴᴄ: {pct}%</b>\n'
            '<i>"This pairing is dangerously cute. 🤭"</i>',
            '💘 <b>Rᴀɴᴅᴏᴍ Cᴏᴜᴘʟᴇ Sᴇʟᴇᴄᴛᴇᴅ!</b>\n'
            '<b>{a} ❤️ {b}</b>\n'
            '💞 <b>Cʜᴇᴍɪsᴛʀʏ: {pct}%</b>\n'
            '<i>"The GC did not see this coming. 😏"</i>'],
 'propose': ['💍 <b>Wᴀɪᴛ... Tʜɪs ɪs Sᴇʀɪᴏᴜs. 😳</b>\n'
             '<b>{a}</b> ᴊᴜsᴛ ɢᴏᴛ ᴅᴏᴡɴ ᴏɴ ᴏɴᴇ ᴋɴᴇᴇ ғᴏʀ <b>{b}</b>. 💍\n'
             '<i>"I don\'t need forever... just say yes to me. 💍🫶"</i>',
             '💍 <b>Sᴏᴍᴇᴏɴᴇ Jᴜsᴛ Gᴏᴛ Bʀᴀᴠᴇ... 😭❤️</b>\n<b>{a} → {b}</b>\n<i>"Will you be mine? 👉👈💗"</i>',
             '🥹 <b>Tʜᴇ Bɪɢ Qᴜᴇsᴛɪᴏɴ ɪs Hᴇʀᴇ...</b>\n'
             '<b>{a} ᴡᴀɴᴛs {b} ᴛᴏ sᴀʏ ʏᴇs ᴡɪᴛʜ ғᴏʀᴇᴠᴇʀ. 💍</b>\n'
             '<i>"One little yes could change everything. ❤️"</i>'],
 'marriage': ['💒 <b>Wᴇʟʟ... Tʜᴇʏ ᴀᴄᴛᴜᴀʟʟʏ ᴅɪᴅ ɪᴛ. 😳❤️</b>\n'
              '<b>{a} × {b}</b>\n'
              '💍 <b>Oғғɪᴄɪᴀʟʟʏ Mᴀʀʀɪᴇᴅ. 💞</b>\n'
              '<i>"From one little yes... to forever. 🥹💗"</i>',
              "💍 <b>Iᴛ's Oғғɪᴄɪᴀʟ!</b>\n"
              '<b>{a} ❤️ {b}</b>\n'
              '💒 <b>Mᴀʀʀɪᴇᴅ!</b>\n'
              '<i>"The GC has a new power couple. 😎💕"</i>',
              '🥂 <b>Mᴀʀʀɪᴀɢᴇ Cᴏɴғɪʀᴍᴇᴅ!</b>\n<b>{a} & {b}</b> 💞\n<i>"Two hearts, one beautiful mess. 😭❤️"</i>'],
 'divorce': ['💔 <b>Sᴏ... Tʜɪs Is Rᴇᴀʟʟʏ Hᴀᴘᴘᴇɴɪɴɢ? 🥺</b>\n'
             '<b>{a} × {b}</b>\n'
             '<i>"Some stories don\'t get their forever... 💔"</i>\n'
             '💔 <b>Mᴀʀʀɪᴀɢᴇ Eɴᴅᴇᴅ</b>',
             '🥺 <b>Tʜᴇ Fᴏʀᴇᴠᴇʀ Pʟᴀɴ ʜᴀs ᴇɴᴅᴇᴅ...</b>\n<b>{a} 💔 {b}</b>\n<i>"And just like that, it\'s over. 😭"</i>',
             '💔 <b>Dɪᴠᴏʀᴄᴇ Fɪʟᴇᴅ... ᴀɴᴅ Aᴘᴘʀᴏᴠᴇᴅ. 🥺</b>\n<b>{a} ≠ {b}</b>\n<i>"Love story status: archived. 😭"</i>']}

COMMANDS = tuple(DEFAULT_CAPTIONS)


def _col():
    return social_settings()


async def get_social_data(command):
    fallback = {"gifs": [], "captions": DEFAULT_CAPTIONS.get(command, [])}
    col = _col()
    if col is None:
        return fallback

    try:
        doc = await col.find_one({"_id": command})
        if not doc:
            return fallback
        captions = list(doc.get("captions") or []) or fallback["captions"]
        gifs = list(doc.get("gifs") or [])
        return {"gifs": gifs, "captions": captions}
    except Exception as e:
        print(f"[SOCIAL SETTINGS ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return fallback


async def add_gif(command, file_id):
    col = _col()
    if col is None:
        return False
    try:
        await col.update_one({"_id": command}, {"$addToSet": {"gifs": file_id}}, upsert=True)
        return True
    except Exception as e:
        print(f"[ADD GIF ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return False


async def add_caption(command, caption):
    col = _col()
    if col is None:
        return False
    try:
        await col.update_one({"_id": command}, {"$addToSet": {"captions": caption}}, upsert=True)
        return True
    except Exception as e:
        print(f"[ADD CAPTION ERROR] /{command}: {type(e).__name__}: {e}", flush=True)
        return False


async def clear_gifs(command):
    col = _col()
    if col is None:
        return False
    try:
        await col.update_one({"_id": command}, {"$set": {"gifs": []}}, upsert=True)
        return True
    except Exception:
        return False


async def clear_captions(command):
    col = _col()
    if col is None:
        return False
    try:
        await col.update_one({"_id": command}, {"$set": {"captions": []}}, upsert=True)
        return True
    except Exception:
        return False
