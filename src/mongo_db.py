"""
MongoDB Database Connection & Repository Layer for TrafficAI.
Manages centralized connection pooling, indexes, health check,
and collection access for users, saved places, saved routes,
trip history, notification preferences, email verification tokens,
and password reset tokens.
"""
import os
import time
from typing import Dict, Any, Optional
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

# Environment Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017/")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "traffic_ai")
MONGODB_MAX_POOL_SIZE = int(os.getenv("MONGODB_MAX_POOL_SIZE", "50"))
MONGODB_MIN_POOL_SIZE = int(os.getenv("MONGODB_MIN_POOL_SIZE", "5"))

_client: Optional[MongoClient] = None

def get_mongo_client() -> MongoClient:
    """Returns a centralized, pooled MongoClient instance."""
    global _client
    if _client is None:
        _client = MongoClient(
            MONGODB_URI,
            maxPoolSize=MONGODB_MAX_POOL_SIZE,
            minPoolSize=MONGODB_MIN_POOL_SIZE,
            serverSelectionTimeoutMS=2500,
            connectTimeoutMS=2500,
            socketTimeoutMS=5000,
            retryWrites=True
        )
    return _client

def get_mongo_db(db_name: Optional[str] = None):
    """Returns the primary TrafficAI MongoDB database."""
    client = get_mongo_client()
    return client[db_name or MONGODB_DATABASE]

def get_mongo_health() -> Dict[str, Any]:
    """
    Performs an active ping against MongoDB to verify connection status.
    Returns: status ('ONLINE' | 'OFFLINE'), latency_ms, and database name.
    """
    start = time.perf_counter()
    try:
        client = get_mongo_client()
        # The admin ping command is the canonical MongoDB heartbeat check
        client.admin.command('ping')
        latency = round((time.perf_counter() - start) * 1000, 1)
        return {
            "status": "ONLINE",
            "latency_ms": latency,
            "database": MONGODB_DATABASE,
            "error": None
        }
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        return {
            "status": "OFFLINE",
            "latency_ms": None,
            "database": MONGODB_DATABASE,
            "error": str(e)
        }
    except Exception as e:
        return {
            "status": "DEGRADED",
            "latency_ms": None,
            "database": MONGODB_DATABASE,
            "error": str(e)
        }

def init_mongo_indexes():
    """
    Ensures required indexes exist across all TrafficAI MongoDB collections:
    1. users: unique email_normalized index, sparse google_subject index.
    2. email_verification_tokens: TTL index on expires_at, index on token_hash.
    3. password_reset_tokens: TTL index on expires_at, index on token_hash.
    4. saved_places: user_id index.
    5. saved_routes: user_id index.
    6. trip_history: compound index on (user_id, created_at).
    7. notification_preferences: unique user_id index.
    8. user_incidents: compound index on (user_id, created_at).
    """
    try:
        db = get_mongo_db()

        # 1. Users Indexes
        db.users.create_index([("email_normalized", ASCENDING)], unique=True, name="idx_users_email_norm_unique")
        db.users.create_index([("google_subject", ASCENDING)], sparse=True, name="idx_users_google_sub")

        # 2. Email Verification Tokens (TTL auto-expires expired docs)
        db.email_verification_tokens.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_verify_ttl")
        db.email_verification_tokens.create_index([("token_hash", ASCENDING)], name="idx_verify_token_hash")
        db.email_verification_tokens.create_index([("user_id", ASCENDING)], name="idx_verify_user_id")

        # 3. Password Reset Tokens (TTL auto-expires expired docs)
        db.password_reset_tokens.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_reset_ttl")
        db.password_reset_tokens.create_index([("token_hash", ASCENDING)], name="idx_reset_token_hash")
        db.password_reset_tokens.create_index([("user_id", ASCENDING)], name="idx_reset_user_id")

        # 4. Saved Places Indexes
        db.saved_places.create_index([("user_id", ASCENDING)], name="idx_places_user_id")

        # 5. Saved Routes Indexes
        db.saved_routes.create_index([("user_id", ASCENDING)], name="idx_routes_user_id")

        # 6. Trip History Indexes
        db.trip_history.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)], name="idx_trips_user_time")

        # 7. Notification Preferences Index
        db.notification_preferences.create_index([("user_id", ASCENDING)], unique=True, name="idx_notif_prefs_user_id")

        # 8. User Incidents Index
        db.user_incidents.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)], name="idx_user_incidents_time")

        # 9. Notifications Indexes
        db.notifications.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)], name="idx_notif_user_time")
        db.notifications.create_index([("recipient_user_id", ASCENDING), ("created_at", ASCENDING)], name="idx_notif_recip_time")
        db.notifications.create_index([("recipient_user_id", ASCENDING), ("read_at", ASCENDING)], name="idx_notif_recip_read")
        db.notifications.create_index([("related_entity_id", ASCENDING)], sparse=True, name="idx_notif_related_entity")
        db.notifications.create_index([("expires_at", ASCENDING)], sparse=True, name="idx_notif_expires")
        db.notifications.create_index([("dedupe_key", ASCENDING)], sparse=True, name="idx_notif_dedupe")

        # 10. Audit Logs Indexes
        db.audit_logs.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)], name="idx_audit_logs_user_time")

        # 11. Support Tickets Indexes
        db.support_tickets.create_index([("ticket_id", ASCENDING)], unique=True, name="idx_tickets_id_unique")
        db.support_tickets.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)], name="idx_tickets_user_time")
        db.support_tickets.create_index([("status", ASCENDING), ("created_at", ASCENDING)], name="idx_tickets_status_time")
        db.support_tickets.create_index([("assigned_operator_id", ASCENDING)], sparse=True, name="idx_tickets_assigned_op")
        db.support_tickets.create_index([("assigned_admin_id", ASCENDING)], sparse=True, name="idx_tickets_assigned_adm")

        return True
    except Exception as e:
        print(f"[MongoDB] Warning creating indexes: {e}")
        return False
