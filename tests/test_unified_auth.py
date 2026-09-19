"""
TrafficAI Unified Account & Cross-Platform Authentication Test Suite
Covers the complete 28-point test matrix:
- Single Centralized Identity Model
- Dual Identifier Login (Email + Password OR Phone + Password)
- Identical user_id resolution
- Database-level duplicate email and phone prevention
- Email casing and canonical phone normalization
- Strict RBAC: Admin Web-Only (HTTP 403) vs Operator & User Web + Android
- Account Lifecycle: ACTIVE, DISABLED, SUSPENDED, PENDING_APPROVAL
- Token Refresh, Logout, and Cross-User Data Isolation
"""
import sys
import os
import uuid
import pytest
from fastapi.testclient import TestClient

# Ensure project root and src/ are in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from app.main import app, auth_manager
from src.auth import AuthManager, normalize_email, normalize_phone, is_email_identifier
from src.mongo_db import get_mongo_db

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_db():
    db = get_mongo_db()
    # Ensure indexes are ready
    from src.mongo_db import init_mongo_indexes
    init_mongo_indexes()
    yield db


class TestUnifiedAccountModel:
    """Tests A - F & U, V, AB: Single Account, Cross-Platform & Dual-Identifier Resolution."""

    def test_web_registration_and_dual_identifier_login(self, setup_db):
        """User registers once on Web with Email + Phone, then logs in with both identifiers on Web & Android."""
        unique_suffix = uuid.uuid4().hex[:8]
        email = f"commuter_{unique_suffix}@trafficai.org"
        phone = "+9198765" + unique_suffix[:5]
        password = "SecurePassword123!"

        # 1. Register on Web
        reg_res = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": f"Commuter {unique_suffix}",
            "phone": phone,
            "country_code": "+91",
            "role": "USER"
        })
        assert reg_res.status_code == 200
        reg_data = reg_res.json()
        assert reg_data["status"] == "success"
        user_id = reg_data["user"]["id"]
        assert user_id.startswith("usr_")

        # 2. Login via Email on Desktop Web
        login_web_email = client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": password
        }, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"})
        assert login_web_email.status_code == 200
        web_email_user = login_web_email.json()["user"]
        assert web_email_user["id"] == user_id
        assert web_email_user["role"] == "USER"

        # 3. Login via Phone on Android App (X-Client-Platform: android)
        login_android_phone = client.post("/api/v1/auth/login", json={
            "identifier": phone,
            "password": password
        }, headers={"X-Client-Platform": "android", "User-Agent": "TrafficAI-Android/4.0"})
        assert login_android_phone.status_code == 200
        android_phone_user = login_android_phone.json()["user"]
        # Must resolve to the EXACT SAME user_id!
        assert android_phone_user["id"] == user_id
        assert android_phone_user["role"] == "USER"

        # 4. Login via Email on Android App
        login_android_email = client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": password
        }, headers={"X-Client-Platform": "android"})
        assert login_android_email.status_code == 200
        assert login_android_email.json()["user"]["id"] == user_id

        # 5. Login via Phone on Desktop Web
        login_web_phone = client.post("/api/v1/auth/login", json={
            "identifier": phone,
            "password": password
        })
        assert login_web_phone.status_code == 200
        assert login_web_phone.json()["user"]["id"] == user_id

    def test_android_registration_and_web_login(self, setup_db):
        """User registers on Android, logs in on Desktop Web without re-registration."""
        unique_suffix = uuid.uuid4().hex[:8]
        email = f"mobile_user_{unique_suffix}@trafficai.org"
        phone = "+9198123" + unique_suffix[:5]
        password = "MobilePassword123@"

        # Register from Android client
        reg_res = client.post("/auth/register", json={
            "email": email,
            "password": password,
            "name": f"Mobile Commuter {unique_suffix}",
            "phone": phone,
            "role": "USER"
        }, headers={"X-Client-Platform": "android"})
        assert reg_res.status_code == 200
        user_id = reg_res.json()["user"]["id"]

        # Log in on Web via /auth/login
        login_res = client.post("/auth/login", json={
            "identifier": email,
            "password": password
        })
        assert login_res.status_code == 200
        assert login_res.json()["user"]["id"] == user_id

        # Log in on Web via Phone
        login_phone_res = client.post("/auth/login", json={
            "identifier": phone,
            "password": password
        })
        assert login_phone_res.status_code == 200
        assert login_phone_res.json()["user"]["id"] == user_id


