# Backward-compat re-export — canonical location: infrastructure.mongo
from .infrastructure.mongo import MongoStorage, mongo_db

__all__ = ["MongoStorage", "mongo_db"]
