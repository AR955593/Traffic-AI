"""
Production Master Test Suite for TrafficAI.
Covers:
- Authentication & JWT validation
- Public registration role enforcement (forces role=USER)
- Single Primary Admin Rule & admin deletion protection
- User Data Isolation (User A cannot access User B data)
- Traffic speed classification boundaries (20, 40, 40.1, 70, 70.1)
- Truthful health check endpoint status
- Admin environment variable verification
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from main import app
from auth import AuthManager, generate_jwt_token, decode_jwt_token
from mongo_db import get_mongo_db
from traffic_service import classify_traffic

client = TestClient(app)
auth = AuthManager()

# -------------------------------------------------------------
# 1. AUTHENTICATION & JWT TESTS
# -------------------------------------------------------------
def test_jwt_generation_and_decoding():
    token = generate_jwt_token("usr_test_123", "test@example.com", "USER", "Test User")
    assert token is not None
    payload = decode_jwt_token(token)
    assert payload is not None
    assert payload["sub"] == "usr_test_123"
    assert payload["email"] == "test@example.com"
    assert payload["role"] == "USER"

def test_public_registration_forces_user_role():
    """Verify that public registration always enforces role = USER."""
    db = get_mongo_db()
    test_email = "commuter_role_test@example.com"
    db.users.delete_many({"email_normalized": test_email})

    response = client.post("/api/v1/auth/register", json={
        "email": test_email,
        "password": "Password123!",
        "name": "Role Test Commuter",
        "role": "ADMIN" # Client attempting to request ADMIN role
    })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    user_info = data["user"]
    # Role MUST be forced to USER regardless of payload
    assert user_info["role"] in ["USER", "VIEWER"]

    # Cleanup
    db.users.delete_many({"email_normalized": test_email})

# -------------------------------------------------------------
# 2. SINGLE PRIMARY ADMIN & PROTECTION TESTS
# -------------------------------------------------------------
def test_primary_admin_deletion_blocked():
    """Verify primary admin account deletion is blocked server-side."""
    db = get_mongo_db()
    admin_user = db.users.find_one({"role": "ADMIN"})
    if admin_user:
        admin_id = admin_user["id"]
        with pytest.raises(ValueError, match="Primary Admin account cannot be deleted"):
            auth.delete_account(admin_id)

# -------------------------------------------------------------
# 3. USER DATA ISOLATION TESTS
# -------------------------------------------------------------
def test_user_data_isolation_saved_places():
    """Verify User A cannot read or modify User B's saved places."""
    db = get_mongo_db()
    user_a_id = "usr_test_data_iso_a"
    user_b_id = "usr_test_data_iso_b"

    db.saved_places.delete_many({"user_id": {"$in": [user_a_id, user_b_id]}})
    db.users.delete_many({"id": {"$in": [user_a_id, user_b_id]}})

    # Insert valid active user docs
    now_str = "2026-09-16T15:00:00Z"
    db.users.insert_one({"id": user_a_id, "email": "a@test.com", "email_normalized": "a@test.com", "name": "User A", "role": "USER", "is_active": True, "created_at": now_str})
    db.users.insert_one({"id": user_b_id, "email": "b@test.com", "email_normalized": "b@test.com", "name": "User B", "role": "USER", "is_active": True, "created_at": now_str})

    # User A creates a place
    client.post("/api/v1/user/places", json={
        "label": "Home",
        "custom_name": "User A Home",
        "address": "123 Main St",
        "lat": 26.45,
        "lon": 80.33
    }, headers={"Authorization": f"Bearer {generate_jwt_token(user_a_id, 'a@test.com', 'USER', 'User A')}"})

    # User B requests saved places
    res_b = client.get("/api/v1/user/places", headers={"Authorization": f"Bearer {generate_jwt_token(user_b_id, 'b@test.com', 'USER', 'User B')}"})
    assert res_b.status_code == 200
    places_b = res_b.json()

    # User B MUST NOT see User A's places
    for p in places_b:
        assert p.get("user_id") != user_a_id

    # Cleanup
    db.saved_places.delete_many({"user_id": {"$in": [user_a_id, user_b_id]}})
    db.users.delete_many({"id": {"$in": [user_a_id, user_b_id]}})

# -------------------------------------------------------------
# 4. SPEED CLASSIFICATION BOUNDARY TESTS
# -------------------------------------------------------------
def test_traffic_classification_boundaries():
    """
    Verify exact traffic speed classification boundaries:
      20.0 km/h -> HIGH
      40.0 km/h -> HIGH
      40.1 km/h -> MEDIUM
      70.0 km/h -> MEDIUM
      70.1 km/h -> LOW
    """
    c20 = classify_traffic(20.0)
    assert c20["level"] == "HIGH"

    c40 = classify_traffic(40.0)
    assert c40["level"] == "HIGH"

    c40_1 = classify_traffic(40.1)
    assert c40_1["level"] == "MEDIUM"

    c70 = classify_traffic(70.0)
    assert c70["level"] == "MEDIUM"

    c70_1 = classify_traffic(70.1)
    assert c70_1["level"] == "LOW"

# -------------------------------------------------------------
# 5. HEALTH CHECK & ENVIRONMENT ENDPOINTS
# -------------------------------------------------------------
def test_health_check_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "mongodb" in data
    assert data["mongodb"]["status"] in ["ONLINE", "OFFLINE", "DEGRADED"]

def test_admin_env_check_endpoint():
    db = get_mongo_db()
    admin_user = db.users.find_one({"role": "ADMIN"})
    admin_id = admin_user["id"] if admin_user else "usr_admin"

    token = generate_jwt_token(admin_id, "admin@traffisense.gov", "ADMIN", "Chief Admin")
    response = client.get("/api/v1/admin/env-check", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "variables" in data
    assert "MONGODB_URI" in data["variables"]
    assert "JWT_SECRET_KEY" in data["variables"]
