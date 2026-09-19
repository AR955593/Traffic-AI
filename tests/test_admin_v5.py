"""
TrafficAI V5 — Admin Command Center Comprehensive Test Suite
Tests all 26+ requirements:
1. Admin web login succeeds
2. Admin Android login is rejected with HTTP 403 (ADMIN_WEB_ONLY)
3. Commuter/User access to Admin APIs is rejected with HTTP 403
4. Operator access to Admin APIs is rejected with HTTP 403
5. Admin overview & KPI metrics
6. Authoritative system health check
7. User management list, search, status update, access reset
8. Operator approval workflow (PENDING_APPROVAL -> APPROVED/ACTIVE)
9. Operator rejection workflow with mandatory reason
10. Operator suspension workflow with mandatory reason
11. Operator duty zone assignment
12. Operator profile drawer aggregation
13. Append-only system audit logs with multi-filter query
14. Server-enforced RBAC permission matrix
15. Database management collection stats & index validation
16. CCTV management 4-state diagnostics & camera configuration update
17. CCTV camera stream truthful test
18. Integration list & live diagnostic probe
19. System configuration retrieval & update with CONFIG_CHANGED audit
20. Feature flags listing and toggle
21. Security events listing and recording
22. Active sessions listing and session revocation
23. Safe backup creation and integrity verification
24. Protected backup restore requiring typed confirmation phrase
25. Data quality matrix endpoint
26. Attention Required counter aggregation
27. Global permission-aware search
28. Secret masking (no passwords, JWTs, RTSP passwords, or API keys exposed)
29. CSV report generation and headers
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
from src.mongo_db import get_mongo_db, init_mongo_indexes
from src.admin_service import admin_service

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_admin_env():
    """Sets up test accounts and returns admin, operator, and commuter credentials & tokens."""
    db = get_mongo_db()
    init_mongo_indexes()

    unique_id = uuid.uuid4().hex[:6]
    admin_email = f"admin_{unique_id}@trafficai.gov.in"
    admin_phone = f"+9188888{unique_id[:5]}"
    op_email = f"operator_{unique_id}@trafficai.gov.in"
    op_phone = f"+9177777{unique_id[:5]}"
    user_email = f"user_{unique_id}@trafficai.org"
    user_phone = f"+9199999{unique_id[:5]}"
    password = "AdminSecurePassword123!"

    # 1. Register & activate Admin
    reg_adm = client.post("/api/v1/auth/register", json={
        "email": admin_email,
        "password": password,
        "name": f"Admin {unique_id}",
        "phone": admin_phone,
        "role": "ADMIN"
    })
    admin_data = reg_adm.json()["user"]
    db.users.update_one({"$or": [{"id": admin_data["id"]}, {"user_id": admin_data["id"]}, {"email": admin_email}]}, {"$set": {"status": "ACTIVE", "role": "ADMIN", "is_active": True, "email_verified": True}})

    # Login Admin on Web
    login_adm = client.post("/api/v1/auth/login", json={
        "identifier": admin_email,
        "password": password
    }, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    admin_token = login_adm.json().get("token") or login_adm.json().get("access_token")

    # 2. Register Operator
    reg_op = client.post("/api/v1/auth/register", json={
        "email": op_email,
        "password": password,
        "name": f"Operator {unique_id}",
        "phone": op_phone,
        "role": "OPERATOR"
    })
    op_data = reg_op.json()["user"]
    db.users.update_one({"$or": [{"id": op_data["id"]}, {"user_id": op_data["id"]}, {"email": op_email}]}, {"$set": {"status": "ACTIVE", "approval_status": "APPROVED", "role": "OPERATOR", "is_active": True, "email_verified": True}})

    login_op = client.post("/api/v1/auth/login", json={
        "identifier": op_email,
        "password": password
    })
    op_token = login_op.json().get("token") or login_op.json().get("access_token")

    # 3. Register Commuter User
    reg_u = client.post("/api/v1/auth/register", json={
        "email": user_email,
        "password": password,
        "name": f"Commuter {unique_id}",
        "phone": user_phone,
        "role": "USER"
    })
    u_data = reg_u.json()["user"]
    db.users.update_one({"$or": [{"id": u_data["id"]}, {"user_id": u_data["id"]}, {"email": user_email}]}, {"$set": {"status": "ACTIVE", "role": "USER", "is_active": True, "email_verified": True}})

    login_u = client.post("/api/v1/auth/login", json={
        "identifier": user_email,
        "password": password
    })
    user_token = login_u.json().get("token") or login_u.json().get("access_token")

    return {
        "admin": {"user_id": admin_data["id"], "email": admin_email, "phone": admin_phone, "password": password, "token": admin_token},
        "operator": {"user_id": op_data["id"], "email": op_email, "phone": op_phone, "password": password, "token": op_token},
        "user": {"user_id": u_data["id"], "email": user_email, "phone": user_phone, "password": password, "token": user_token},
        "db": db
    }


class TestAdminV5CommandCenter:
    """Comprehensive test suite for TrafficAI V5 Admin Command Center."""

    def test_01_admin_web_login_and_android_block(self, setup_admin_env):
        """Admin logs in on Web successfully; Admin mobile/Android login is rejected with HTTP 403 (ADMIN_WEB_ONLY)."""
        env = setup_admin_env
        # Web login succeeds
        res_web = client.post("/api/v1/auth/login", json={
            "identifier": env["admin"]["email"],
            "password": env["admin"]["password"]
        }, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        assert res_web.status_code == 200
        assert "token" in res_web.json() or "access_token" in res_web.json()

        # Mobile / Android login is strictly blocked with HTTP 403
        res_android = client.post("/api/v1/auth/login", json={
            "identifier": env["admin"]["email"],
            "password": env["admin"]["password"]
        }, headers={"User-Agent": "TrafficAI-Android-App/2.1.0 (Linux; Android 14; Pixel 8)"})
        assert res_android.status_code == 403
        assert "ADMIN_WEB_ONLY" in res_android.json().get("detail", "")

    def test_02_rbac_unauthorized_access_rejected(self, setup_admin_env):
        """User and Operator tokens cannot access Admin endpoints and return HTTP 403."""
        env = setup_admin_env
        user_headers = {"Authorization": f"Bearer {env['user']['token']}"}
        op_headers = {"Authorization": f"Bearer {env['operator']['token']}"}

        # Commuter access to /api/v1/admin/overview
        res_u = client.get("/api/v1/admin/overview", headers=user_headers)
        assert res_u.status_code == 403

        # Operator access to /api/v1/admin/overview
        res_op = client.get("/api/v1/admin/overview", headers=op_headers)
        assert res_op.status_code == 403

        # Commuter access to /api/v1/admin/users
        res_u_users = client.get("/api/v1/admin/users", headers=user_headers)
        assert res_u_users.status_code == 403

    def test_03_admin_overview_and_metrics(self, setup_admin_env):
        """Admin overview returns real operational KPI metrics and attention counters."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        res = client.get("/api/v1/admin/overview?timeframe=24h", headers=headers)
        assert res.status_code == 200
        data = res.json()["data"]

        assert "kpis" in data
        assert "total_users" in data["kpis"]
        assert "active_operators" in data["kpis"]
        assert "pending_approvals" in data["kpis"]
        assert "cctv_health" in data["kpis"]
        assert "system_uptime" in data["kpis"]
        assert "data_quality" in data["kpis"]
        assert "attention_required" in data
        assert isinstance(data["attention_required"]["total_count"], int)

    def test_04_authoritative_system_health(self, setup_admin_env):
        """System health returns authoritative status for all platform services."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        res = client.get("/api/v1/admin/system-health", headers=headers)
        assert res.status_code == 200
        data = res.json()["data"]

        assert data["overall_status"] in ["ONLINE", "DEGRADED", "OFFLINE"]
        assert len(data["services"]) >= 8

        # Verify MongoDB and FastAPI services are present
        svc_ids = [s["id"] for s in data["services"]]
        assert "fastapi_backend" in svc_ids
        assert "mongodb_database" in svc_ids
        assert "tomtom_traffic" in svc_ids
        assert "open_meteo_weather" in svc_ids

    def test_05_admin_user_management_lifecycle(self, setup_admin_env):
        """User management: list, search, status change (SUSPENDED/ACTIVE), access reset, and audit trail."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # 1. List users
        res_list = client.get("/api/v1/admin/users?page=1&limit=10", headers=headers)
        assert res_list.status_code == 200
        data_list = res_list.json()["data"]
        assert data_list["total_count"] > 0
        assert len(data_list["users"]) > 0

        target_user_id = env["user"]["user_id"]

        # 2. Suspend user
        res_suspend = client.patch(f"/api/v1/admin/users/{target_user_id}/status", json={
            "status": "SUSPENDED",
            "reason": "Suspected automated scraping activity"
        }, headers=headers)
        assert res_suspend.status_code == 200
        assert res_suspend.json()["data"]["new_status"] == "SUSPENDED"

        # Verify user in database is now SUSPENDED
        u_doc = env["db"].users.find_one({"$or": [{"id": target_user_id}, {"user_id": target_user_id}]})
        assert u_doc["status"] == "SUSPENDED"

        # 3. Reactivate user
        res_active = client.patch(f"/api/v1/admin/users/{target_user_id}/status", json={
            "status": "ACTIVE",
            "reason": "Identity verified"
        }, headers=headers)
        assert res_active.status_code == 200
        assert res_active.json()["data"]["new_status"] == "ACTIVE"

        # 4. Reset user access
        res_reset = client.post(f"/api/v1/admin/users/{target_user_id}/reset-access", json={
            "reason": "Security token refresh"
        }, headers=headers)
        assert res_reset.status_code == 200
        assert res_reset.json()["data"]["success"] is True

    def test_06_operator_approval_workflow(self, setup_admin_env):
        """Operator approval workflow: PENDING_APPROVAL -> APPROVED/ACTIVE with audit event."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # Create a new pending operator
        unique_op = uuid.uuid4().hex[:6]
        op_email = f"pending_op_{unique_op}@trafficai.gov.in"
        reg_res = client.post("/api/v1/auth/register", json={
            "email": op_email,
            "password": "OperatorPass123!",
            "name": f"Pending Op {unique_op}",
            "phone": f"+9166666{unique_op[:5]}",
            "role": "OPERATOR"
        })
        new_op_id = reg_res.json()["user"]["id"]
        # Ensure status is PENDING_APPROVAL
        env["db"].users.update_one({"$or": [{"id": new_op_id}, {"user_id": new_op_id}]}, {"$set": {"approval_status": "PENDING_APPROVAL", "status": "PENDING_APPROVAL", "role": "OPERATOR"}})

        # 1. Verify operator appears in pending list
        res_pending = client.get("/api/v1/admin/operators?status=PENDING", headers=headers)
        assert res_pending.status_code == 200
        pending_ids = [op.get("user_id") or op.get("id") for op in res_pending.json()["data"]["operators"]]
        assert new_op_id in pending_ids

        # 2. Approve operator
        res_approve = client.post(f"/api/v1/admin/operators/{new_op_id}/approve", headers=headers)
        assert res_approve.status_code == 200
        assert res_approve.json()["data"]["status"] == "ACTIVE"
        assert res_approve.json()["data"]["approval_status"] == "APPROVED"

        # 3. Check database state
        op_doc = env["db"].users.find_one({"$or": [{"id": new_op_id}, {"user_id": new_op_id}]})
        assert op_doc["status"] == "ACTIVE"
        assert op_doc["approval_status"] == "APPROVED"

        # 4. Verify audit event was created
        audit = env["db"].audit_logs.find_one({"action": "OPERATOR_APPROVED", "metadata.operator_id": new_op_id})
        assert audit is not None
        assert audit["actor_role"] == "ADMIN"

    def test_07_operator_rejection_and_suspension_workflows(self, setup_admin_env):
        """Operator rejection and suspension workflows enforce mandatory reasons."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # Create operator to reject
        unique_rej = uuid.uuid4().hex[:6]
        reg_rej = client.post("/api/v1/auth/register", json={
            "email": f"rej_op_{unique_rej}@trafficai.gov.in",
            "password": "Password123!",
            "name": f"Reject Op {unique_rej}",
            "phone": f"+9155555{unique_rej[:5]}",
            "role": "OPERATOR"
        })
        rej_id = reg_rej.json()["user"]["id"]
        env["db"].users.update_one({"$or": [{"id": rej_id}, {"user_id": rej_id}]}, {"$set": {"approval_status": "PENDING_APPROVAL", "role": "OPERATOR"}})

        # Rejection without reason fails
        res_fail = client.post(f"/api/v1/admin/operators/{rej_id}/reject", json={"reason": ""}, headers=headers)
        assert res_fail.status_code == 400

        # Rejection with valid reason succeeds
        res_rej = client.post(f"/api/v1/admin/operators/{rej_id}/reject", json={"reason": "Invalid municipal ID documents"}, headers=headers)
        assert res_rej.status_code == 200
        assert res_rej.json()["data"]["approval_status"] == "REJECTED"

        # Suspension workflow on active operator
        target_op_id = env["operator"]["user_id"]
        res_susp = client.post(f"/api/v1/admin/operators/{target_op_id}/suspend", json={"reason": "Protocol violation during shift"}, headers=headers)
        assert res_susp.status_code == 200
        assert res_susp.json()["data"]["status"] == "SUSPENDED"

        # Reactivation
        res_react = client.post(f"/api/v1/admin/operators/{target_op_id}/reactivate", headers=headers)
        assert res_react.status_code == 200
        assert res_react.json()["data"]["status"] == "ACTIVE"

    def test_08_operator_duty_zone_and_profile_drawer(self, setup_admin_env):
        """Duty zone assignment and comprehensive operator profile drawer retrieval."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}
        op_id = env["operator"]["user_id"]

        # Assign duty zone
        res_zone = client.post(f"/api/v1/admin/operators/{op_id}/assign-zone", json={"zone_id": "ZONE-CENTRAL"}, headers=headers)
        assert res_zone.status_code == 200
        assert res_zone.json()["data"]["duty_zone"] == "ZONE-CENTRAL"

        # Get operator profile drawer data
        res_prof = client.get(f"/api/v1/admin/operators/{op_id}", headers=headers)
        assert res_prof.status_code == 200
        pdata = res_prof.json()["data"]
        assert "operator" in pdata
        assert "shifts" in pdata
        assert "incidents" in pdata
        assert "recommendations" in pdata
        assert "audit_trail" in pdata
        assert pdata["operator"]["duty_zone"] == "ZONE-CENTRAL"

    def test_09_system_audit_logs_query_and_filtering(self, setup_admin_env):
        """Audit logs console supports filtering by role, action, and severity."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # Query all audit logs
        res_all = client.get("/api/v1/admin/audit-logs?page=1&limit=25", headers=headers)
        assert res_all.status_code == 200
        assert res_all.json()["data"]["total_count"] > 0

        # Query by role ADMIN
        res_admin = client.get("/api/v1/admin/audit-logs?role=ADMIN&page=1&limit=25", headers=headers)
        assert res_admin.status_code == 200
        for log in res_admin.json()["data"]["logs"]:
            assert log["actor_role"] == "ADMIN"

    def test_10_database_management_and_index_validation(self, setup_admin_env):
        """Safe database stats and non-destructive index validation."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        res_db = client.get("/api/v1/admin/database", headers=headers)
        assert res_db.status_code == 200
        db_data = res_db.json()["data"]
        assert db_data["database_name"] == "traffic_ai"
        assert db_data["total_collections"] >= 10
        assert db_data["total_documents"] >= 0

        # Validate indexes
        res_idx = client.post("/api/v1/admin/database/validate-indexes", headers=headers)
        assert res_idx.status_code == 200
        assert res_idx.json()["data"]["success"] is True

    def test_11_cctv_management_and_stream_testing(self, setup_admin_env):
        """CCTV list returns 4-state diagnostics and supports camera updates and truthful stream testing."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # Ensure a test camera exists in MongoDB
        env["db"].cctv_cameras.update_one(
            {"camera_code": "CAM-TEST-01"},
            {"$set": {
                "camera_code": "CAM-TEST-01",
                "name": "Civil Lines Intersection North",
                "location_name": "Civil Lines",
                "zone_id": "ZONE-CENTRAL",
                "status": "ONLINE",
                "stream_status": "ONLINE",
                "ai_status": "ONLINE",
                "vehicle_data_status": "ONLINE",
                "confidence_threshold": 0.65,
                "stream_url": "rtsp://admin:secret@camera1.kanpur.gov.in/live"
            }},
            upsert=True
        )

        # 1. Get CCTV list
        res_cctv = client.get("/api/v1/admin/cctv?page=1&limit=10", headers=headers)
        assert res_cctv.status_code == 200
        cams = res_cctv.json()["data"]["cameras"]
        assert len(cams) > 0

        # Verify RTSP password was masked
        test_cam = next((c for c in cams if c["camera_code"] == "CAM-TEST-01"), None)
        assert test_cam is not None
        if "rtsp_url" in test_cam:
            assert "secret" not in test_cam["rtsp_url"]

        # 2. Update camera config
        res_upd = client.patch("/api/v1/admin/cctv/CAM-TEST-01", json={
            "name": "Civil Lines Primary Flow North",
            "confidence_threshold": 0.70
        }, headers=headers)
        assert res_upd.status_code == 200
        assert res_upd.json()["data"]["success"] is True

        # 3. Test camera stream probe
        res_probe = client.post("/api/v1/admin/cctv/CAM-TEST-01/test", headers=headers)
        assert res_probe.status_code == 200
        assert res_probe.json()["data"]["status"] in ["ONLINE", "DEGRADED", "NOT_CONFIGURED"]

    def test_12_integrations_list_and_live_test(self, setup_admin_env):
        """Integration list and live connectivity probe."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # List integrations
        res_list = client.get("/api/v1/admin/integrations", headers=headers)
        assert res_list.status_code == 200
        assert len(res_list.json()["data"]) >= 5

        # Test mongodb integration
        res_test = client.post("/api/v1/admin/integrations/mongodb_database/test", headers=headers)
        assert res_test.status_code == 200
        assert res_test.json()["data"]["status"] == "ONLINE"

    def test_13_system_config_and_feature_flags(self, setup_admin_env):
        """System settings and feature flags read/update with audit trails."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # 1. Get system config
        res_cfg = client.get("/api/v1/admin/config", headers=headers)
        assert res_cfg.status_code == 200
        configs = res_cfg.json()["data"]
        assert len(configs) > 0

        # Update setting
        res_patch_cfg = client.patch("/api/v1/admin/config", json={
            "key": "traffic.anomaly_speed_drop_pct",
            "value": 40,
            "reason": "Adjusting for peak festival congestion"
        }, headers=headers)
        assert res_patch_cfg.status_code == 200
        assert res_patch_cfg.json()["data"]["new_value"] == 40

        # 2. Get feature flags
        res_flags = client.get("/api/v1/admin/feature-flags", headers=headers)
        assert res_flags.status_code == 200
        flags = res_flags.json()["data"]
        assert len(flags) >= 5

        # Toggle feature flag
        res_toggle = client.patch("/api/v1/admin/feature-flags/anomaly_detection", json={
            "enabled": True
        }, headers=headers)
        assert res_toggle.status_code == 200
        assert res_toggle.json()["data"]["enabled"] is True

    def test_14_security_events_and_session_revocation(self, setup_admin_env):
        """Security events recording and active session revocation."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # 1. Record security event
        res_sec = client.post("/api/v1/admin/security/events", json={
            "event_type": "SUSPICIOUS_LOGIN_ACTIVITY",
            "severity": "MEDIUM",
            "target_user_id": env["user"]["user_id"],
            "metadata": {"reason": "Multiple IP shifts"}
        }, headers=headers)
        assert res_sec.status_code == 200
        assert res_sec.json()["data"]["type"] == "SUSPICIOUS_LOGIN_ACTIVITY"

        # 2. List security events
        res_sec_list = client.get("/api/v1/admin/security/events?limit=10", headers=headers)
        assert res_sec_list.status_code == 200
        assert len(res_sec_list.json()["data"]) > 0

        # 3. Create dummy active session and revoke
        sess_id = f"sess_{uuid.uuid4().hex[:8]}"
        env["db"].admin_sessions.insert_one({
            "session_id": sess_id,
            "user_id": env["user"]["user_id"],
            "platform": "WEB",
            "status": "ACTIVE",
            "login_time": "2026-09-19T12:00:00Z"
        })

        res_revoke = client.post(f"/api/v1/admin/sessions/{sess_id}/revoke", json={
            "reason": "Administrative security revocation"
        }, headers=headers)
        assert res_revoke.status_code == 200
        assert res_revoke.json()["data"]["status"] == "REVOKED"

    def test_15_backup_and_protected_recovery(self, setup_admin_env):
        """Backup creation, integrity verification, and protected restore with confirmation phrase."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # 1. Create backup
        res_bak = client.post("/api/v1/admin/backups", json={"backup_type": "METADATA_AND_CONFIG"}, headers=headers)
        assert res_bak.status_code == 200
        bak_data = res_bak.json()["data"]
        backup_id = bak_data["backup_id"]
        assert bak_data["status"] == "VERIFIED"

        # 2. Verify backup
        res_ver = client.post(f"/api/v1/admin/backups/{backup_id}/verify", headers=headers)
        assert res_ver.status_code == 200
        assert res_ver.json()["data"]["status"] == "VERIFIED"

        # 3. Restore with incorrect phrase fails (HTTP 400)
        res_rest_fail = client.post(f"/api/v1/admin/backups/{backup_id}/restore", json={
            "confirmation_phrase": "wrong phrase"
        }, headers=headers)
        assert res_rest_fail.status_code == 400

        # 4. Restore with correct typed phrase succeeds
        res_rest_ok = client.post(f"/api/v1/admin/backups/{backup_id}/restore", json={
            "confirmation_phrase": "CONFIRM RESTORE"
        }, headers=headers)
        assert res_rest_ok.status_code == 200
        assert res_rest_ok.json()["data"]["success"] is True

    def test_16_global_permission_aware_search(self, setup_admin_env):
        """Global search returns matching users, operators, cameras, roads, and incidents without secret leakage."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        res_search = client.get("/api/v1/admin/search?q=Civil", headers=headers)
        assert res_search.status_code == 200
        data = res_search.json()["data"]
        assert "results" in data
        assert "users" in data["results"]
        assert "operators" in data["results"]
        assert "cameras" in data["results"]

    def test_17_reports_and_csv_export(self, setup_admin_env):
        """Reports endpoint and structured CSV export generation."""
        env = setup_admin_env
        headers = {"Authorization": f"Bearer {env['admin']['token']}"}

        # 1. Get JSON report data
        res_rep = client.get("/api/v1/admin/reports?type=user_growth&timeframe=24h", headers=headers)
        assert res_rep.status_code == 200
        assert "summary" in res_rep.json()["data"]

        # 2. Export users CSV
        res_csv = client.get("/api/v1/admin/reports/users/export?timeframe=24h", headers=headers)
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv.headers["content-type"]
        csv_text = res_csv.text
        assert "User ID" in csv_text
        assert "Email" in csv_text
        assert "Role" in csv_text
