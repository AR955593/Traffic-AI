"""
Database Engine & Persistence Layer for TrafficAI.
Uses standard library sqlite3 for zero external database dependencies.
Manages users, saved places, saved routes, trip history, notification preferences,
user incident reports, prediction validation logs, and anomaly events.
"""
import os
import sqlite3
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import uuid

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "traffic_ai.db"))

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        initials TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'VIEWER',
        role_display TEXT NOT NULL DEFAULT 'Public Commuter',
        city TEXT DEFAULT 'Kanpur, UP',
        created_at TEXT NOT NULL
    );
    """)

    # Saved Places Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS saved_places (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        label TEXT NOT NULL, -- 'Home', 'Office', 'College', 'Custom'
        custom_name TEXT NOT NULL,
        address TEXT NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # Saved Routes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS saved_routes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        origin_name TEXT NOT NULL,
        origin_lat REAL NOT NULL,
        origin_lon REAL NOT NULL,
        dest_name TEXT NOT NULL,
        dest_lat REAL NOT NULL,
        dest_lon REAL NOT NULL,
        preference TEXT DEFAULT 'balanced',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # Trip History Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trip_history (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        origin_name TEXT NOT NULL,
        dest_name TEXT NOT NULL,
        distance_km REAL NOT NULL,
        duration_min INTEGER NOT NULL,
        est_duration_min INTEGER,
        route_used TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # Notification Preferences Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notification_prefs (
        user_id TEXT PRIMARY KEY,
        severe_traffic INTEGER DEFAULT 1,
        incident_on_route INTEGER DEFAULT 1,
        weather_impact INTEGER DEFAULT 1,
        route_change INTEGER DEFAULT 1,
        saved_route_congestion INTEGER DEFAULT 1,
        forecast_warning INTEGER DEFAULT 1,
        min_severity_threshold TEXT DEFAULT 'MODERATE',
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # User Reported Incidents Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_incidents (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        user_name TEXT,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        photo_url TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        road_segment_id TEXT,
        severity TEXT NOT NULL DEFAULT 'MODERATE',
        status TEXT NOT NULL DEFAULT 'Reported', -- Reported -> Verification -> Verified -> Active -> Resolved
        upvotes INTEGER DEFAULT 0,
        source TEXT DEFAULT 'Community Report',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Prediction Validation Logs Table (for ML Metrics MAE/RMSE/MAPE)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prediction_logs (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        segment_id TEXT NOT NULL,
        horizon TEXT NOT NULL, -- '+15m', '+30m', '+60m'
        predicted_congestion INTEGER NOT NULL,
        actual_congestion INTEGER NOT NULL,
        predicted_speed_kmh REAL NOT NULL,
        actual_speed_kmh REAL NOT NULL,
        model_version TEXT NOT NULL DEFAULT 'v1.3-xgb'
    );
    """)

    # Traffic Anomalies Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anomalies (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        segment_id TEXT NOT NULL,
        road_name TEXT NOT NULL,
        speed_drop_kmh REAL NOT NULL,
        congestion_score INTEGER NOT NULL,
        anomaly_state TEXT NOT NULL DEFAULT 'Watch', -- Normal, Watch, High Risk
        review_status TEXT NOT NULL DEFAULT 'Pending Review'
    );
    """)

    # Operational Zones Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS zones (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        city TEXT NOT NULL DEFAULT 'Kanpur',
        state TEXT NOT NULL DEFAULT 'UP',
        geometry TEXT,
        assigned_operators TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Operational Corridors Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS corridors (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        road_type TEXT NOT NULL DEFAULT 'Arterial',
        zone_id TEXT,
        road_segments TEXT,
        active_status INTEGER DEFAULT 1,
        congestion_threshold INTEGER DEFAULT 40,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # CCTV Cameras Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cctv_cameras (
        id TEXT PRIMARY KEY,
        camera_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        location TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        zone_id TEXT,
        stream_url TEXT NOT NULL,
        stream_protocol TEXT NOT NULL DEFAULT 'HLS',
        status TEXT NOT NULL DEFAULT 'ONLINE',
        enabled INTEGER DEFAULT 1,
        last_heartbeat TEXT,
        vehicle_count_source TEXT DEFAULT 'CCTV Analytics',
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Camera Health Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS camera_health_logs (
        id TEXT PRIMARY KEY,
        camera_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        status TEXT NOT NULL,
        latency_ms REAL,
        error_message TEXT,
        FOREIGN KEY (camera_id) REFERENCES cctv_cameras (id) ON DELETE CASCADE
    );
    """)

    # Vehicle Counts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicle_counts (
        id TEXT PRIMARY KEY,
        camera_id TEXT,
        segment_id TEXT,
        location TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        vehicle_count INTEGER NOT NULL,
        vehicle_classes TEXT,
        source TEXT NOT NULL,
        confidence REAL DEFAULT 1.0
    );
    """)

    # Signal Intelligence Recommendations Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS signal_recommendations (
        id TEXT PRIMARY KEY,
        intersection_id TEXT NOT NULL,
        name TEXT NOT NULL,
        direction TEXT NOT NULL,
        queue_meters REAL NOT NULL,
        current_green_sec INTEGER NOT NULL,
        recommended_green_sec INTEGER NOT NULL,
        reason TEXT NOT NULL,
        confidence REAL DEFAULT 0.90,
        status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
        created_by TEXT DEFAULT 'AI_TRAFFIC_ENGINE',
        approved_by TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Emergency Green Corridors Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emergency_corridors (
        id TEXT PRIMARY KEY,
        vehicle_type TEXT NOT NULL,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        route_geometry TEXT,
        eta_min REAL NOT NULL,
        time_saved_min REAL NOT NULL,
        intersections TEXT,
        status TEXT NOT NULL DEFAULT 'RECOMMENDATION_GENERATED',
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Traffic Alerts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS traffic_alerts (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'MEDIUM',
        affected_area TEXT NOT NULL,
        affected_corridor TEXT,
        start_time TEXT NOT NULL,
        expires_at TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        publisher_id TEXT NOT NULL,
        publisher_name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # Operator Preferences Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS operator_preferences (
        user_id TEXT PRIMARY KEY,
        alert_prefs TEXT,
        theme TEXT DEFAULT 'dark',
        units TEXT DEFAULT 'metric',
        telemetry_refresh_interval INTEGER DEFAULT 5,
        notification_settings TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        user_name TEXT NOT NULL,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        details TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        client_ip TEXT
    );
    """)

    # System Events Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_events (
        id TEXT PRIMARY KEY,
        component TEXT NOT NULL,
        status TEXT NOT NULL,
        details TEXT NOT NULL,
        timestamp TEXT NOT NULL
    );
    """)

    # Seed Initial Data if Tables are Empty
    now_str = datetime.now(timezone.utc).isoformat()

    cursor.execute("SELECT COUNT(*) FROM zones")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO zones VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ZONE-01", "Zone 1 - Central Corridor", "Kanpur", "UP", '{"lat":26.4499,"lon":80.3319}', '[]', "ACTIVE", now_str, now_str))
        cursor.execute("INSERT INTO zones VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ZONE-02", "Zone 2 - Mall Road Interchange", "Kanpur", "UP", '{"lat":26.4600,"lon":80.3400}', '[]', "ACTIVE", now_str, now_str))

    cursor.execute("SELECT COUNT(*) FROM corridors")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO corridors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CORR-01", "Mall Road Arterial", "Arterial", "ZONE-02", '["seg_mall_rd_1","seg_mall_rd_2"]', 1, 40, "Primary commercial corridor", now_str, now_str))
        cursor.execute("INSERT INTO corridors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CORR-02", "GT Road Bypass Sector 4", "Highway", "ZONE-01", '["seg_gt_road_1"]', 1, 35, "Heavy freight bypass", now_str, now_str))

    cursor.execute("SELECT COUNT(*) FROM cctv_cameras")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO cctv_cameras VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CAM-01", "CAM-01", "Civil Lines Crossing North", "Civil Lines Crossing North", 26.4710, 80.3510, "ZONE-01", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8", "HLS", "ONLINE", 1, now_str, "CCTV Analytics", "Primary PTZ optical camera", now_str, now_str))
        cursor.execute("INSERT INTO cctv_cameras VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CAM-02", "CAM-02", "Mall Road Interchange", "Mall Road Interchange", 26.4600, 80.3400, "ZONE-02", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8", "HLS", "ONLINE", 1, now_str, "CCTV Analytics", "Fixed traffic flow camera", now_str, now_str))
        cursor.execute("INSERT INTO cctv_cameras VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CAM-03", "CAM-03", "GT Road Bypass Sector 4", "GT Road Bypass Sector 4", 26.4400, 80.3200, "ZONE-01", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8", "HLS", "ONLINE", 1, now_str, "CCTV Analytics", "Thermal flow sensor feed", now_str, now_str))
        cursor.execute("INSERT INTO cctv_cameras VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CAM-04", "CAM-04", "Swaroop Nagar Junction", "Swaroop Nagar Junction", 26.4800, 80.3100, "ZONE-01", "", "HLS", "OFFLINE", 0, None, "CCTV Analytics", "Maintenance feed - link pending", now_str, now_str))

    cursor.execute("SELECT COUNT(*) FROM signal_recommendations")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO signal_recommendations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("SIG-01", "INT-01-CIVIL-LINES", "Civil Lines / Mall Road Junction", "Northbound / Eastbound", 210.0, 35, 55, "Queue length exceeded threshold by 65m", 0.92, "PENDING_APPROVAL", "AI_TRAFFIC_ENGINE", None, now_str, now_str))
        cursor.execute("INSERT INTO signal_recommendations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("SIG-02", "INT-02-SWAROOP-NAGAR", "Swaroop Nagar Crossing", "Southbound", 85.0, 25, 35, "Flow stabilization recommendation", 0.88, "PENDING_APPROVAL", "AI_TRAFFIC_ENGINE", None, now_str, now_str))

    # Operator Shifts & Handover Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS operator_shifts (
        id TEXT PRIMARY KEY,
        operator_id TEXT NOT NULL,
        operator_name TEXT NOT NULL,
        shift_start TEXT NOT NULL,
        shift_end TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        handover_to_id TEXT,
        handover_to_name TEXT,
        handover_notes TEXT,
        summary_snapshot TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Camera Calibrations Table (V4)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS camera_calibrations (
        id TEXT PRIMARY KEY,
        camera_id TEXT UNIQUE NOT NULL,
        road_segment_id TEXT,
        direction TEXT DEFAULT 'BOTH',
        lanes INTEGER DEFAULT 2,
        counting_line TEXT,
        roi TEXT,
        vehicle_classes TEXT,
        calibration_status TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
        updated_at TEXT NOT NULL,
        FOREIGN KEY (camera_id) REFERENCES cctv_cameras (id) ON DELETE CASCADE
    );
    """)

    # Vehicle Telemetry Ingestion Table (V4)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicle_telemetry (
        id TEXT PRIMARY KEY,
        camera_id TEXT,
        road_segment_id TEXT,
        zone_id TEXT,
        timestamp TEXT NOT NULL,
        vehicle_count INTEGER NOT NULL,
        vehicles_per_minute REAL,
        vehicles_per_5_minutes REAL,
        direction TEXT,
        average_speed REAL,
        queue_length REAL,
        occupancy REAL,
        vehicle_class_counts TEXT,
        source TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'LIVE'
    );
    """)

    # Traffic Anomalies Table (V4)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS traffic_anomalies (
        id TEXT PRIMARY KEY,
        road_segment_id TEXT NOT NULL,
        type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'WARNING',
        observed_value REAL,
        baseline_value REAL,
        change_pct REAL,
        detected_at TEXT NOT NULL,
        data_source TEXT,
        freshness TEXT NOT NULL DEFAULT 'LIVE',
        status TEXT NOT NULL DEFAULT 'ACTIVE'
    );
    """)

    # AI Recommendations Center Table (V4)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_recommendations (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        what TEXT NOT NULL,
        why TEXT NOT NULL,
        data_source TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        freshness TEXT NOT NULL DEFAULT 'LIVE',
        expected_impact TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'NEW'
    );
    """)

    # Migrations: Ensure cctv_cameras has V4 columns
    cursor.execute("PRAGMA table_info(cctv_cameras)")
    cam_cols = [r[1] for r in cursor.fetchall()]
    new_cols = {
        "road_segment_id": "TEXT",
        "direction": "TEXT DEFAULT 'BOTH'",
        "source_type": "TEXT DEFAULT 'RTSP_ONVIF'",
        "stream_reference": "TEXT",
        "camera_status": "TEXT DEFAULT 'ONLINE'",
        "stream_status": "TEXT DEFAULT 'NOT_CONFIGURED'",
        "ai_status": "TEXT DEFAULT 'UNAVAILABLE'",
        "vehicle_data_status": "TEXT DEFAULT 'N/A'",
        "last_stream_check": "TEXT",
        "last_frame_time": "TEXT"
    }
    for col_name, col_def in new_cols.items():
        if col_name not in cam_cols:
            try:
                cursor.execute(f"ALTER TABLE cctv_cameras ADD COLUMN {col_name} {col_def}")
            except Exception:
                pass

    # Seed initial V4 anomalies if empty
    cursor.execute("SELECT COUNT(*) FROM traffic_anomalies")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO traffic_anomalies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ANOM-01", "CORR-01", "SUDDEN_SPEED_DROP", "HIGH", 19.5, 45.0, -56.7, now_str, "TomTom Traffic API", "LIVE", "ACTIVE"))
        cursor.execute("INSERT INTO traffic_anomalies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ANOM-02", "CORR-02", "QUEUE_GROWTH", "WARNING", 240.0, 90.0, 166.7, now_str, "TrafficAI Anomaly Engine", "LIVE", "ACTIVE"))

    # Seed initial V4 AI recommendations if empty
    cursor.execute("SELECT COUNT(*) FROM ai_recommendations")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO ai_recommendations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("REC-01", "SIGNALS", "Extend Green Phase at GT Road Junction", "Increase Northbound green phase from 35s to 55s (+20s)", "Queue length on GT Road Bypass reached 240m exceeding the 90m baseline", "TomTom Speed & Signal Queue Telemetry", now_str, "LIVE", "Estimated delay reduction: -4.5 min / -30% queue length", "NEW"))
        cursor.execute("INSERT INTO ai_recommendations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("REC-02", "TRAFFIC", "Publish Advisory for VIP Road Waterlogging", "Broadcast caution alert to mobile commuters navigating VIP Road Riverfront", "Observed speed drop to 18 km/h due to road surface conditions", "Open-Meteo Weather & Traffic Sensors", now_str, "LIVE", "Estimated diversion of 25% traffic to Ring Road", "NEW"))

    conn.commit()
    conn.close()

# Initialize DB structure on import
init_db()
