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
        try:
            db.users.create_index(
                [("phone_normalized", ASCENDING)],
                unique=True,
                partialFilterExpression={"phone_normalized": {"$type": "string"}},
                name="idx_users_phone_norm_unique"
            )
        except Exception:
            # Drop old index without partialFilterExpression if schema options conflict
            try:
                db.users.drop_index("idx_users_phone_norm_unique")
                db.users.create_index(
                    [("phone_normalized", ASCENDING)],
                    unique=True,
                    partialFilterExpression={"phone_normalized": {"$type": "string"}},
                    name="idx_users_phone_norm_unique"
                )
            except Exception as ex:
                print(f"[MongoDB] Note on phone index: {ex}")
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

        # 12. Operational Control Center Indexes
        db.cctv_cameras.create_index([("camera_code", ASCENDING)], unique=True, name="idx_cctv_code_unique")
        db.cctv_cameras.create_index([("status", ASCENDING)], name="idx_cctv_status")
        db.cctv_cameras.create_index([("zone_id", ASCENDING)], name="idx_cctv_zone")
        db.zones.create_index([("id", ASCENDING)], unique=True, name="idx_zones_id")
        db.corridors.create_index([("id", ASCENDING)], unique=True, name="idx_corridors_id")
        db.signal_recommendations.create_index([("id", ASCENDING)], unique=True, name="idx_signals_id")
        db.signal_recommendations.create_index([("status", ASCENDING)], name="idx_signals_status")
        db.emergency_corridors.create_index([("id", ASCENDING)], unique=True, name="idx_emerg_id")
        db.traffic_alerts.create_index([("id", ASCENDING)], unique=True, name="idx_alerts_id")
        db.operator_preferences.create_index([("user_id", ASCENDING)], unique=True, name="idx_op_prefs_user")

        # 13. V5 Real Traffic Intelligence Indexes
        # Road Segments
        db.road_segments.create_index([("segment_id", ASCENDING)], unique=True, name="idx_road_seg_id_unique")
        db.road_segments.create_index([("corridor_id", ASCENDING)], name="idx_road_seg_corridor")
        db.road_segments.create_index([("zone_id", ASCENDING)], name="idx_road_seg_zone")
        db.road_segments.create_index([("external_id", ASCENDING)], sparse=True, name="idx_road_seg_ext")

        # Corridors (V5 collection or alias)
        db.v5_corridors.create_index([("corridor_id", ASCENDING)], unique=True, name="idx_v5_corridor_id_unique")
        db.v5_corridors.create_index([("zone_id", ASCENDING)], name="idx_v5_corridor_zone")

        # Camera Road Mappings
        db.camera_road_mappings.create_index([("camera_id", ASCENDING)], unique=True, name="idx_cam_road_map_cam")
        db.camera_road_mappings.create_index([("segment_id", ASCENDING)], name="idx_cam_road_map_seg")
        db.camera_road_mappings.create_index([("corridor_id", ASCENDING)], name="idx_cam_road_map_corr")

        # Vehicle Flow Snapshots
        db.vehicle_flow_snapshots.create_index([("camera_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_vflow_cam_time")
        db.vehicle_flow_snapshots.create_index([("segment_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_vflow_seg_time")
        db.vehicle_flow_snapshots.create_index([("corridor_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_vflow_corr_time")

        # Traffic State Snapshots
        db.traffic_state_snapshots.create_index([("segment_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_tstate_seg_time")
        db.traffic_state_snapshots.create_index([("corridor_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_tstate_corr_time")

        # Traffic Forecasts
        db.traffic_forecasts.create_index([("target_id", ASCENDING), ("target_timestamp", ASCENDING)], name="idx_forecast_target_time")
        db.traffic_forecasts.create_index([("target_type", ASCENDING), ("status", ASCENDING)], name="idx_forecast_type_status")

        # Anomalies V5
        db.anomalies.create_index([("anomaly_id", ASCENDING)], unique=True, name="idx_anomalies_id_unique")
        db.anomalies.create_index([("segment_id", ASCENDING)], name="idx_anomalies_seg")
        db.anomalies.create_index([("corridor_id", ASCENDING)], name="idx_anomalies_corr")
        db.anomalies.create_index([("status", ASCENDING), ("detected_at", ASCENDING)], name="idx_anomalies_status_time")

        # AI Recommendations V5
        db.recommendations.create_index([("recommendation_id", ASCENDING)], unique=True, name="idx_recs_id_unique")
        db.recommendations.create_index([("target_id", ASCENDING)], name="idx_recs_target")
        db.recommendations.create_index([("category", ASCENDING), ("status", ASCENDING)], name="idx_recs_cat_status")

        # Outcome Events
        db.outcome_events.create_index([("action_id", ASCENDING)], unique=True, name="idx_outcomes_action_id_unique")
        db.outcome_events.create_index([("recommendation_id", ASCENDING)], sparse=True, name="idx_outcomes_rec_id")
        db.outcome_events.create_index([("incident_id", ASCENDING)], sparse=True, name="idx_outcomes_inc_id")
        db.outcome_events.create_index([("measured_at", ASCENDING)], name="idx_outcomes_time")

        # Data Quality Snapshots
        db.data_quality_snapshots.create_index([("source", ASCENDING), ("measured_at", ASCENDING)], name="idx_dq_source_time")

        # 14. Admin V5 Command Center Indexes
        db.admin_settings.create_index([("key", ASCENDING)], unique=True, name="idx_admin_settings_key_unique")
        db.admin_settings.create_index([("category", ASCENDING)], name="idx_admin_settings_cat")

        db.feature_flags.create_index([("key", ASCENDING)], unique=True, name="idx_feature_flags_key_unique")
        db.feature_flags.create_index([("environment", ASCENDING)], name="idx_feature_flags_env")

        db.service_health_snapshots.create_index([("service", ASCENDING), ("timestamp", ASCENDING)], name="idx_svc_health_time")

        db.security_events.create_index([("event_id", ASCENDING)], unique=True, name="idx_sec_events_id_unique")
        db.security_events.create_index([("type", ASCENDING), ("timestamp", ASCENDING)], name="idx_sec_events_type_time")
        db.security_events.create_index([("severity", ASCENDING)], name="idx_sec_events_sev")
        db.security_events.create_index([("actor_user_id", ASCENDING)], sparse=True, name="idx_sec_events_actor")

        db.backup_records.create_index([("backup_id", ASCENDING)], unique=True, name="idx_backups_id_unique")
        db.backup_records.create_index([("status", ASCENDING), ("created_at", ASCENDING)], name="idx_backups_status_time")

        db.admin_sessions.create_index([("session_id", ASCENDING)], unique=True, name="idx_admin_sessions_id_unique")
        db.admin_sessions.create_index([("user_id", ASCENDING), ("status", ASCENDING)], name="idx_admin_sessions_user_status")

        # Initialize defaults safely
        init_admin_v5_defaults(db)

        return True
    except Exception as e:
        print(f"[MongoDB] Warning creating indexes: {e}")
        return False

def init_admin_v5_defaults(db=None):
    """
    Safely seeds initial feature flags and default admin settings if not present.
    Idempotent and backward compatible.
    """
    if db is None:
        db = get_mongo_db()

    # Default Feature Flags
    default_flags = [
        {
            "key": "vehicle_intelligence",
            "name": "Vehicle Telemetry & Flow Intelligence",
            "enabled": True,
            "category": "Traffic",
            "environment": "production",
            "description": "Enables camera-level vehicle counting, speed calculation and classification.",
            "last_changed": "2026-09-19T00:00:00Z",
            "changed_by": "SYSTEM"
        },
        {
            "key": "camera_calibration",
            "name": "CCTV ROI & Perspective Calibration",
            "enabled": True,
            "category": "CCTV",
            "environment": "production",
            "description": "Enables operator and admin configuration of camera counting lines and ROI coordinates.",
            "last_changed": "2026-09-19T00:00:00Z",
            "changed_by": "SYSTEM"
        },
        {
            "key": "anomaly_detection",
            "name": "Automated Anomaly Detection Engine V5",
            "enabled": True,
            "category": "Intelligence",
            "environment": "production",
            "description": "Triggers speed drop, queue surge and stale data alerts automatically.",
            "last_changed": "2026-09-19T00:00:00Z",
            "changed_by": "SYSTEM"
        },
        {
            "key": "ai_recommendations",
            "name": "Explainable AI Signal Recommendations",
            "enabled": True,
            "category": "AI",
            "environment": "production",
            "description": "Generates structured signal split proposals with simulation-only safeguard labels.",
            "last_changed": "2026-09-19T00:00:00Z",
            "changed_by": "SYSTEM"
        },
        {
            "key": "incident_replay",
            "name": "Timeline Incident Replay",
            "enabled": True,
            "category": "Operations",
            "environment": "production",
            "description": "Enables multi-entity synchronized incident historical playback.",
            "last_changed": "2026-09-19T00:00:00Z",
            "changed_by": "SYSTEM"
        },
        {
            "key": "emergency_corridor",
            "name": "Emergency Green Corridor Dispatch",
            "enabled": True,
            "category": "Operations",
            "environment": "production",
            "description": "Allows operators to clear corridors for emergency vehicle preemption.",
            "last_changed": "2026-09-19T00:00:00Z",
            "changed_by": "SYSTEM"
        },
        {
            "key": "notification_realtime",
            "name": "Real-Time WebSocket Broadcasts",
            "enabled": True,
            "category": "Notifications",
            "environment": "production",
            "description": "Broadcasts live incident, camera and system alerts to connected clients.",
            "last_changed": "2026-09-19T00:00:00Z",
            "changed_by": "SYSTEM"
        },
        {
            "key": "new_admin_dashboard",
            "name": "Admin Command Center V5",
            "enabled": True,
            "category": "Platform",
            "environment": "production",
            "description": "Enables comprehensive municipal administrative console and security center.",
            "last_changed": "2026-09-19T00:00:00Z",
            "changed_by": "SYSTEM"
        }
    ]

    for flag in default_flags:
        db.feature_flags.update_one(
            {"key": flag["key"]},
            {"$setOnInsert": flag},
            upsert=True
        )

    # Default Admin Settings
    default_settings = [
        {
            "key": "platform.name",
            "name": "Platform Title",
            "value": "TrafficAI Smart Route Platform",
            "default_value": "TrafficAI Smart Route Platform",
            "category": "General",
            "description": "Display title across administrative and municipal interfaces.",
            "risk_level": "LOW",
            "updated_at": "2026-09-19T00:00:00Z",
            "updated_by": "SYSTEM"
        },
        {
            "key": "platform.city",
            "name": "Jurisdiction City",
            "value": "Kanpur Nagar, India",
            "default_value": "Kanpur Nagar, India",
            "category": "General",
            "description": "Municipal operational jurisdiction location identifier.",
            "risk_level": "LOW",
            "updated_at": "2026-09-19T00:00:00Z",
            "updated_by": "SYSTEM"
        },
        {
            "key": "security.session_timeout_minutes",
            "name": "Admin Session Timeout (Minutes)",
            "value": 120,
            "default_value": 120,
            "category": "Security",
            "description": "Inactivity duration before requiring administrative re-authentication.",
            "risk_level": "MEDIUM",
            "updated_at": "2026-09-19T00:00:00Z",
            "updated_by": "SYSTEM"
        },
        {
            "key": "security.max_failed_logins",
            "name": "Max Failed Login Attempts",
            "value": 5,
            "default_value": 5,
            "category": "Security",
            "description": "Threshold of consecutive failed logins before flagging suspicious login activity.",
            "risk_level": "HIGH",
            "updated_at": "2026-09-19T00:00:00Z",
            "updated_by": "SYSTEM"
        },
        {
            "key": "traffic.anomaly_speed_drop_pct",
            "name": "Anomaly Speed Drop Threshold (%)",
            "value": 35,
            "default_value": 35,
            "category": "Traffic",
            "description": "Percentage decrease from free flow required to trigger sudden speed drop anomaly.",
            "risk_level": "MEDIUM",
            "updated_at": "2026-09-19T00:00:00Z",
            "updated_by": "SYSTEM"
        },
        {
            "key": "cctv.heartbeat_stale_seconds",
            "name": "CCTV Stale Threshold (Seconds)",
            "value": 300,
            "default_value": 300,
            "category": "CCTV",
            "description": "Duration without heartbeat before camera telemetry is marked STALE.",
            "risk_level": "MEDIUM",
            "updated_at": "2026-09-19T00:00:00Z",
            "updated_by": "SYSTEM"
        },
        {
            "key": "backup.retention_days",
            "name": "Backup Retention (Days)",
            "value": 30,
            "default_value": 30,
            "category": "Recovery",
            "description": "Number of days configuration and database snapshot records are preserved.",
            "risk_level": "LOW",
            "updated_at": "2026-09-19T00:00:00Z",
            "updated_by": "SYSTEM"
        }
    ]

    for setting in default_settings:
        db.admin_settings.update_one(
            {"key": setting["key"]},
            {"$setOnInsert": setting},
            upsert=True
        )

