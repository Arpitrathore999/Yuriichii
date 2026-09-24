from motor.motor_asyncio import AsyncIOMotorClient
import config

_client = AsyncIOMotorClient(config.MONGO_URI) if config.MONGO_URI else None
db = _client["elara"] if _client else None

def users():
    return db["users"] if db else None

def ai_history():
    return db["ai_history"] if db else None

def relationships():
    return db["relationships"] if db else None

def warnings():
    return db["warnings"] if db else None
