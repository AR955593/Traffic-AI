"""
Comprehensive Test Suite for 3-Tier Traffic Classification, Real-Time MongoDB Notifications,
User Isolation, Notification Preferences, and Provider Health Checks in TrafficAI.
"""
import sys
import os
import pytest
from fastapi.testclient import TestClient

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from traffic_service import classify_traffic
from mongo_db import get_mongo_db, init_mongo_indexes
from auth import AuthManager
from user_service import UserService
from main import app

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    """Ensure indexes are initialized before running tests."""
    init_mongo_indexes()
    yield

def test_3_tier_traffic_classification_boundaries():
    """
    Verifies exact speed threshold classification:
      currentSpeed <= 40 km/h           -> HIGH TRAFFIC (RED #ef4444)
      >40 km/h AND <= 70 km/h          -> MEDIUM TRAFFIC (YELLOW #f59e0b)
      >70 km/h                           -> LOW TRAFFIC (GREEN #10b981)
      None                               -> STALE / GRAY (#80928e)
    """
    # 20 km/h -> HIGH
    c20 = classify_traffic(20.0)
    assert c20["level"] == "HIGH"
    assert c20["color"] == "#ef4444"

    # 40 km/h -> HIGH (boundary)
    c40 = classify_traffic(40.0)
    assert c40["level"] == "HIGH"
    assert c40["color"] == "#ef4444"

    # 40.1 km/h -> MEDIUM (boundary)
    c40_1 = classify_traffic(40.1)
    assert c40_1["level"] == "MEDIUM"
    assert c40_1["color"] == "#f59e0b"

    # 70 km/h -> MEDIUM (boundary)
    c70 = classify_traffic(70.0)
    assert c70["level"] == "MEDIUM"
    assert c70["color"] == "#f59e0b"

    # 70.1 km/h -> LOW (boundary)
    c70_1 = classify_traffic(70.1)
    assert c70_1["level"] == "LOW"
    assert c70_1["color"] == "#10b981"

    # None -> STALE
    c_none = classify_traffic(None)
    assert c_none["level"] == "STALE"
    assert c_none["color"] == "#80928e"


def test_notification_creation_deduplication_and_user_isolation():
    user_service = UserService()
    db = get_mongo_db()

    user_a = "usr_notif_tester_a"
    user_b = "usr_notif_tester_b"

    # Cleanup leftover test notifications
    db.notifications.delete_many({"user_id": {"$in": [user_a, user_b]}})

    # 1. Create Notification for User A
    n1 = user_service.create_notification(
        user_id=user_a,
        notif_type="incident.new",
        title="Accident on GT Road",
        message="Right lane blocked near Mall Road flyover.",
        severity="HIGH",
        source="tomtom",
        dedupe_key="incident:inc_test_101:new"
    )
    assert n1 is not None
    assert n1["user_id"] == user_a
    assert n1["severity"] == "HIGH"
    assert n1["read"] is False

    # 2. Duplicate notification with same dedupe_key should be ignored
    n1_dup = user_service.create_notification(
        user_id=user_a,
        notif_type="incident.new",
        title="Duplicate Accident",
        message="Should not be inserted",
        severity="HIGH",
        source="tomtom",
        dedupe_key="incident:inc_test_101:new"
    )
    assert n1_dup is None

    # 3. Create Notification for User B (User Isolation)
    n2 = user_service.create_notification(
        user_id=user_b,
        notif_type="traffic.high",
        title="Congestion Alert",
        message="Heavy traffic along Civil Lines.",
        severity="MEDIUM",
        source="tomtom",
        dedupe_key="road:civil_lines:high"
    )
    assert n2 is not None

    # 4. User A should only see User A's notifications
    notifs_a = user_service.get_user_notifications(user_a)
    assert len(notifs_a) == 1
    assert notifs_a[0]["user_id"] == user_a

    unread_a = user_service.get_unread_count(user_a)
    assert unread_a == 1

    # 5. Mark read & clear
    marked = user_service.mark_notification_read(user_a, n1["id"])
    assert marked is True
    assert user_service.get_unread_count(user_a) == 0

    # Cleanup
    db.notifications.delete_many({"user_id": {"$in": [user_a, user_b]}})


def test_notification_rest_endpoints_with_jwt():
    auth = AuthManager()
    email = "notif_rest_tester@traffic.ai"
    db = get_mongo_db()
    db.users.delete_many({"email_normalized": email.lower()})

    res = auth.register_user(email, "Password123!", "Notif Tester")
    token = res["token"]
    user_id = res["user"]["id"]

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Unread count endpoint
    resp = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 0

    # 2. Add notification directly
    user_service = UserService()
    notif = user_service.create_notification(user_id, "test", "Test Title", "Test Message", "HIGH")
    assert notif is not None

    # 3. Verify via GET /api/v1/notifications
    resp_list = client.get("/api/v1/notifications", headers=headers)
    assert resp_list.status_code == 200
    data = resp_list.json()
    assert data["unread_count"] == 1
    assert len(data["notifications"]) == 1

    # 4. Mark Read via POST
    resp_read = client.post(f"/api/v1/notifications/{notif['id']}/read", headers=headers)
    assert resp_read.status_code == 200
    assert resp_read.json()["unread_count"] == 0

    # Cleanup
    auth.delete_account(user_id)


def test_health_check_endpoint():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "mongodb" in data
    assert data["mongodb"]["status"] == "ONLINE"
    assert "providers" in data


def test_notification_mark_all_read_and_delete():
    auth = AuthManager()
    email = "notif_bulk_tester@traffic.ai"
    db = get_mongo_db()
    db.users.delete_many({"email_normalized": email.lower()})

    res = auth.register_user(email, "Password123!", "Bulk Tester")
    token = res["token"]
    user_id = res["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    user_service = UserService()
    # Create 3 notifications
    n1 = user_service.create_notification(user_id, "traffic", "Alert 1", "Message 1", "HIGH")
    n2 = user_service.create_notification(user_id, "incident", "Alert 2", "Message 2", "MEDIUM")
    n3 = user_service.create_notification(user_id, "weather", "Alert 3", "Message 3", "LOW")

    # Verify initial unread count
    resp = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.json()["unread_count"] == 3

    # Mark all read
    resp_mark_all = client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp_mark_all.status_code == 200
    assert resp_mark_all.json()["unread_count"] == 0

    # Delete 1 notification
    resp_del = client.delete(f"/api/v1/notifications/{n1['id']}", headers=headers)
    assert resp_del.status_code == 200
    assert resp_del.json()["deleted"] is True

    # Check remaining count
    resp_list = client.get("/api/v1/notifications", headers=headers)
    assert len(resp_list.json()["notifications"]) == 2

    # Cleanup
    auth.delete_account(user_id)

