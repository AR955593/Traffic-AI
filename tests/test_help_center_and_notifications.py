"""
Comprehensive Test Suite for TrafficAI Help Center, Support Ticket Lifecycle,
and Centralized Notification Architecture across USER, OPERATOR, and ADMIN roles.
"""

import pytest
import sys
import os
from fastapi.testclient import TestClient

# Ensure src is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from app.main import app
from auth import AuthManager
from user_service import UserService
from help_center import help_center_manager
from mongo_db import get_mongo_db

client = TestClient(app)
user_service = UserService()
auth = AuthManager()

@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Cleanup test users, tickets, and notifications before and after tests."""
    db = get_mongo_db()
    db.users.delete_many({"email": {"$regex": r"@test-hc\.com$"}})
    db.support_tickets.delete_many({"user_email": {"$regex": r"@test-hc\.com$"}})
    db.notifications.delete_many({"$or": [{"metadata.test_run": True}, {"recipient_user_id": {"$regex": r"^usr_"}}]})
    yield
    db.users.delete_many({"email": {"$regex": r"@test-hc\.com$"}})
    db.support_tickets.delete_many({"user_email": {"$regex": r"@test-hc\.com$"}})
    db.notifications.delete_many({"$or": [{"metadata.test_run": True}, {"recipient_user_id": {"$regex": r"^usr_"}}]})

def create_test_account(name: str, email: str, role: str = "USER"):
    """Helper to register and authenticate test user accounts for all roles."""
    from auth import create_access_token
    role_upper = role.upper()
    reg_res = auth.register_user(email=email, password="TestPassword123!", name=name, role=role_upper, city="Kanpur, UP")
    user_data = reg_res["user"]
    user_id = user_data["id"]

    if role_upper == "TRAFFIC_OPERATOR":
        auth.approve_operator(user_id, admin_user_id="usr_admin")
    elif role_upper == "ADMIN":
        db = get_mongo_db()
        db.users.update_one({"id": user_id}, {"$set": {"role": "ADMIN"}})

    token = create_access_token({"sub": user_id, "id": user_id, "email": email, "role": role_upper})
    headers = {"Authorization": f"Bearer {token}"}
    return user_id, token, headers

def test_centralized_notification_architecture_helpers():
    """Verifies all required Part B notification functions exist and persist cleanly."""
    db = get_mongo_db()
    uid = "usr_test_notif_001"

    # 1. create_notification
    n1 = user_service.create_notification(
        user_id=uid,
        notif_type="TEST_TYPE",
        title="Test Title",
        message="Test Message",
        severity="HIGH",
        source_role="SYSTEM",
        related_entity_type="TEST_ENTITY",
        related_entity_id="ENT_100",
        dedupe_key="test_dk_001",
        metadata={"test_run": True}
    )
    assert n1 is not None
    assert n1["recipient_user_id"] == uid
    assert n1["severity"] == "HIGH"
    assert n1["related_entity_type"] == "TEST_ENTITY"
    assert n1["related_entity_id"] == "ENT_100"

    # 2. Duplicate prevention check
    n1_dup = user_service.create_notification(
        user_id=uid,
        notif_type="TEST_TYPE",
        title="Test Title",
        message="Test Message",
        dedupe_key="test_dk_001"
    )
    assert n1_dup is None

    # 3. get_unread_count & get_notifications
    unread = user_service.get_unread_count(uid)
    assert unread >= 1

    notifs = user_service.get_notifications(uid)
    assert len(notifs) >= 1
    assert notifs[0]["id"] == n1["id"]

    # 4. mark_notification_read
    ok_read = user_service.mark_notification_read(uid, n1["id"])
    assert ok_read is True
    assert user_service.get_unread_count(uid) == 0

    # 5. delete_notification
    ok_del = user_service.delete_notification(uid, n1["id"])
    assert ok_del is True

    db.notifications.delete_many({"recipient_user_id": uid})

def test_help_center_knowledge_base_search():
    """Verifies Help Center Knowledge Base article retrieval and search queries."""
    res = client.get("/api/v1/support/knowledge-base?query=login")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    articles = data["articles"]
    assert len(articles) >= 1
    assert any("Login" in a["title"] for a in articles)

def test_support_ticket_creation_and_auto_solution():
    """Verifies user support ticket submission, auto KB match, and TI-100001 format."""
    uid, token, headers = create_test_account("User Alpha", "user.alpha@test-hc.com", "USER")

    res = client.post("/api/v1/support/tickets", json={
        "category": "LOGIN_REGISTRATION",
        "subject": "Login problem with password",
        "description": "I cannot log in using my password credentials",
        "priority": "NORMAL",
        "related_feature": "Login / Registration"
    }, headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    ticket = data["ticket"]

    assert ticket["ticket_id"].startswith("TI-")
    assert ticket["user_id"] == uid
    assert ticket["category"] == "LOGIN_REGISTRATION"
    assert ticket["has_verified_solution"] is True
    assert ticket["status"] in ["IN_PROGRESS", "OPEN"]

    # Verify ticket listing for user
    res_list = client.get("/api/v1/support/tickets", headers=headers)
    assert res_list.status_code == 200
    tickets = res_list.json()["tickets"]
    assert len(tickets) >= 1
    assert tickets[0]["ticket_id"] == ticket["ticket_id"]

def test_support_ticket_role_isolation():
    """Verifies USER A cannot view or access USER B's support tickets."""
    uid_a, token_a, headers_a = create_test_account("User A", "user.a@test-hc.com", "USER")
    uid_b, token_b, headers_b = create_test_account("User B", "user.b@test-hc.com", "USER")

    # User A creates a ticket
    res_t = client.post("/api/v1/support/tickets", json={
        "category": "ROUTE_PLANNER",
        "subject": "Route planning failure on corridor",
        "description": "Cannot calculate route for Mall Road Kanpur",
        "priority": "URGENT"
    }, headers=headers_a)
    assert res_t.status_code == 200
    ticket_id = res_t.json()["ticket"]["ticket_id"]

    # User A can view own ticket
    res_own = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers_a)
    assert res_own.status_code == 200

    # User B attempting to view User A's ticket must receive HTTP 403 / denied
    res_other = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers_b)
    assert res_other.status_code == 403

