"""
Migration script from SQLite database to MongoDB.
Safely migrates users, saved places, saved routes, trip history,
notification preferences, and community incidents into MongoDB.
Does NOT delete the SQLite database.
Idempotent: matches existing records by email_normalized or IDs to prevent duplicates.
"""
import os
import sys
import sqlite3
from datetime import datetime, timezone

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(project_dir, "src"))

from mongo_db import get_mongo_db, init_mongo_indexes

SQLITE_PATH = os.path.join(project_dir, "data", "traffic_ai.db")

def migrate():
    print(f"=== Starting Migration from SQLite to MongoDB ===")
    if not os.path.exists(SQLITE_PATH):
        print(f"SQLite database not found at {SQLITE_PATH}. Nothing to migrate.")
        return

    init_mongo_indexes()
    db = get_mongo_db()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Migrate Users
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    print(f"Found {len(users)} users in SQLite.")
    migrated_users = 0
    for u in users:
        email_norm = u["email"].strip().lower()
        existing = db.users.find_one({"email_normalized": email_norm})
        if not existing:
            doc = {
                "id": u["id"],
                "email": u["email"].strip(),
                "email_normalized": email_norm,
                "name": u["name"],
                "initials": u["initials"],
                "password_hash": u["password_hash"],
                "auth_provider": "local",
                "google_subject": None,
                "email_verified": True, # Existing seeded/operational users marked verified
                "phone": None,
                "phone_verified": False,
                "role": u["role"],
                "role_display": u["role_display"],
                "city": u["city"],
                "avatar_url": None,
                "is_active": True,
                "created_at": u["created_at"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_login_at": datetime.now(timezone.utc).isoformat()
            }
            db.users.insert_one(doc)
            migrated_users += 1
    print(f"Migrated {migrated_users} new users to MongoDB.")

    # 2. Migrate Saved Places
    cursor.execute("SELECT * FROM saved_places")
    places = cursor.fetchall()
    print(f"Found {len(places)} saved places in SQLite.")
    migrated_places = 0
    for p in places:
        existing = db.saved_places.find_one({"id": p["id"]})
        if not existing:
            doc = {
                "id": p["id"],
                "user_id": p["user_id"],
                "label": p["label"],
                "custom_name": p["custom_name"],
                "address": p["address"],
                "lat": float(p["lat"]),
                "lon": float(p["lon"]),
                "created_at": p["created_at"],
                "updated_at": p["created_at"]
            }
            db.saved_places.insert_one(doc)
            migrated_places += 1
    print(f"Migrated {migrated_places} saved places to MongoDB.")

    # 3. Migrate Saved Routes
    cursor.execute("SELECT * FROM saved_routes")
    routes = cursor.fetchall()
    print(f"Found {len(routes)} saved routes in SQLite.")
    migrated_routes = 0
    for r in routes:
        existing = db.saved_routes.find_one({"id": r["id"]})
        if not existing:
            doc = {
                "id": r["id"],
                "user_id": r["user_id"],
                "title": r["title"],
                "origin_name": r["origin_name"],
                "origin_lat": float(r["origin_lat"]),
                "origin_lon": float(r["origin_lon"]),
                "dest_name": r["dest_name"],
                "dest_lat": float(r["dest_lat"]),
                "dest_lon": float(r["dest_lon"]),
                "preference": r["preference"] or "balanced",
                "created_at": r["created_at"],
                "updated_at": r["created_at"]
            }
            db.saved_routes.insert_one(doc)
            migrated_routes += 1
    print(f"Migrated {migrated_routes} saved routes to MongoDB.")

    # 4. Migrate Trip History
    cursor.execute("SELECT * FROM trip_history")
    trips = cursor.fetchall()
    print(f"Found {len(trips)} trips in SQLite.")
    migrated_trips = 0
    for t in trips:
        existing = db.trip_history.find_one({"id": t["id"]})
        if not existing:
            doc = {
                "id": t["id"],
                "user_id": t["user_id"],
                "origin_name": t["origin_name"],
                "dest_name": t["dest_name"],
                "distance_km": float(t["distance_km"]),
                "duration_min": int(t["duration_min"]),
                "est_duration_min": int(t["est_duration_min"] or t["duration_min"]),
                "route_used": t["route_used"] or "Recommended Route",
                "created_at": t["created_at"]
            }
            db.trip_history.insert_one(doc)
            migrated_trips += 1
    print(f"Migrated {migrated_trips} trips to MongoDB.")

    # 5. Migrate Notification Preferences
    cursor.execute("SELECT * FROM notification_prefs")
    prefs = cursor.fetchall()
    print(f"Found {len(prefs)} notification preference records in SQLite.")
    migrated_prefs = 0
    for pr in prefs:
        existing = db.notification_preferences.find_one({"user_id": pr["user_id"]})
        if not existing:
            doc = {
                "user_id": pr["user_id"],
                "severe_traffic": bool(pr["severe_traffic"]),
                "incident_on_route": bool(pr["incident_on_route"]),
                "weather_impact": bool(pr["weather_impact"]),
                "route_change": bool(pr["route_change"]),
                "saved_route_congestion": bool(pr["saved_route_congestion"]),
                "forecast_warning": bool(pr["forecast_warning"]),
                "min_severity_threshold": pr["min_severity_threshold"] or "MODERATE",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            db.notification_preferences.insert_one(doc)
            migrated_prefs += 1
    print(f"Migrated {migrated_prefs} notification preferences to MongoDB.")

    # 6. Migrate User Incidents
    cursor.execute("SELECT * FROM user_incidents")
    incidents = cursor.fetchall()
    print(f"Found {len(incidents)} user incidents in SQLite.")
    migrated_incidents = 0
    for inc in incidents:
        existing = db.user_incidents.find_one({"id": inc["id"]})
        if not existing:
            doc = {
                "id": inc["id"],
                "user_id": inc["user_id"],
                "user_name": inc["user_name"],
                "category": inc["category"],
                "description": inc["description"],
                "photo_url": inc["photo_url"],
                "latitude": float(inc["latitude"]),
                "longitude": float(inc["longitude"]),
                "road_segment_id": inc["road_segment_id"],
                "severity": inc["severity"],
                "status": inc["status"],
                "upvotes": int(inc["upvotes"] or 0),
                "source": inc["source"],
                "created_at": inc["created_at"],
                "updated_at": inc["updated_at"]
            }
            db.user_incidents.insert_one(doc)
            migrated_incidents += 1
    print(f"Migrated {migrated_incidents} incidents to MongoDB.")

    conn.close()
    print("=== Migration to MongoDB Complete! SQLite preserved untouched ===")

if __name__ == "__main__":
    migrate()
