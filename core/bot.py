from pyrogram import Client
import config

app = Client(
    "Elara",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)
