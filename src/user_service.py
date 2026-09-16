"""
User Service Module for TrafficAI.
Manages Saved Places (Home, Office, College, Custom), Saved Routes, Trip History,
and Notification Preferences stored in MongoDB collections with strict user-level isolation.
"""
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from mongo_db import get_mongo_db

class UserService:
    def __init__(self):
        pass

    @property
    def db(self):
        return get_mongo_db()

    # -------------------------------------------------------------
    # SAVED PLACES
    # -------------------------------------------------------------
    def get_saved_places(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.db.saved_places.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1)
        return list(cursor)

    def add_saved_place(self, user_id: str, label: str, custom_name: str, address: str, lat: float, lon: float) -> Dict[str, Any]:
        place_id = f"plc_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": place_id,
            "user_id": user_id,
            "label": label,
            "custom_name": custom_name,
            "address": address,
            "lat": float(lat),
            "lon": float(lon),
            "created_at": now_str
        }
        self.db.saved_places.insert_one(doc.copy())
        return {
            "id": place_id,
            "user_id": user_id,
            "label": label,
            "custom_name": custom_name,
            "address": address,
            "lat": float(lat),
            "lon": float(lon),
            "created_at": now_str
        }

    def delete_saved_place(self, user_id: str, place_id: str) -> bool:
        res = self.db.saved_places.delete_one({"id": place_id, "user_id": user_id})
        return res.deleted_count > 0

    # -------------------------------------------------------------
    # SAVED ROUTES
    # -------------------------------------------------------------
    def get_saved_routes(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.db.saved_routes.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1)
        return list(cursor)

    def add_saved_route(self, user_id: str, title: str, origin_name: str, origin_lat: float, origin_lon: float, dest_name: str, dest_lat: float, dest_lon: float, preference: str = "balanced") -> Dict[str, Any]:
        route_id = f"srt_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": route_id,
            "user_id": user_id,
            "title": title,
            "origin_name": origin_name,
            "origin_lat": float(origin_lat),
            "origin_lon": float(origin_lon),
            "dest_name": dest_name,
            "dest_lat": float(dest_lat),
            "dest_lon": float(dest_lon),
            "preference": preference,
            "created_at": now_str
        }
        self.db.saved_routes.insert_one(doc.copy())
        return {
            "id": route_id,
            "user_id": user_id,
            "title": title,
            "origin_name": origin_name,
            "origin_lat": float(origin_lat),
            "origin_lon": float(origin_lon),
            "dest_name": dest_name,
            "dest_lat": float(dest_lat),
            "dest_lon": float(dest_lon),
            "preference": preference,
            "created_at": now_str
        }

    def delete_saved_route(self, user_id: str, route_id: str) -> bool:
        res = self.db.saved_routes.delete_one({"id": route_id, "user_id": user_id})
        return res.deleted_count > 0

    # -------------------------------------------------------------
    # TRIP HISTORY & PERSONAL ANALYTICS
    # -------------------------------------------------------------
    def get_trip_history(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        cursor = self.db.trip_history.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1).limit(limit)
        return list(cursor)

    def add_trip_record(self, user_id: str, origin_name: str, dest_name: str, distance_km: float, duration_min: int, est_duration_min: Optional[int] = None, route_used: str = "Recommended Corridor") -> Dict[str, Any]:
        trip_id = f"trp_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": trip_id,
            "user_id": user_id,
            "origin_name": origin_name,
            "dest_name": dest_name,
            "distance_km": float(distance_km),
            "duration_min": int(duration_min),
            "est_duration_min": int(est_duration_min or duration_min),
            "route_used": route_used,
            "created_at": now_str
        }
        self.db.trip_history.insert_one(doc.copy())
        return {
            "id": trip_id,
            "origin_name": origin_name,
            "dest_name": dest_name,
            "distance_km": float(distance_km),
            "duration_min": int(duration_min),
            "est_duration_min": int(est_duration_min or duration_min),
            "route_used": route_used,
            "created_at": now_str
        }

    def clear_trip_history(self, user_id: str) -> bool:
        self.db.trip_history.delete_many({"user_id": user_id})
        return True

    def get_personal_analytics(self, user_id: str) -> Dict[str, Any]:
        trips = self.get_trip_history(user_id, limit=200)
        if not trips:
            return {
                "total_trips": 0,
                "total_distance_km": 0.0,
                "avg_travel_time_min": 0,
                "estimated_time_saved_min": 0,
                "frequent_corridors": [],
                "best_departure_window": "08:35–08:50"
            }

        total_dist = sum(t.get("distance_km", 0.0) for t in trips)
        avg_dur = int(sum(t.get("duration_min", 0) for t in trips) / len(trips))
        time_saved = sum(max(0, (t.get("est_duration_min") or t.get("duration_min", 0)) - t.get("duration_min", 0)) for t in trips)
        routes_count = {}
        for t in trips:
            r = t.get("route_used") or "Main Arterial"
            routes_count[r] = routes_count.get(r, 0) + 1
        
        top_routes = sorted([{"corridor": k, "trips": v} for k, v in routes_count.items()], key=lambda x: x["trips"], reverse=True)[:3]

        return {
            "total_trips": len(trips),
            "total_distance_km": round(total_dist, 1),
            "avg_travel_time_min": avg_dur,
            "estimated_time_saved_min": time_saved,
            "frequent_corridors": top_routes,
            "best_departure_window": "08:35–08:50"
        }

    # -------------------------------------------------------------
    # NOTIFICATION PREFERENCES
    # -------------------------------------------------------------
    def get_notification_prefs(self, user_id: str) -> Dict[str, Any]:
        doc = self.db.notification_preferences.find_one({"user_id": user_id}, {"_id": 0})
        if not doc:
            now_str = datetime.now(timezone.utc).isoformat()
            default_prefs = {
                "user_id": user_id,
                "severe_traffic": True,
                "incident_on_route": True,
                "weather_impact": True,
                "route_change": True,
                "saved_route_congestion": True,
                "forecast_warning": True,
                "min_severity_threshold": "MODERATE",
                "updated_at": now_str
            }
            self.db.notification_preferences.update_one(
                {"user_id": user_id},
                {"$setOnInsert": default_prefs},
                upsert=True
            )
            return {k: v for k, v in default_prefs.items() if k != "_id"}
        
        return {
            "user_id": doc.get("user_id", user_id),
            "severe_traffic": bool(doc.get("severe_traffic", True)),
            "incident_on_route": bool(doc.get("incident_on_route", True)),
            "weather_impact": bool(doc.get("weather_impact", True)),
            "route_change": bool(doc.get("route_change", True)),
            "saved_route_congestion": bool(doc.get("saved_route_congestion", True)),
            "forecast_warning": bool(doc.get("forecast_warning", True)),
            "min_severity_threshold": doc.get("min_severity_threshold", "MODERATE")
        }

    def update_notification_prefs(self, user_id: str, prefs: dict) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        update_data = {
            "severe_traffic": bool(prefs.get("severe_traffic", True)),
            "incident_on_route": bool(prefs.get("incident_on_route", True)),
            "weather_impact": bool(prefs.get("weather_impact", True)),
            "route_change": bool(prefs.get("route_change", True)),
            "saved_route_congestion": bool(prefs.get("saved_route_congestion", True)),
            "forecast_warning": bool(prefs.get("forecast_warning", True)),
            "min_severity_threshold": prefs.get("min_severity_threshold", "MODERATE"),
            "updated_at": now_str
        }
        self.db.notification_preferences.update_one(
            {"user_id": user_id},
            {"$set": update_data, "$setOnInsert": {"user_id": user_id}},
            upsert=True
        )
        return self.get_notification_prefs(user_id)

    # -------------------------------------------------------------
    # REAL-TIME NOTIFICATIONS
    # -------------------------------------------------------------
    def create_notification(
        self,
        user_id: str,
        notif_type: str,
        title: str,
        message: str,
        severity: str = "MEDIUM",
        source: str = "system",
        source_id: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Creates and persists a real-time notification document in MongoDB with deduplication."""
        # 1. Deduplication check
        if dedupe_key:
            existing = self.db.notifications.find_one({"dedupe_key": dedupe_key})
            if existing:
                return None

        # 2. Check user notification preferences
        prefs = self.get_notification_prefs(user_id)
        if severity == "LOW" and not prefs.get("saved_route_congestion", True):
            return None

        notif_id = f"ntf_{uuid.uuid4().hex[:10]}"
        now_str = datetime.now(timezone.utc).isoformat()

        doc = {
            "id": notif_id,
            "notification_id": notif_id,
            "user_id": user_id,
            "type": notif_type,
            "title": title,
            "message": message,
            "severity": severity,
            "source": source,
            "source_id": source_id,
            "dedupe_key": dedupe_key,
            "created_at": now_str,
            "read_at": None,
            "read": False,
            "metadata": metadata or {}
        }

        self.db.notifications.insert_one(doc.copy())
        return {k: v for k, v in doc.items() if k != "_id"}

    def get_user_notifications(self, user_id: str, limit: int = 50, unread_only: bool = False) -> List[Dict[str, Any]]:
        # Auto-seed role-specific default notifications if user has 0 notifications
        total_count = self.db.notifications.count_documents({"user_id": user_id})
        if total_count == 0:
            user_doc = self.db.users.find_one({"$or": [{"id": user_id}, {"_id": user_id}]}) or {}
            role = user_doc.get("role", "USER")
            
            if role == "ADMIN":
                self.create_notification(user_id, "SYSTEM", "System Admin Control Online", "Primary Admin dashboard activated. User management and operator approvals ready.", "HIGH", "admin_system", dedupe_key=f"init_admin_{user_id}")
                self.create_notification(user_id, "ALERT", "Pending Operator Approvals", "Review registered Traffic Operator accounts requiring verification before activation.", "MEDIUM", "admin_system", dedupe_key=f"init_admin_op_{user_id}")
                self.create_notification(user_id, "INFO", "Database Health Optimal", "MongoDB Atlas production cluster connected and operational.", "LOW", "system", dedupe_key=f"init_admin_db_{user_id}")
            elif role == "TRAFFIC_OPERATOR":
                self.create_notification(user_id, "ALERT", "Traffic Control Portal Activated", "Operator dashboard online. Signal timing override & incident verification enabled.", "HIGH", "operator_system", dedupe_key=f"init_op_{user_id}")
                self.create_notification(user_id, "INCIDENT", "Pending Incident Verification", "User reported heavy congestion on Mall Road. Please inspect camera grid & verify.", "MEDIUM", "operator_system", dedupe_key=f"init_op_inc_{user_id}")
                self.create_notification(user_id, "CORRIDOR", "Emergency Corridor Standby", "Green wave emergency corridor system ready for dispatch requests.", "LOW", "operator_system", dedupe_key=f"init_op_emg_{user_id}")
            else:
                self.create_notification(user_id, "INFO", "Welcome to TrafficAI Hub", "Live AI traffic monitoring, optimal route planning, and real-time alerts active.", "LOW", "system", dedupe_key=f"init_usr_{user_id}")
                self.create_notification(user_id, "CONGESTION", "Mall Road Traffic Delay", "Heavy traffic detected on Mall Road, Kanpur (+12 min delay). Consider alternative routes.", "MEDIUM", "traffic_alert", dedupe_key=f"init_usr_delay_{user_id}")
                self.create_notification(user_id, "WEATHER", "Rainfall Advisory", "Light rain reported near Kanpur Central. Drive carefully with headlights on.", "LOW", "weather", dedupe_key=f"init_usr_wth_{user_id}")

        query = {"user_id": user_id}
        if unread_only:
            query["read_at"] = None

        cursor = self.db.notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
        return list(cursor)

    def get_unread_count(self, user_id: str) -> int:
        return self.db.notifications.count_documents({"user_id": user_id, "read_at": None})

    def mark_notification_read(self, user_id: str, notification_id: str) -> bool:
        now_str = datetime.now(timezone.utc).isoformat()
        res = self.db.notifications.update_one(
            {"user_id": user_id, "$or": [{"id": notification_id}, {"notification_id": notification_id}]},
            {"$set": {"read_at": now_str, "read": True}}
        )
        return res.modified_count > 0 or res.matched_count > 0

    def mark_all_read(self, user_id: str) -> int:
        now_str = datetime.now(timezone.utc).isoformat()
        res = self.db.notifications.update_many(
            {"user_id": user_id, "read_at": None},
            {"$set": {"read_at": now_str, "read": True}}
        )
        return res.modified_count

    def delete_notification(self, user_id: str, notification_id: str) -> bool:
        res = self.db.notifications.delete_one({"user_id": user_id, "$or": [{"id": notification_id}, {"notification_id": notification_id}]})
        return res.deleted_count > 0
