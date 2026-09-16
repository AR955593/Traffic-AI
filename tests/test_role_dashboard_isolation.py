"""
Comprehensive Test Suite for 3-Role Dashboard Isolation, RBAC Security, User Data Scoping, and Cross-Role Workflows.
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from main import app
from auth import AuthManager, generate_jwt_token
from mongo_db import get_mongo_db

auth_manager = AuthManager()

client = TestClient(app)

@pytest.fixture
def setup_users():
    db = get_mongo_db()
    # Clean up test users
    db.users.delete_many({"email_normalized": {"$in": ["iso_user_a@test.com", "iso_user_b@test.com", "iso_op@test.com"]}})
    
    # Create User A
    user_a = auth_manager.register_user("iso_user_a@test.com", "Password123!", "User A", role="USER")["user"]
    # Create User B
    user_b = auth_manager.register_user("iso_user_b@test.com", "Password123!", "User B", role="USER")["user"]
    # Create Traffic Operator
    op_user = auth_manager.register_user("iso_op@test.com", "Password123!", "Op User", role="TRAFFIC_OPERATOR")["user"]
    auth_manager.approve_operator(op_user["id"], admin_user_id="usr_admin")

    token_a = generate_jwt_token(user_a["id"], user_a["email"], "USER", user_a["name"])
    token_b = generate_jwt_token(user_b["id"], user_b["email"], "USER", user_b["name"])
    token_op = generate_jwt_token(op_user["id"], op_user["email"], "TRAFFIC_OPERATOR", op_user["name"])
    token_admin = generate_jwt_token("usr_admin", "admin@traffisense.gov", "ADMIN", "Primary Admin")

    return {
        "user_a": user_a,
        "user_b": user_b,
        "op_user": op_user,
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "headers_b": {"Authorization": f"Bearer {token_b}"},
        "headers_op": {"Authorization": f"Bearer {token_op}"},
        "headers_admin": {"Authorization": f"Bearer {token_admin}"}
    }

def test_user_cannot_access_admin_endpoints(setup_users):
    """Verify regular USER gets 403 on admin routes."""
    headers_a = setup_users["headers_a"]
    res = client.get("/api/v1/admin/users", headers=headers_a)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    res_audit = client.get("/api/v1/admin/audit-logs", headers=headers_a)
    assert res_audit.status_code == 403

def test_user_cannot_access_operator_endpoints(setup_users):
    """Verify regular USER gets 403 on operator triage/alert endpoints."""
    headers_a = setup_users["headers_a"]
    res = client.get("/api/v1/operator/incidents", headers=headers_a)
    assert res.status_code == 403

    res_alert = client.post("/api/v1/operator/alerts/publish", headers=headers_a, json={"title": "Hack Alert", "message": "Test"})
    assert res_alert.status_code == 403

def test_operator_cannot_access_admin_endpoints(setup_users):
    """Verify TRAFFIC_OPERATOR gets 403 on admin routes."""
    headers_op = setup_users["headers_op"]
    res = client.get("/api/v1/admin/users", headers=headers_op)
    assert res.status_code == 403

def test_user_data_isolation(setup_users):
    """Verify User A cannot access or delete User B's saved places/routes."""
    headers_a = setup_users["headers_a"]
    headers_b = setup_users["headers_b"]

    # Add saved place for User B
    res_b_add = client.post("/api/v1/user/places", headers=headers_b, json={
        "label": "Home",
        "custom_name": "B's Castle",
        "address": "Mall Road, Kanpur",
        "lat": 26.4499,
        "lon": 80.3319
    })
    assert res_b_add.status_code == 200
    place_b_id = res_b_add.json()["id"]

    # User A tries to delete User B's place -> expect 404 (not found in User A's places)
    res_a_del = client.delete(f"/api/v1/user/places/{place_b_id}", headers=headers_a)
    assert res_a_del.status_code == 404

    # User A listing places should not see User B's place
    res_a_list = client.get("/api/v1/user/places", headers=headers_a)
    assert res_a_list.status_code == 200
    places_a = res_a_list.json()
    assert not any(p["id"] == place_b_id for p in places_a)

def test_user_to_operator_workflow(setup_users):
    """Test USER incident report notifies TRAFFIC_OPERATOR."""
    headers_a = setup_users["headers_a"]
    headers_op = setup_users["headers_op"]

    res_report = client.post("/api/v1/incidents/report", headers=headers_a, json={
        "title": "Stalled Bus on VIP Road",
        "incident_type": "Vehicle Breakdown",
        "severity": "Moderate",
        "latitude": 26.4620,
        "longitude": 80.3550,
        "description": "Bus engine broke down blocking left lane"
    })
    assert res_report.status_code == 200
    inc_data = res_report.json()["incident"]
    inc_id = inc_data["incident_id"]

    # Check that Operator receives notification
    res_op_notifs = client.get("/api/v1/notifications", headers=headers_op)
    assert res_op_notifs.status_code == 200
    notifs = res_op_notifs.json()["notifications"]
    assert any(n.get("source_id") == inc_id for n in notifs)

def test_operator_to_user_workflow(setup_users):
    """Test OPERATOR incident verification notifies USER."""
    headers_a = setup_users["headers_a"]
    headers_op = setup_users["headers_op"]

    # Report incident
    res_report = client.post("/api/v1/incidents/report", headers=headers_a, json={
        "title": "Waterlogging on GT Road",
        "incident_type": "Flooding",
        "severity": "Major",
        "latitude": 26.4500,
        "longitude": 80.3200,
        "description": "Heavy rain water accumulation"
    })
    inc_id = res_report.json()["incident"]["incident_id"]

    # Operator verifies
    res_verify = client.post("/api/v1/operator/incidents/verify", headers=headers_op, json={
        "incident_id": inc_id,
        "status": "VERIFIED",
        "public_note": "Pumps deployed. Single lane open."
    })
    assert res_verify.status_code == 200

    # User receives notification
    res_user_notifs = client.get("/api/v1/notifications", headers=headers_a)
    assert res_user_notifs.status_code == 200
    user_notifs = res_user_notifs.json()["notifications"]
    assert any(n.get("source_id") == inc_id for n in user_notifs)

def test_admin_to_operator_workflow(setup_users):
    """Test ADMIN operator suspend/reactivate workflow."""
    headers_admin = setup_users["headers_admin"]
    op_user = setup_users["op_user"]

    # Admin suspends operator
    res_susp = client.post("/api/v1/admin/suspend-operator", headers=headers_admin, json={"operator_user_id": op_user["id"]})
    assert res_susp.status_code == 200
    assert res_susp.json()["user"]["status"] == "SUSPENDED"

    # Admin reactivates operator
    res_react = client.post("/api/v1/admin/reactivate-operator", headers=headers_admin, json={"operator_user_id": op_user["id"]})
    assert res_react.status_code == 200
    assert res_react.json()["user"]["status"] == "APPROVED"
