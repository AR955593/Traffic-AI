import os
import sys
import uuid
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from main import app
from auth import AuthManager

client = TestClient(app)
auth_manager = AuthManager()

def test_v3_operations_suite():
    print("=== TESTING OPERATOR V3 INTELLIGENCE + OPERATIONS SUITE ===")
    
    # 1. Login operator with unique email
    op_email = f"test_op_v3_{uuid.uuid4().hex[:6]}@trafficai.gov.in"
    op_pass = "OperatorV3#2026!"
    reg_res = auth_manager.register_user(email=op_email, password=op_pass, name="V3 Duty Operator", role="TRAFFIC_OPERATOR")
    auth_manager.approve_operator(reg_res["user"]["id"])
    
    login_res = client.post("/api/v1/auth/login", json={"email": op_email, "password": op_pass})
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Start Shift
    res_start = client.post("/api/v1/operator/shift/start", json={"notes": "V3 Verification Shift"}, headers=headers)
    assert res_start.status_code == 200
    shift_id = res_start.json()["shift"]["id"]
    print(f"  [OK] Shift started: {shift_id}")
    
    # 3. Test Live Operations Timeline
    res_timeline = client.get("/api/v1/operator/timeline?limit=20", headers=headers)
    assert res_timeline.status_code == 200
    timeline_data = res_timeline.json()
    assert "events" in timeline_data
    assert isinstance(timeline_data["events"], list)
    print(f"  [OK] Timeline retrieved {len(timeline_data['events'])} events.")
    
    # 4. Test Road Intelligence & Causal Breakdown
    res_road = client.get("/api/v1/operator/roads/CORR-01/intelligence", headers=headers)
    assert res_road.status_code == 200
    road_intel = res_road.json().get("intelligence", {})
    assert "causal_factors" in road_intel
    assert "nearby_cameras" in road_intel
    assert "congestion_score" in road_intel
    print(f"  [OK] Road intelligence for CORR-01: {road_intel.get('name')} (Congestion: {road_intel.get('congestion_score')}%, Causal factors: {len(road_intel.get('causal_factors', []))}).")
    
    # 5. Test Operations Analytics 2.0 Summary
    res_analytics = client.get("/api/v1/operator/analytics/summary?timeframe=24h", headers=headers)
    assert res_analytics.status_code == 200
    analytics_data = res_analytics.json().get("analytics", {})
    assert "kpis" in analytics_data
    assert "hourly_trends" in analytics_data
    assert "top_congested_corridors" in analytics_data
    assert "causal_factors" in analytics_data
    print(f"  [OK] Analytics 2.0 summary: Avg Speed={analytics_data['kpis'].get('network_avg_speed')} km/h, Top Corridors={len(analytics_data.get('top_congested_corridors', []))}.")
    
    # 6. Test End Shift
    res_end = client.post("/api/v1/operator/shift/end", json={"shift_id": shift_id, "notes": "Shift ended cleanly."}, headers=headers)
    assert res_end.status_code == 200
    assert res_end.json().get("status") == "success" or res_end.json().get("status_label") == "COMPLETED"
    print(f"  [OK] Shift {shift_id} ended cleanly.")
    
    print("=== ALL OPERATOR V3 TESTS PASSED PERFECTLY ===")

if __name__ == "__main__":
    test_v3_operations_suite()
