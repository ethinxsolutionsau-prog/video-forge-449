"""MongoDB connection singleton and startup helpers."""
import os
from motor.motor_asyncio import AsyncIOMotorClient

_client: AsyncIOMotorClient = None
_db = None


def init_db():
    global _client, _db
    _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    _db = _client[os.environ["DB_NAME"]]
    return _db


def get_db():
    if _db is None:
        init_db()
    return _db


def close_db():
    if _client is not None:
        _client.close()


async def ensure_indexes():
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.projects.create_index("id", unique=True)
    await db.projects.create_index("user_id")
    await db.scripts.create_index("project_id", unique=True)
    await db.scenes.create_index("project_id")
    await db.metadata_packages.create_index("project_id", unique=True)
    await db.assets.create_index("project_id")
    await db.render_jobs.create_index("project_id")
    await db.cost_logs.create_index("project_id")
    await db.provider_settings.create_index("user_id")
    await db.login_attempts.create_index("identifier")
    # Share tokens
    await db.projects.create_index("share_token", sparse=True, unique=True)
