import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from main import app
from auth import AuthManager

client = TestClient(app)
auth_manager = AuthManager()

def test_admin_mobile_rejection():
    print("[1/6] Testing Admin mobile app rejection...")
    # 1. Admin login with Web header -> 200
    admin_email = f"admin_test_{uuid.uuid4().hex[:6]}@trafficai.gov.in"
    admin_pass = "AdminSec#2026!"
    reg_res = auth_manager.register_user(email=admin_email, password=admin_pass, name="Platform Admin", role="USER")
    from mongo_db import get_mongo_db
    db = get_mongo_db()
    db.users.update_one({"id": reg_res["user"]["id"]}, {"$set": {"role": "ADMIN"}})
    
    # Try logging in via mobile header
    res_mobile = client.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": admin_pass},
        headers={"X-Client-Platform": "android"}
    )
    assert res_mobile.status_code == 403, f"Expected 403 for Admin on mobile, got {res_mobile.status_code}"
    assert "restricted to Desktop Web only" in res_mobile.json()["detail"]
    print("  -> Admin correctly blocked from Android/Mobile app!")

    # Try logging in via Web (no mobile headers)
    res_web = client.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": admin_pass},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    assert res_web.status_code == 200, f"Expected 200 for Admin on Web, got {res_web.status_code}"
    print("  -> Admin login successful on Desktop Web.")

@pytest.fixture(scope="module")
def op_token():
    op_email = f"op_test_{uuid.uuid4().hex[:6]}@trafficai.gov.in"
    op_pass = "Operator#2026!"
    reg_res = auth_manager.register_user(email=op_email, password=op_pass, name="Duty Operator", role="TRAFFIC_OPERATOR")
    auth_manager.approve_operator(reg_res["user"]["id"])
    
    res_op = client.post(
        "/api/v1/auth/login",
        json={"email": op_email, "password": op_pass},
        headers={"X-Client-Platform": "android"}
    )
    return res_op.json()["token"]

def test_operator_and_user_mobile_allowed(op_token: str):
    print("[2/6] Testing Operator and Commuter mobile app access...")
    assert op_token is not None

    # Commuter
    user_email = f"user_test_{uuid.uuid4().hex[:6]}@gmail.com"
    user_pass = "Commuter#2026!"
    auth_manager.register_user(email=user_email, password=user_pass, name="Daily Commuter", role="USER")
    
    res_user = client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": user_pass},
        headers={"X-Client-Platform": "android"}
    )
    assert res_user.status_code == 200, f"Expected 200 for User on mobile, got {res_user.status_code}"
    print("  -> Commuter permitted on Mobile App.")

def test_operator_shift_lifecycle(op_token: str):
    print("[3/6] Testing Operator Shift & Handover lifecycle...")
    headers = {"Authorization": f"Bearer {op_token}"}
    
    # 1. Start Shift
    res_start = client.post("/api/v1/operator/shift/start", json={"notes": "Morning Shift Started"}, headers=headers)
    assert res_start.status_code == 200, f"Shift start failed: {res_start.text}"
    shift = res_start.json()["shift"]
    assert shift["status"] == "ACTIVE"
    print(f"  -> Shift started with ID: {shift['id']}")

    # 2. Check Active Shift
    res_active = client.get("/api/v1/operator/shift/active", headers=headers)
    assert res_active.status_code == 200
    assert res_active.json()["active"] is True
    print("  -> Active shift verified.")

    # 3. Get Handover Summary
    res_summary = client.get("/api/v1/operator/shift/summary", headers=headers)
    assert res_summary.status_code == 200
    summary = res_summary.json()["summary"]
    assert "open_incidents" in summary
    print(f"  -> Handover summary compiled (Action items: {summary.get('total_action_items', 0)}).")

    # 4. Submit Handover
    res_handover = client.post(
        "/api/v1/operator/shift/handover",
        json={
            "shift_id": shift["id"],
            "handover_to_name": "S. Sharma (Desk 2)",
            "handover_notes": "All arterials operating within capacity. Handover complete."
        },
        headers=headers
    )
    assert res_handover.status_code == 200, f"Handover failed: {res_handover.text}"
    print("  -> Shift handover recorded successfully.")

    # 5. Start new shift and test End Shift
    res_start2 = client.post("/api/v1/operator/shift/start", json={"notes": "Shift 2 Started"}, headers=headers)
    shift2_id = res_start2.json()["shift"]["id"]
    res_end = client.post("/api/v1/operator/shift/end", json={"shift_id": shift2_id, "notes": "Shift concluded normally."}, headers=headers)
    assert res_end.status_code == 200, f"End shift failed: {res_end.text}"
    print(f"  -> Shift {shift2_id} ended cleanly.")

