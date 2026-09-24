import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
MONGO_URI = os.getenv("MONGO_URI", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ✅ NEW
BOT_NAME = os.getenv("BOT_NAME", "Elara")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

START_IMAGE_URL = os.getenv("START_IMAGE_URL", "")
SUPPORT_URL = os.getenv("SUPPORT_URL", "")
UPDATES_URL = os.getenv("UPDATES_URL", "")
OWNER_URL = os.getenv("OWNER_URL", "")