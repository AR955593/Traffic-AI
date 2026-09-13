"""
Comprehensive Test Suite for MongoDB Authentication, Registration, Google Sign-In,
Email Verification, Password Reset, and Strict Cross-User Isolation in TrafficAI.
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from mongo_db import get_mongo_db, get_mongo_health, init_mongo_indexes
from auth import AuthManager, hash_password, verify_password, create_access_token, decode_access_token, hash_token
from user_service import UserService
from main import app

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    """Ensure indexes are created before running tests."""
    init_mongo_indexes()
    yield

def test_mongodb_connection_and_health():
    health = get_mongo_health()
    assert health["status"] == "ONLINE"
    assert health["latency_ms"] >= 0
    assert health["database"] is not None

def test_user_registration_duplicate_and_password_hashing():
    auth = AuthManager()
    email = "mongo_tester_reg@traffic.ai"
    password = "StrongPassword987!"
    name = "Mongo Tester"

    # Clean up any leftover test data
    db = get_mongo_db()
    db.users.delete_many({"email_normalized": email.lower()})

    # 1. Register User
    res = auth.register_user(email, password, name, "Kanpur, UP")
    assert "user" in res
    assert "token" in res
    assert "email_verification_token" in res
    user = res["user"]
    assert user["email"] == email
    assert user["name"] == name
    assert user["email_verified"] is False
    assert user["auth_provider"] == "local"

    # Verify password hash in MongoDB
    raw_user = db.users.find_one({"id": user["id"]})
    assert raw_user is not None
    assert "password_hash" in raw_user
    assert raw_user["password_hash"] != password
    assert verify_password(password, raw_user["password_hash"]) is True

    # 2. Duplicate registration attempt should raise KeyError (maps to 409 Conflict)
    with pytest.raises(KeyError) as exc_info:
        auth.register_user(email.upper(), "AnotherPass123", "Duplicate Name")
    assert "already exists" in str(exc_info.value).lower()

    # Cleanup
    auth.delete_account(user["id"])

def test_email_verification_flow():
    auth = AuthManager()
    email = "mongo_verify_test@traffic.ai"
    password = "VerifyPassword123"
    name = "Verification Tester"

    db = get_mongo_db()
    db.users.delete_many({"email_normalized": email.lower()})

    res = auth.register_user(email, password, name)
    token = res.get("email_verification_token")
    user_id = res["user"]["id"]
    assert token is not None

    # Token must be hashed in MongoDB, not stored in plaintext
    token_h = hash_token(token)
    token_record = db.email_verification_tokens.find_one({"token_hash": token_h})
    assert token_record is not None
    assert token_record["user_id"] == user_id
    assert token_record["used_at"] is None

    # Verify Email with valid token
    verify_res = auth.verify_email(token)
    assert verify_res["status"] == "success"
    assert verify_res["user"]["email_verified"] is True

    # Check MongoDB updated
    updated_user = db.users.find_one({"id": user_id})
    assert updated_user["email_verified"] is True

    # Attempting to use the token again must fail
    with pytest.raises(ValueError) as exc_info:
        auth.verify_email(token)
    assert "already been used" in str(exc_info.value).lower()

    # Cleanup
    auth.delete_account(user_id)

def test_login_and_jwt_authentication():
    auth = AuthManager()
    email = "mongo_login_test@traffic.ai"
    password = "CorrectPassword123"
    name = "Login Tester"

    db = get_mongo_db()
    db.users.delete_many({"email_normalized": email.lower()})

    reg = auth.register_user(email, password, name)
    user_id = reg["user"]["id"]

    # 1. Successful login
    login_res = auth.login_user(email, password)
    assert login_res["user"]["id"] == user_id
    assert "token" in login_res
    jwt_token = login_res["token"]

    # 2. Decode JWT
    payload = decode_access_token(jwt_token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["email"] == email

    # 3. Invalid password
    with pytest.raises(ValueError):
        auth.login_user(email, "WrongPassword123")

    # 4. Non-existent email
    with pytest.raises(ValueError):
        auth.login_user("nonexistent@traffic.ai", password)

    # Cleanup
    auth.delete_account(user_id)

def test_google_oauth_login_mocked():
    auth = AuthManager()
    fake_token = "fake_google_jwt_token_for_testing"
    fake_google_profile = {
        "google_subject": "google_sub_9876543210",
        "email": "google_oauth_user@example.com",
        "email_verified": True,
        "name": "Google OAuth User",
        "picture": "https://lh3.googleusercontent.com/a/fake_photo.jpg"
    }

    db = get_mongo_db()
    db.users.delete_many({"email_normalized": fake_google_profile["email"].lower()})

    # Mock verify_google_token to simulate Google OAuth ID token validation
    with patch.object(auth, "verify_google_token", return_value=fake_google_profile):
        res = auth.google_login(fake_token)
        assert "user" in res
        assert "token" in res
        user = res["user"]
        assert user["email"] == fake_google_profile["email"]
        assert user["google_subject"] == fake_google_profile["google_subject"]
        assert user["auth_provider"] == "google"
        assert user["email_verified"] is True
        assert user["avatar_url"] == fake_google_profile["picture"]

        # Logging in again with same Google account should succeed and update last_login
        res2 = auth.google_login(fake_token)
        assert res2["user"]["id"] == user["id"]

        # Cleanup
        auth.delete_account(user["id"])

def test_password_reset_flow():
    auth = AuthManager()
    email = "mongo_reset_test@traffic.ai"
    old_pass = "OldPassword123!"
    new_pass = "BrandNewPassword456!"

    db = get_mongo_db()
    db.users.delete_many({"email_normalized": email.lower()})

    reg = auth.register_user(email, old_pass, "Reset Tester")
    user_id = reg["user"]["id"]

    # Request Reset Token
    token = auth.request_password_reset(email)
    assert len(token) > 16

    # Confirm Reset with new password
    success = auth.confirm_password_reset(token, new_pass)
    assert success is True

    # Login with new password must succeed
    login_new = auth.login_user(email, new_pass)
    assert login_new["user"]["id"] == user_id

    # Login with old password must fail
    with pytest.raises(ValueError):
        auth.login_user(email, old_pass)

    # Reusing reset token must fail
    with pytest.raises(ValueError) as exc_info:
        auth.confirm_password_reset(token, "YetAnotherPassword789!")
    assert "already been used" in str(exc_info.value).lower()

    # Cleanup
    auth.delete_account(user_id)

def test_cross_user_isolation():
    """Verify strict tenant/user isolation between User Alpha and User Beta."""
    auth = AuthManager()
    user_svc = UserService()

    db = get_mongo_db()
    db.users.delete_many({"email_normalized": {"$in": ["alpha@traffic.ai", "beta@traffic.ai"]}})

    alpha = auth.register_user("alpha@traffic.ai", "AlphaPass123", "User Alpha")["user"]
    beta = auth.register_user("beta@traffic.ai", "BetaPass123", "User Beta")["user"]

    alpha_id = alpha["id"]
    beta_id = beta["id"]

    # 1. Saved Places Isolation
    place_alpha = user_svc.add_saved_place(alpha_id, "Home", "Alpha House", "Mall Road, Kanpur", 26.45, 80.33)
    place_beta = user_svc.add_saved_place(beta_id, "Office", "Beta Tech Park", "Civil Lines, Kanpur", 26.47, 80.35)

    alpha_places = user_svc.get_saved_places(alpha_id)
    beta_places = user_svc.get_saved_places(beta_id)

    assert any(p["id"] == place_alpha["id"] for p in alpha_places)
    assert not any(p["id"] == place_beta["id"] for p in alpha_places)

    assert any(p["id"] == place_beta["id"] for p in beta_places)
    assert not any(p["id"] == place_alpha["id"] for p in beta_places)

    # Beta cannot delete Alpha's place
    del_res = user_svc.delete_saved_place(beta_id, place_alpha["id"])
    assert del_res is False
    # Alpha's place still exists
    assert any(p["id"] == place_alpha["id"] for p in user_svc.get_saved_places(alpha_id))

    # 2. Saved Routes Isolation
    route_alpha = user_svc.add_saved_route(alpha_id, "Alpha Commute", "Mall Road", 26.45, 80.33, "IIT Kanpur", 26.51, 80.23)
    route_beta = user_svc.add_saved_route(beta_id, "Beta Commute", "Civil Lines", 26.47, 80.35, "Govind Nagar", 26.44, 80.31)

    alpha_routes = user_svc.get_saved_routes(alpha_id)
    beta_routes = user_svc.get_saved_routes(beta_id)

    assert any(r["id"] == route_alpha["id"] for r in alpha_routes)
    assert not any(r["id"] == route_beta["id"] for r in alpha_routes)

    # 3. Trip History Isolation
    trip_alpha = user_svc.add_trip_record(alpha_id, "Mall Road", "IIT Kanpur", 12.5, 25)
    trip_beta = user_svc.add_trip_record(beta_id, "Civil Lines", "Govind Nagar", 7.2, 16)

    alpha_trips = user_svc.get_trip_history(alpha_id)
    beta_trips = user_svc.get_trip_history(beta_id)

    assert any(t["id"] == trip_alpha["id"] for t in alpha_trips)
    assert not any(t["id"] == trip_beta["id"] for t in alpha_trips)

    # 4. Account Deletion Cascade: Purging Alpha must NOT affect Beta
    auth.delete_account(alpha_id)
    assert db.users.find_one({"id": alpha_id}) is None
    assert len(user_svc.get_saved_places(alpha_id)) == 0
    assert len(user_svc.get_saved_routes(alpha_id)) == 0
    assert len(user_svc.get_trip_history(alpha_id)) == 0

    # Beta's data must remain completely intact
    assert db.users.find_one({"id": beta_id}) is not None
    assert any(p["id"] == place_beta["id"] for p in user_svc.get_saved_places(beta_id))
    assert any(r["id"] == route_beta["id"] for r in user_svc.get_saved_routes(beta_id))
    assert any(t["id"] == trip_beta["id"] for t in user_svc.get_trip_history(beta_id))

    # Cleanup Beta
    auth.delete_account(beta_id)

def test_fastapi_endpoints_integration():
    """Test FastAPI HTTP endpoints for auth, duplicates, health, and profile."""
    test_email = "api_mongo_test@traffic.ai"
    test_pass = "TestApiPass123"

    db = get_mongo_db()
    db.users.delete_many({"email_normalized": test_email.lower()})

    # 1. Health check includes mongodb
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert "mongodb" in health_data
    assert health_data["mongodb"]["status"] == "ONLINE"

    # 2. Register
    reg_resp = client.post("/api/v1/auth/register", json={
        "email": test_email,
        "password": test_pass,
        "name": "API Tester"
    })
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert reg_data["status"] == "success"
    user_id = reg_data["user"]["id"]
    jwt_token = reg_data["token"]

    # 3. Duplicate registration -> 409 Conflict
    dup_resp = client.post("/api/v1/auth/register", json={
        "email": test_email,
        "password": "OtherPassword",
        "name": "API Tester Duplicate"
    })
    assert dup_resp.status_code == 409
    assert "already exists" in dup_resp.json()["detail"].lower()

    # 4. Login -> 200
    login_resp = client.post("/api/v1/auth/login", json={
        "email": test_email,
        "password": test_pass
    })
    assert login_resp.status_code == 200
    assert "token" in login_resp.json()

    # 5. /api/v1/auth/me with Bearer token
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["id"] == user_id

    # 6. /api/v1/auth/me without Bearer token -> 401
    unauth_resp = client.get("/api/v1/auth/me")
    assert unauth_resp.status_code == 401

    # 7. Update User Profile
    prof_resp = client.put("/api/v1/user/profile", 
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"city": "Kanpur South", "phone": "+91-9876543210"}
    )
    assert prof_resp.status_code == 200
    assert prof_resp.json()["user"]["city"] == "Kanpur South"
    assert prof_resp.json()["user"]["phone"] == "+91-9876543210"

    # 8. Delete Account
    del_resp = client.delete("/api/v1/user/account", headers={"Authorization": f"Bearer {jwt_token}"})
    assert del_resp.status_code == 200
    assert db.users.find_one({"id": user_id}) is None