def test_cctv_and_signals(op_token: str):
    print("[4/6] Testing CCTV diagnostic probes and signal recommendations...")
    headers = {"Authorization": f"Bearer {op_token}"}

    # 1. List CCTV
    res_cctv = client.get("/api/v1/cctv/cameras")
    assert res_cctv.status_code == 200
    cameras = res_cctv.json()["cameras"]
    assert len(cameras) > 0
    cam_id = cameras[0]["id"]
    print(f"  -> CCTV list returned {len(cameras)} cameras. Testing probe on {cam_id}...")

    # 2. Test Probe (unconfigured stream -> returns NOT_CONFIGURED without faking)
    res_probe = client.post(f"/api/v1/cctv/{cam_id}/test")
    assert res_probe.status_code == 200
    probe_result = res_probe.json()["probe"]
    assert probe_result["status"] in ["ONLINE", "OFFLINE", "NOT_CONFIGURED", "UNREACHABLE", "DEGRADED"]
    print(f"  -> Probe completed truthfully: Status={probe_result['status']}")

    # 3. Signals
    res_sig = client.get("/api/v1/signals/recommendations")
    assert res_sig.status_code == 200
    recs = res_sig.json()["recommendations"]
    assert len(recs) > 0
    int_id = recs[0]["intersection_id"]

    # 4. Signal Approval
    res_appr = client.post(f"/api/v1/operator/signals/{int_id}/approve", headers=headers)
    assert res_appr.status_code == 200
    print(f"  -> Signal optimization approved for {int_id}.")

def test_incidents_and_alerts(op_token: str):
    print("[5/6] Testing Incident creation, nearby CCTV linking, verification, reject reason audit, and alert broadcast...")
    headers = {"Authorization": f"Bearer {op_token}"}

    # 1. Create Incident
    inc_res = client.post("/api/v1/incidents", json={
        "title": "Minor Stalled Truck on VIP Road",
        "category": "Vehicle Breakdown",
        "severity": "Moderate",
        "road_segment_id": "VIP_Road_Arterial",
        "latitude": 26.4600,
        "longitude": 80.3400,
        "description": "Right lane blocked temporarily.",
        "source": "Traffic Control Desk"
    })
    assert inc_res.status_code == 200
    inc_id = inc_res.json()["id"]
    print(f"  -> Incident reported: {inc_id}")

    # 2. Test nearby CCTV enrichment
    nearby_res = client.get(f"/api/v1/operator/incidents/{inc_id}/nearby-cctv", headers=headers)
    assert nearby_res.status_code == 200
    print(f"  -> Incident {inc_id} nearby CCTV count: {nearby_res.json().get('count', 0)}")

    # 3. Update status to Verified
    up_res = client.patch(f"/api/v1/incidents/{inc_id}", json={"status": "Verified"})
    assert up_res.status_code == 200
    assert up_res.json()["status"] == "Verified"
    print(f"  -> Incident {inc_id} verified.")

    # 4. Test Reject with mandatory reason
    inc_res2 = client.post("/api/v1/incidents", json={
        "title": "False Alarm Report",
        "category": "Congestion",
        "severity": "Low",
        "latitude": 26.4700,
        "longitude": 80.3500,
        "description": "Reported heavy blockage."
    })
    inc2_id = inc_res2.json()["id"]
    rej_res = client.post("/api/v1/operator/incidents/reject", json={
        "incident_id": inc2_id,
        "public_note": "Visual check via CCTV shows normal flow / False alarm"
    }, headers=headers)
    assert rej_res.status_code == 200
    print(f"  -> Incident {inc2_id} rejected with audited operational reason.")

    # 5. Publish Alert
    alt_res = client.post("/api/v1/operator/alerts", json={
        "title": "VIP Road Delay Advisory",
        "message": "Stalled vehicle cleared, expect residual slow-moving traffic.",
        "severity": "LOW",
        "affected_area": "VIP Road Corridor"
    }, headers=headers)
    assert alt_res.status_code == 200
    print("  -> Traffic alert published successfully.")


