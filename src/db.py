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

    conn.commit()
    conn.close()

# Initialize DB structure on import
init_db()
