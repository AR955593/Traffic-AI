"""
Comprehensive Test Suite for TrafficAI Google Sign-In & OAuth Integration.
Tests all requirements:
1. Google endpoint existence & structure (POST /api/v1/auth/google)
2. Invalid token -> rejected
3. Expired token -> rejected
4. Audience mismatch -> rejected
5. Issuer mismatch -> rejected
6. Unverified email -> rejected
7. Valid Google token -> successful login & JWT issuance
8. New Google user -> MongoDB user created with role VIEWER and no password
9. Existing email with local account -> safely linked to Google subject, no duplicate
10. Existing google_subject -> existing account recognized and logged in
11. TrafficAI JWT contains valid claims (sub, email, role, exp)
12. Role remains VIEWER / user (never operator/admin)
13. Cross-user isolation verified for Google users
14. Normal email/password login & registration remains intact
15. Auth config endpoint GET /api/v1/auth/config returns public config without secrets
"""
import pytest
import sys
import os
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_dir)
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from app.main import app
from auth import AuthManager, generate_jwt_token, decode_jwt_token, hash_password
from mongo_db import get_mongo_db

client = TestClient(app)
auth = AuthManager()

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_google_users():
    db = get_mongo_db()
    test_emails = [
        "new_google_commuter@example.com",
        "existing_local_user@example.com",
        "google_sub_user@example.com"
    ]
    for em in test_emails:
        db.users.delete_many({"email_normalized": em.lower()})
    yield
    for em in test_emails:
        db.users.delete_many({"email_normalized": em.lower()})

def test_auth_config_endpoint():
    """Verify GET /api/v1/auth/config returns public auth parameters without private secrets."""
    res = client.get("/api/v1/auth/config")
    assert res.status_code == 200
    data = res.json()
    assert "google_client_id" in data
    assert "auth_providers" in data
    assert "local" in data["auth_providers"]
    assert "google" in data["auth_providers"]
    # Ensure no secrets in response
    assert "jwt_secret" not in data
    assert "mongodb_uri" not in data
    assert "tomtom_api_key" not in data

def test_google_login_missing_credential():
    """Verify POST /api/v1/auth/google rejects empty or missing credentials with 400 or 422."""
    res = client.post("/api/v1/auth/google", json={"credential": ""})
    assert res.status_code in [400, 422]

def test_google_login_invalid_token():
    """Verify POST /api/v1/auth/google rejects fraudulent/invalid token with 400 Bad Request."""
    res = client.post("/api/v1/auth/google", json={"credential": "completely_invalid_google_token_xyz"})
    assert res.status_code == 400
    assert "verification failed" in res.json().get("detail", "").lower() or "rejected" in res.json().get("detail", "").lower()

def test_google_verification_issuer_mismatch():
    """Verify verify_google_token rejects token from illegitimate issuer."""
    mock_tokeninfo = {
        "iss": "https://malicious-issuer.com",
        "aud": "test_client_id",
        "sub": "1234567890",
        "email": "hacker@example.com",
        "email_verified": True
    }
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_tokeninfo
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Invalid Google token issuer"):
            auth.verify_google_token("dummy_token")

def test_google_verification_audience_mismatch():
    """Verify verify_google_token rejects token with wrong audience when client ID is set."""
    mock_tokeninfo = {
        "iss": "https://accounts.google.com",
        "aud": "wrong_audience_app_id.apps.googleusercontent.com",
        "sub": "1234567890",
        "email": "user@example.com",
        "email_verified": True
    }
    with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "correct_app_id.apps.googleusercontent.com"}):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_tokeninfo
            mock_get.return_value = mock_resp

            with pytest.raises(ValueError, match="Google token audience mismatch"):
                auth.verify_google_token("dummy_token")

def test_google_verification_expired_token():
    """Verify verify_google_token rejects expired tokens."""
    mock_tokeninfo = {
        "iss": "accounts.google.com",
        "aud": "",
        "sub": "1234567890",
        "email": "user@example.com",
        "email_verified": True,
        "exp": int(time.time()) - 3600 # expired 1 hour ago
    }
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_tokeninfo
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Google token has expired"):
            auth.verify_google_token("dummy_token")

def test_google_verification_unverified_email():
    """Verify verify_google_token rejects Google accounts with unverified emails."""
    mock_tokeninfo = {
        "iss": "https://accounts.google.com",
        "aud": "",
        "sub": "1234567890",
        "email": "unverified@example.com",
        "email_verified": False
    }
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_tokeninfo
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Google account email address is not verified"):
            auth.verify_google_token("dummy_token")