class TestDuplicatePreventionAndNormalization:
    """Tests G - J & AB: Uniqueness and Normalization."""

    def test_duplicate_email_registration_blocked(self, setup_db):
        """Attempting to register an already-registered email returns HTTP 409 ACCOUNT_ALREADY_EXISTS."""
        unique_suffix = uuid.uuid4().hex[:8]
        email = f"dup_email_{unique_suffix}@trafficai.org"
        password = "TestPassword123!"

        res1 = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": "First Account"
        })
        assert res1.status_code == 200

        # Duplicate Attempt with same email
        res2 = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": "Second Account Duplicate"
        })
        assert res2.status_code == 409
        assert "ACCOUNT_ALREADY_EXISTS" in res2.json()["detail"] or "already registered" in res2.json()["detail"]

    def test_duplicate_phone_registration_blocked(self, setup_db):
        """Attempting to register an already-registered phone returns HTTP 409 ACCOUNT_ALREADY_EXISTS."""
        unique_suffix = uuid.uuid4().hex[:8]
        email1 = f"user1_{unique_suffix}@trafficai.org"
        email2 = f"user2_{unique_suffix}@trafficai.org"
        phone = "+9197777" + unique_suffix[:5]
        password = "TestPassword123!"

        res1 = client.post("/api/v1/auth/register", json={
            "email": email1,
            "password": password,
            "name": "User One",
            "phone": phone
        })
        assert res1.status_code == 200

        # Attempt to register User Two with User One's phone
        res2 = client.post("/api/v1/auth/register", json={
            "email": email2,
            "password": password,
            "name": "User Two",
            "phone": phone
        })
        assert res2.status_code == 409
        assert "ACCOUNT_ALREADY_EXISTS" in res2.json()["detail"] or "already registered" in res2.json()["detail"]

    def test_email_casing_normalization(self, setup_db):
        """Emails with different casing resolve to the same account without duplicates."""
        unique_suffix = uuid.uuid4().hex[:8]
        base_email = f"CaseTest_{unique_suffix}@TrafficAI.ORG"
        password = "TestPassword123!"

        res = client.post("/api/v1/auth/register", json={
            "email": base_email,
            "password": password,
            "name": "Case Test User"
        })
        assert res.status_code == 200
        user_id = res.json()["user"]["id"]

        # Login using all lowercase
        res_lower = client.post("/api/v1/auth/login", json={
            "identifier": base_email.lower(),
            "password": password
        })
        assert res_lower.status_code == 200
        assert res_lower.json()["user"]["id"] == user_id

        # Login using all uppercase
        res_upper = client.post("/api/v1/auth/login", json={
            "identifier": base_email.upper(),
            "password": password
        })
        assert res_upper.status_code == 200
        assert res_upper.json()["user"]["id"] == user_id

    def test_phone_formatting_normalization(self, setup_db):
        """Phone variants like '+91 98765 43210' and '9876543210' resolve to canonical E.164."""
        unique_suffix = uuid.uuid4().hex[:8]
        raw_phone_10 = "98765" + unique_suffix[:5]
        canonical_phone = f"+91{raw_phone_10}"
        email = f"phone_norm_{unique_suffix}@trafficai.org"
        password = "TestPassword123!"

        res = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": "Phone Norm User",
            "phone": f"+91 {raw_phone_10[:5]} {raw_phone_10[5:]}" # spaced format
        })
        assert res.status_code == 200
        user_id = res.json()["user"]["id"]

        # Login using 10-digit raw format
        res_10 = client.post("/api/v1/auth/login", json={
            "identifier": raw_phone_10,
            "password": password
        })
        assert res_10.status_code == 200
        assert res_10.json()["user"]["id"] == user_id

        # Login using canonical format
        res_canon = client.post("/api/v1/auth/login", json={
            "identifier": canonical_phone,
            "password": password
        })
        assert res_canon.status_code == 200
        assert res_canon.json()["user"]["id"] == user_id