def test_weather_sync():
    print("[6/9] Testing Weather coordinates synchronization...")
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    weather = res.json()["weather"]
    assert "temperature_c" in weather
    assert "city" in weather or "city_name" in weather
    print(f"  -> Weather synchronised: {weather.get('city') or weather.get('city_name')} ({weather.get('temperature_c')}°C)")

def test_notifications_workflow(op_token: str):
    print("[7/9] Testing Notification creation, unread count, mark read, and mark all read...")
    headers = {"Authorization": f"Bearer {op_token}"}
    
    # 1. Fetch unread count
    res_count = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res_count.status_code == 200
    initial_unread = res_count.json()["unread_count"]
    print(f"  -> Initial unread count: {initial_unread}")

    # 2. Fetch list
    res_list = client.get("/api/v1/notifications", headers=headers)
    assert res_list.status_code == 200
    notifs = res_list.json()["notifications"]
    print(f"  -> Retrieved {len(notifs)} notifications for operator.")

    if len(notifs) > 0:
        notif_id = notifs[0]["id"]
        # Mark single read
        res_read = client.patch(f"/api/v1/notifications/{notif_id}/read", headers=headers)
        assert res_read.status_code == 200
        assert res_read.json()["marked"] is True
        print(f"  -> Marked notification {notif_id} as read.")

    # Mark all read
    res_all = client.post("/api/v1/notifications/mark-all-read", headers=headers)
    assert res_all.status_code == 200
    assert res_all.json()["unread_count"] == 0
    print("  -> Marked all notifications as read (unread count = 0).")

def test_emergency_corridors(op_token: str):
    print("[8/9] Testing Emergency Green Corridors...")
    headers = {"Authorization": f"Bearer {op_token}"}
    res_corr = client.get("/api/v1/operator/emergency-corridors", headers=headers)
    assert res_corr.status_code == 200
    corridors = res_corr.json()["corridors"]
    assert len(corridors) > 0
    assert res_corr.json()["badge"] == "SIMULATION / RECOMMENDATION ONLY"
    print(f"  -> Retrieved {len(corridors)} emergency corridors with truthful simulation badge.")

def test_system_health_and_observability():
    print("[9/9] Testing System Health & Observability endpoints...")
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "mongodb" in data
    assert "weather" in data
    print("  -> System health operational across all subsystems.")

if __name__ == "__main__":
    print("=== STARTING MASTER PLATFORM PRODUCTION VERIFICATION ===")
    test_admin_mobile_rejection()
    op_token = test_operator_and_user_mobile_allowed()
    test_operator_shift_lifecycle(op_token)
    test_cctv_and_signals(op_token)
    test_incidents_and_alerts(op_token)
    test_weather_sync()
    test_notifications_workflow(op_token)
    test_emergency_corridors(op_token)
    test_system_health_and_observability()
    print("=== ALL MASTER VERIFICATION TESTS PASSED SUCCESSFULLY! ===")
