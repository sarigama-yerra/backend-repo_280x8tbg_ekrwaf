from motor.motor_asyncio import AsyncIOMotorClient
from typing import Any, Dict, Optional, List
from datetime import datetime
import os

MONGO_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DATABASE_NAME", "appdb")

_client: Optional[AsyncIOMotorClient] = None
_db = None

async def get_db():
    global _client, _db
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URL)
        _db = _client[DB_NAME]
    return _db

async def create_document(collection: str, data: Dict[str, Any]) -> str:
    db = await get_db()
    now = datetime.utcnow()
    data["created_at"] = data.get("created_at", now)
    data["updated_at"] = data.get("updated_at", now)
    res = await db[collection].insert_one(data)
    return str(res.inserted_id)

async def update_document(collection: str, filter_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> int:
    db = await get_db()
    update_dict["updated_at"] = datetime.utcnow()
    res = await db[collection].update_one(filter_dict, {"$set": update_dict})
    return res.modified_count

async def get_documents(collection: str, filter_dict: Dict[str, Any], limit: int = 50, sort: Optional[List] = None) -> List[Dict[str, Any]]:
    db = await get_db()
    cursor = db[collection].find(filter_dict)
    if sort:
        cursor = cursor.sort(sort)
    docs = await cursor.limit(limit).to_list(length=limit)
    for d in docs:
        d["_id"] = str(d["_id"])  # cast ObjectId to str
    return docs

async def get_document(collection: str, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    db = await get_db()
    doc = await db[collection].find_one(filter_dict)
    if doc:
        doc["_id"] = str(doc["_id"])  # cast ObjectId to str
    return doc