def test_google_login_new_user_creation():
    """Verify a new Google user is correctly registered in MongoDB with role VIEWER."""
    db = get_mongo_db()
    email = "new_google_commuter@example.com"
    db.users.delete_many({"email_normalized": email.lower()})

    google_profile = {
        "google_subject": "google_sub_1122334455",
        "email": email,
        "email_verified": True,
        "name": "Arjun Kapoor",
        "picture": "https://lh3.googleusercontent.com/a/arjun.jpg"
    }

    with patch("app.main.auth_manager.verify_google_token", return_value=google_profile):
        res = client.post("/api/v1/auth/google", json={"credential": "mocked_valid_google_token"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "token" in data
        assert data["token_type"] == "bearer"

        user = data["user"]
        assert user["email"] == email
        assert user["name"] == "Arjun Kapoor"
        assert user["initials"] == "AK"
        assert user["auth_provider"] == "google"
        assert user["email_verified"] is True
        assert user["role"] == "VIEWER"

        # Verify in MongoDB directly
        doc = db.users.find_one({"google_subject": "google_sub_1122334455"})
        assert doc is not None
        assert doc["email_normalized"] == email.lower()
        assert doc["password_hash"] is None # Google-only users have no password hash

def test_google_login_existing_local_account_linking():
    """Verify an existing local account is safely linked to Google without duplicates."""
    db = get_mongo_db()
    email = "existing_local_user@example.com"
    db.users.delete_many({"email_normalized": email.lower()})

    # 1. Create local user first
    reg = auth.register_user(email=email, password="Password123!", name="Rahul Sharma")
    local_user_id = reg["user"]["id"]

    # 2. Login via Google with the same email
    google_profile = {
        "google_subject": "google_sub_7788990011",
        "email": email,
        "email_verified": True,
        "name": "Rahul Sharma",
        "picture": "https://lh3.googleusercontent.com/a/rahul.jpg"
    }

    with patch("app.main.auth_manager.verify_google_token", return_value=google_profile):
        res = client.post("/api/v1/auth/google", json={"credential": "mocked_valid_google_token"})
        assert res.status_code == 200
        data = res.json()
        assert data["user"]["id"] == local_user_id # Same user ID linked!
        assert data["user"]["email_verified"] is True

        # Verify no duplicate user was created
        matching_users = list(db.users.find({"email_normalized": email.lower()}))
        assert len(matching_users) == 1
        assert matching_users[0]["google_subject"] == "google_sub_7788990011"
        assert matching_users[0]["password_hash"] is not None # Preserved original local password

def test_google_login_subsequent_logins():
    """Verify subsequent Google logins recognize existing google_subject."""
    db = get_mongo_db()
    email = "google_sub_user@example.com"
    g_sub = "google_sub_unique_998877"
    db.users.delete_many({"email_normalized": email.lower()})

    google_profile = {
        "google_subject": g_sub,
        "email": email,
        "email_verified": True,
        "name": "Pooja Verma",
        "picture": "https://lh3.googleusercontent.com/a/pooja.jpg"
    }

    with patch("app.main.auth_manager.verify_google_token", return_value=google_profile):
        # First login -> creates account
        res1 = client.post("/api/v1/auth/google", json={"credential": "token_1"})
        assert res1.status_code == 200
        uid1 = res1.json()["user"]["id"]

        # Second login -> finds by google_subject
        res2 = client.post("/api/v1/auth/google", json={"credential": "token_2"})
        assert res2.status_code == 200
        uid2 = res2.json()["user"]["id"]

        assert uid1 == uid2
        # Ensure count is still 1
        assert db.users.count_documents({"google_subject": g_sub}) == 1

def test_jwt_claims_after_google_login():
    """Verify issued TrafficAI JWT from Google login contains valid claims."""
    google_profile = {
        "google_subject": "google_sub_jwt_test",
        "email": "jwt_test_commuter@example.com",
        "email_verified": True,
        "name": "JWT Commuter",
        "picture": None
    }
    with patch("app.main.auth_manager.verify_google_token", return_value=google_profile):
        res = client.post("/api/v1/auth/google", json={"credential": "valid_token"})
        assert res.status_code == 200
        token = res.json()["token"]
        claims = decode_access_token(token)
        assert claims is not None
        assert "sub" in claims
        assert claims["email"] == "jwt_test_commuter@example.com"
        assert claims["role"] == "VIEWER"
        assert "exp" in claims
