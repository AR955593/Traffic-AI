"""
TEST SUITE: Traffic Operator Dashboard & Control Center RBAC Isolation
Verifies operator endpoints, role enforcement, incident triage, alert broadcast, and simulation badging.
"""

import pytest
from fastapi.testclient import TestClient
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import app, auth_manager
from auth import create_access_token
from mongo_db import get_mongo_db

client = TestClient(app)

@pytest.fixture
def test_users():
    unique_suffix = uuid.uuid4().hex[:6]
    
    # 1. Commuter User
    u_email = f"commuter_{unique_suffix}@example.com"
    u_res = auth_manager.register_user(u_email, "Password123!", f"Commuter {unique_suffix}", role="USER")
    user_data = u_res["user"]
    user_token = create_access_token({"sub": user_data["id"], "email": u_email, "role": "USER"})

    # 2. Traffic Operator User
    op_email = f"op_{unique_suffix}@trafficai.gov.in"
    op_res = auth_manager.register_user(op_email, "Password123!", f"Operator {unique_suffix}", role="TRAFFIC_OPERATOR")
    op_data = op_res["user"]
    auth_manager.approve_operator(op_data["id"], admin_user_id="usr_admin")
    op_token = create_access_token({"sub": op_data["id"], "email": op_email, "role": "TRAFFIC_OPERATOR"})

    # 3. System Admin User
    admin_email = f"admin_{unique_suffix}@trafficai.gov.in"
    admin_res = auth_manager.register_user(admin_email, "Password123!", f"Admin {unique_suffix}", role="ADMIN")
    admin_data = admin_res["user"]
    admin_token = create_access_token({"sub": admin_data["id"], "email": admin_email, "role": "ADMIN"})

    return {
        "user_headers": {"Authorization": f"Bearer {user_token}"},
        "op_headers": {"Authorization": f"Bearer {op_token}"},
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "user_id": user_data["id"],
        "op_id": op_data["id"]
    }

def test_user_cannot_access_operator_apis(test_users):
    """Commuter USER must receive HTTP 403 Forbidden on all /api/v1/operator/* routes."""
    res_dash = client.get("/api/v1/operator/dashboard", headers=test_users["user_headers"])
    assert res_dash.status_code == 403, f"Expected 403 for commuter on operator dashboard, got {res_dash.status_code}"

    res_inc = client.get("/api/v1/operator/incidents", headers=test_users["user_headers"])
    assert res_inc.status_code == 403

    res_alert = client.post(
        "/api/v1/operator/alerts/publish",
        headers=test_users["user_headers"],
        json={"title": "Unauthorized Alert", "message": "Test Message", "severity": "HIGH", "location": "Test"}
    )
    assert res_alert.status_code == 403

def test_operator_can_access_operator_dashboard(test_users):
    """TRAFFIC_OPERATOR can access operator dashboard, incidents, signals, cctv, activity."""
    res_dash = client.get("/api/v1/operator/dashboard", headers=test_users["op_headers"])
    assert res_dash.status_code == 200
    data = res_dash.json()
    assert data["status"] == "success"
    assert data["operator"]["role"] == "TRAFFIC_OPERATOR"
    assert "kpis" in data
    assert "active_incidents" in data["kpis"]

    res_inc = client.get("/api/v1/operator/incidents", headers=test_users["op_headers"])
    assert res_inc.status_code == 200
    assert "pending" in res_inc.json()

def test_operator_cannot_access_admin_apis(test_users):
    """TRAFFIC_OPERATOR must receive HTTP 403 Forbidden on admin management routes."""
    res_admin_ops = client.get("/api/v1/admin/operators", headers=test_users["op_headers"])
    assert res_admin_ops.status_code == 403

    res_admin_health = client.get("/api/v1/admin/system-health", headers=test_users["op_headers"])
    assert res_admin_health.status_code == 403

def test_operator_incident_triage_workflow(test_users):
    """Operator verifies an incident -> updates status and notifies commuters."""
    inc_payload = {
        "title": "Road Blockage GT Road",
        "description": "Fallen tree blocking left lane",
        "incident_type": "Road Hazard",
        "severity": "HIGH",
        "location": "GT Road Kanpur",
        "latitude": 26.4499,
        "longitude": 80.3450
    }
    create_res = client.post("/api/v1/incidents/report", headers=test_users["user_headers"], json=inc_payload)
    assert create_res.status_code == 200
    inc_dict = create_res.json()["incident"]
    inc_id = inc_dict.get("incident_id") or inc_dict.get("id")

    verify_res = client.post(
        "/api/v1/operator/incidents/verify",
        headers=test_users["op_headers"],
        json={"incident_id": inc_id, "status": "VERIFIED", "public_note": "Verified by Traffic Ops"}
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["incident"]["status"] == "VERIFIED"

    notif_res = client.get("/api/v1/notifications", headers=test_users["user_headers"])
    assert notif_res.status_code == 200
    notifs = notif_res.json().get("notifications", [])
    assert any("Verified by Traffic Ops" in n.get("message", "") or "Traffic Update" in n.get("title", "") for n in notifs)

def test_operator_alert_publishing(test_users):
    """Operator publishes traffic alert -> broadcasts notification to commuters."""
    alert_payload = {
        "title": "Heavy Rain Flood Alert",
        "message": "Waterlogging on Mall Road underpass. Use Civil Lines diversion.",
        "severity": "HIGH",
        "location": "Mall Road Corridor"
    }
    pub_res = client.post("/api/v1/operator/alerts/publish", headers=test_users["op_headers"], json=alert_payload)
    assert pub_res.status_code == 200
    assert "alert_id" in pub_res.json()

    notif_res = client.get("/api/v1/notifications", headers=test_users["user_headers"])
    assert notif_res.status_code == 200
    notifs = notif_res.json().get("notifications", [])
    assert any("Heavy Rain Flood Alert" in n.get("title", "") for n in notifs)

def test_simulation_badges_in_operator_apis(test_users):
    """Signal Intelligence and Emergency Corridors must return clear simulation badges."""
    sig_res = client.get("/api/v1/operator/signals", headers=test_users["op_headers"])
    assert sig_res.status_code == 200
    assert sig_res.json().get("badge") == "SIMULATION / RECOMMENDATION ONLY"

    corridor_res = client.get("/api/v1/operator/emergency-corridors", headers=test_users["op_headers"])
    assert corridor_res.status_code == 200
    assert corridor_res.json().get("badge") == "SIMULATION / RECOMMENDATION ONLY"

    cctv_res = client.get("/api/v1/operator/cctv", headers=test_users["op_headers"])
    assert cctv_res.status_code == 200
    assert cctv_res.json().get("badge") == "DEMO / SIMULATION"