def test_support_ticket_reply_and_user_notification():
    """Verifies support reply by operator/admin creates notification for user with entity routing."""
    uid_u, token_u, headers_u = create_test_account("User Commuter", "user.commuter@test-hc.com", "USER")
    uid_op, token_op, headers_op = create_test_account("Operator Support", "op.support@test-hc.com", "TRAFFIC_OPERATOR")

    # 1. User submits ticket
    res_t = client.post("/api/v1/support/tickets", json={
        "category": "GPS_LOCATION",
        "subject": "GPS location accuracy issue",
        "description": "App loses GPS satellite lock in dense area",
        "priority": "NORMAL"
    }, headers=headers_u)
    ticket_id = res_t.json()["ticket"]["ticket_id"]

    # 2. Operator replies to ticket
    res_reply = client.post(f"/api/v1/support/tickets/{ticket_id}/reply", json={
        "message": "Please enable High Accuracy GPS mode under Android device settings."
    }, headers=headers_op)
    assert res_reply.status_code == 200
    updated_ticket = res_reply.json()["ticket"]
    assert updated_ticket["status"] == "WAITING_FOR_USER"

    # 3. User receives support update notification
    res_notifs = client.get("/api/v1/notifications", headers=headers_u)
    assert res_notifs.status_code == 200
    notifs = res_notifs.json()["notifications"]
    sup_notif = next((n for n in notifs if n.get("related_entity_id") == ticket_id), None)
    assert sup_notif is not None
    assert sup_notif["related_entity_type"] == "SUPPORT_TICKET"
    assert "High Accuracy GPS" in sup_notif["message"]

def test_admin_public_system_notice_delivery():
    """Verifies ADMIN -> USER public system notice delivery."""
    uid_admin, token_admin, headers_admin = create_test_account("Admin System", "admin.sys@test-hc.com", "ADMIN")
    uid_u, token_u, headers_u = create_test_account("User Notice", "user.notice@test-hc.com", "USER")

    res_notice = client.post("/api/v1/admin/public-notice", json={
        "title": "Scheduled Maintenance Advisory",
        "message": "TrafficAI servers will undergo routine optimization from 02:00 to 02:30 UTC.",
        "severity": "HIGH"
    }, headers=headers_admin)

    assert res_notice.status_code == 200
    assert res_notice.json()["status"] == "success"

    # User receives public system notification
    res_notifs = client.get("/api/v1/notifications", headers=headers_u)
    notifs = res_notifs.json()["notifications"]
    pub_notif = next((n for n in notifs if n.get("type") == "PUBLIC_SYSTEM_NOTIFICATION"), None)
    assert pub_notif is not None
    assert pub_notif["title"] == "Scheduled Maintenance Advisory"