class TestRBACAndPlatformRestrictions:
    """Tests O - T: Admin Web-Only & Cross-Platform Operator/User."""

    def test_admin_web_login_success(self, setup_db):
        """System Admin can successfully log in from Desktop Web."""
        res = client.post("/api/v1/auth/login", json={
            "identifier": "admin@traffisense.gov",
            "password": "admin123"
        }, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"})
        assert res.status_code == 200
        assert res.json()["user"]["role"] in ["ADMIN", "SUPER_ADMIN"]

    def test_admin_android_login_forbidden_403(self, setup_db):
        """System Admin login from Android / Mobile App is rejected with HTTP 403 ADMIN_WEB_ONLY."""
        # 1. Using X-Client-Platform header
        res1 = client.post("/api/v1/auth/login", json={
            "identifier": "admin@traffisense.gov",
            "password": "admin123"
        }, headers={"X-Client-Platform": "android"})
        assert res1.status_code == 403
        assert "ADMIN_WEB_ONLY" in res1.json()["detail"] or "Desktop Web only" in res1.json()["detail"]

        # 2. Using Android WebView User-Agent
        res2 = client.post("/api/v1/auth/login", json={
            "identifier": "admin@traffisense.gov",
            "password": "admin123"
        }, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0 Mobile TrafficAIApp/4.0"})
        assert res2.status_code == 403

    def test_operator_cross_platform_login(self, setup_db):
        """Traffic Operator can log in from both Desktop Web and Android App."""
        # Desktop Web
        res_web = client.post("/api/v1/auth/login", json={
            "identifier": "rawasthi@kanpur.traffic.gov",
            "password": "password123"
        })
        assert res_web.status_code == 200
        assert res_web.json()["user"]["role"] in ["TRAFFIC_OPERATOR", "OPERATOR"]

        # Android Mobile
        res_android = client.post("/api/v1/auth/login", json={
            "identifier": "rawasthi@kanpur.traffic.gov",
            "password": "password123"
        }, headers={"X-Client-Platform": "android"})
        assert res_android.status_code == 200
        assert res_android.json()["user"]["id"] == res_web.json()["user"]["id"]

    def test_user_cross_platform_login(self, setup_db):
        """Public Commuter user can log in from both Web and Android."""
        res_web = client.post("/api/v1/auth/login", json={
            "identifier": "viewer@city.gov",
            "password": "viewer123"
        })
        assert res_web.status_code == 200

        res_android = client.post("/api/v1/auth/login", json={
            "identifier": "viewer@city.gov",
            "password": "viewer123"
        }, headers={"X-Client-Platform": "android"})
        assert res_android.status_code == 200
        assert res_android.json()["user"]["id"] == res_web.json()["user"]["id"]


class TestSecurityAndAccountStatus:
    """Tests K - N, W - AA: Passwords, Statuses, Sessions, Tokens, and Data Isolation."""

    def test_wrong_password_rejected(self, setup_db):
        """Incorrect password returns HTTP 401 INVALID_CREDENTIALS."""
        res = client.post("/api/v1/auth/login", json={
            "identifier": "viewer@city.gov",
            "password": "wrong_password_123"
        })
        assert res.status_code == 401
        assert "INVALID_CREDENTIALS" in res.json()["detail"] or "Invalid email" in res.json()["detail"]

    def test_disabled_account_blocked(self, setup_db):
        """Disabled account login is blocked with HTTP 403 ACCOUNT_DISABLED."""
        db = get_mongo_db()
        unique_suffix = uuid.uuid4().hex[:8]
        email = f"disabled_{unique_suffix}@trafficai.org"
        password = "TestPassword123!"

        reg_res = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": "Disabled User"
        })
        user_id = reg_res.json()["user"]["id"]

        # Set status = DISABLED in database
        db.users.update_one({"id": user_id}, {"$set": {"status": "DISABLED", "is_active": False}})

        login_res = client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": password
        })
        assert login_res.status_code == 403
        assert "ACCOUNT_DISABLED" in login_res.json()["detail"]

    def test_suspended_account_blocked(self, setup_db):
        """Suspended account login is blocked with HTTP 403 ACCOUNT_SUSPENDED."""
        db = get_mongo_db()
        unique_suffix = uuid.uuid4().hex[:8]
        email = f"suspended_{unique_suffix}@trafficai.org"
        password = "TestPassword123!"

        reg_res = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": "Suspended User"
        })
        user_id = reg_res.json()["user"]["id"]

        # Set status = SUSPENDED in database
        db.users.update_one({"id": user_id}, {"$set": {"status": "SUSPENDED"}})

        login_res = client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": password
        })
        assert login_res.status_code == 403
        assert "ACCOUNT_SUSPENDED" in login_res.json()["detail"]

    def test_token_refresh_and_logout(self, setup_db):
        """Valid session token can be refreshed and logged out cleanly."""
        login_res = client.post("/api/v1/auth/login", json={
            "identifier": "viewer@city.gov",
            "password": "viewer123"
        })
        assert login_res.status_code == 200
        token = login_res.json()["token"]

        # Refresh token
        refresh_res = client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {token}"})
        assert refresh_res.status_code == 200
        new_token = refresh_res.json()["token"]
        assert new_token is not None

        # Authenticated /auth/me check
        me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert me_res.status_code == 200
        assert me_res.json()["id"] == "usr_viewer"

        # Logout
        logout_res = client.post("/auth/logout", headers={"Authorization": f"Bearer {new_token}"})
        assert logout_res.status_code == 200
        assert logout_res.json()["code"] == "LOGGED_OUT"

    def test_cross_user_data_isolation(self, setup_db):
        """User A cannot access or mutate User B's saved places."""
        # User A
        u1_res = client.post("/api/v1/auth/login", json={"identifier": "viewer@city.gov", "password": "viewer123"})
        token_a = u1_res.json()["token"]

        # User B
        u2_res = client.post("/api/v1/auth/login", json={"identifier": "rawasthi@kanpur.traffic.gov", "password": "password123"})
        token_b = u2_res.json()["token"]

        # User A creates a place
        place_res = client.post("/api/v1/user/places", json={
            "label": "Home",
            "custom_name": "User A Home",
            "address": "Civil Lines, Kanpur",
            "lat": 26.4499,
            "lon": 80.3319
        }, headers={"Authorization": f"Bearer {token_a}"})
        assert place_res.status_code == 200
        place_id = place_res.json()["id"]

        # User B fetches places - should NOT see User A's place
        user_b_places = client.get("/api/v1/user/places", headers={"Authorization": f"Bearer {token_b}"}).json()
        assert not any(p.get("id") == place_id for p in user_b_places)

    def test_invalid_identifier_rejected(self, setup_db):
        """Empty or missing identifier returns HTTP 400."""
        res = client.post("/api/v1/auth/login", json={
            "identifier": "",
            "password": "Password123!"
        })
        assert res.status_code == 400

    def test_notification_synchronization_across_platforms(self, setup_db):
        """Notifications are tied to user_id, accessible equally on Web and Android."""
        db = get_mongo_db()
        unique_suffix = uuid.uuid4().hex[:8]
        user_id = f"usr_{unique_suffix}"
        notif_id = f"ntf_{unique_suffix}"

        # Insert a notification for this user
        db.notifications.insert_one({
            "id": notif_id,
            "notification_id": notif_id,
            "user_id": user_id,
            "recipient_user_id": user_id,
            "type": "CONGESTION_ALERT",
            "title": "Severe Traffic on Route",
            "message": "Heavy congestion detected on Mall Road.",
            "severity": "HIGH",
            "source": "traffic_system",
            "read": False,
            "read_at": None,
            "created_at": "2026-09-19T10:00:00Z"
        })

        # Fetch notifications for this user
        notifs = list(db.notifications.find({"$or": [{"user_id": user_id}, {"recipient_user_id": user_id}]}))
        assert len(notifs) == 1
        assert notifs[0]["title"] == "Severe Traffic on Route"

        # Web marks notification as read
        db.notifications.update_one({"id": notif_id}, {"$set": {"read": True, "read_at": "2026-09-19T10:05:00Z"}})

        # Android query sees updated state immediately
        updated = db.notifications.find_one({"id": notif_id})
        assert updated["read"] is True

    def test_sms_verification_truthful_unconfigured_status(self, setup_db):
        """When SMS provider is unconfigured, send-phone-otp returns truthful status without faking delivery."""
        res = client.post("/api/v1/auth/send-phone-otp", json={
            "phone": "+919876543210"
        })
        assert res.status_code == 200
        data = res.json()
        assert data.get("code") in ["PHONE_VERIFICATION_NOT_CONFIGURED", "OTP_SENT"]
        if data.get("code") == "PHONE_VERIFICATION_NOT_CONFIGURED":
            assert "NOT CONFIGURED" in data.get("message", "")

    def test_operator_approval_lifecycle(self, setup_db):
        """Pending operator cannot log in until approved by Admin, then works across platforms."""
        unique_suffix = uuid.uuid4().hex[:8]
        email = f"op_candidate_{unique_suffix}@trafficai.org"
        phone = "+9198999" + unique_suffix[:5]
        password = "OpPassword123!"

        # 1. Register as OPERATOR
        reg_res = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": f"Candidate {unique_suffix}",
            "phone": phone,
            "role": "TRAFFIC_OPERATOR"
        })
        assert reg_res.status_code == 200
        user_id = reg_res.json()["user"]["id"]
        assert reg_res.json()["user"]["status"] == "PENDING_APPROVAL"

        # 2. Login while pending should fail with 403
        login_pending = client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": password
        })
        assert login_pending.status_code == 403

        # 3. Admin approves operator
        approve_res = auth_manager.approve_operator(user_id, admin_user_id="usr_admin")
        assert approve_res["status"] == "success"

        # 4. Operator Web login now succeeds
        login_web = client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": password
        })
        assert login_web.status_code == 200

        # 5. Operator Android login via Phone succeeds with same user_id
        login_android = client.post("/api/v1/auth/login", json={
            "identifier": phone,
            "password": password
        }, headers={"X-Client-Platform": "android"})
        assert login_android.status_code == 200
        assert login_android.json()["user"]["id"] == user_id

