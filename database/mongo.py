from motor.motor_asyncio import AsyncIOMotorClient
import config

_client = (
    AsyncIOMotorClient(config.MONGO_URI)
    if config.MONGO_URI
    else None
)

db = _client["elara"] if _client is not None else None


def users():
    return db["users"] if db is not None else None


def ai_history():
    return db["ai_history"] if db is not None else None


def relationships():
    return db["relationships"] if db is not None else None


def warnings():
    return db["warnings"] if db is not None else None


def social_settings():
    return db["social_settings"] if db is not None else None
