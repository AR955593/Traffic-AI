"""
TrafficAI V5: Production Real Traffic Intelligence Platform Test Suite
Tests covering:
1. Road segment CRUD, listing and detail retrieval
2. Corridor intelligence aggregation
3. Camera -> Road -> Corridor spatial resolution
4. Vehicle telemetry ingestion and flow aggregation
5. Freshness calculation & Truthful data states (LIVE, STALE, UNAVAILABLE)
6. Anomaly detection with structured evidence & lifecycle transition
7. Multi-entity incident correlation
8. Forecast generation (+15, +30, +60 min) & FORECAST_UNAVAILABLE handling
9. Explainable AI Recommendations (WHAT, WHY, EVIDENCE, SIMULATION ONLY)
10. Recommendation review lifecycle (Approval for simulation & Rejection)
11. Outcome measurement engine (Before -> Action -> After Delta)
12. Data quality matrix
13. Historical incident replay without fake video
14. Strict Server-Side RBAC: USER rejected (HTTP 403) on operator endpoints
15. Strict Server-Side RBAC: ADMIN mobile rejection (HTTP 403)
16. Dual-identifier unified authentication resolution
17. Negative tests (malformed input, missing segments, invalid reviews)
"""
import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

# Ensure project root and src/ are in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

from app.main import app, v5_engine
from src.auth import create_access_token
from src.mongo_db import get_mongo_db, init_mongo_indexes
from src.db import init_db

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_environment():
    init_db()
    init_mongo_indexes()
    db = get_mongo_db()
    yield db

@pytest.fixture(scope="module")
def operator_token():
    return create_access_token(data={
        "sub": "op-v5-test",
        "email": "operator_v5@trafficai.gov.in",
        "name": "Operator V5",
        "role": "TRAFFIC_OPERATOR"
    })

@pytest.fixture(scope="module")
def user_token():
    return create_access_token(data={
        "sub": "user-v5-test",
        "email": "user_v5@trafficai.org",
        "name": "User V5",
        "role": "USER"
    })

@pytest.fixture(scope="module")
def admin_token():
    return create_access_token(data={
        "sub": "admin-v5-test",
        "email": "admin_v5@trafficai.gov.in",
        "name": "Admin V5",
        "role": "ADMIN"
    })


class TestTrafficAIV5RealIntelligence:
    """Master V5 Test Suite for Production Real Traffic Intelligence Platform."""

    # 1. Road Segments
    def test_01_road_segments_listing(self, setup_environment, operator_token):
        res = client.get(
            "/api/v1/operator/road-segments",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert len(data["segments"]) >= 4
        # Verify segment structure
        first_seg = data["segments"][0]
        assert "segment_id" in first_seg
        assert "live_state" in first_seg
        assert "free_flow_speed" in first_seg

    def test_02_road_segment_detail(self, setup_environment, operator_token):
        res = client.get(
            "/api/v1/operator/road-segments/SEG-MALL-01",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        seg = data["segment"]
        assert seg["segment_id"] == "SEG-MALL-01"
        assert "mapped_cameras" in seg
        assert "forecasts" in seg
        assert "live_state" in seg

    def test_03_record_road_traffic_state_and_freshness(self, setup_environment, operator_token):
        state_payload = {
            "speed": 32.5,
            "free_flow_speed": 45.0,
            "queue_length_m": 120.0,
            "delay_seconds": 45,
            "source": "TOMTOM_TRAFFIC_API"
        }
        res = client.post(
            "/api/v1/operator/road-segments/SEG-MALL-01/state",
            json=state_payload,
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        snap = res.json()["snapshot"]
        assert snap["speed"] == 32.5
        assert snap["congestion_index"] > 0
        assert snap["status"] == "LIVE"
        assert snap["freshness_seconds"] == 0

    # 2. Corridors
    def test_04_corridor_intelligence_aggregation(self, setup_environment, operator_token):
        res = client.get(
            "/api/v1/operator/corridors/CORR-MALL-RD/intelligence",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        intel = data["intelligence"]
        assert intel["corridor_id"] == "CORR-MALL-RD"
        assert "avg_speed" in intel
        assert "cctv_available_count" in intel
        assert "queue_length_m" in intel

    # 3. Camera Graph
    def test_05_camera_graph_resolution(self, setup_environment, operator_token):
        res = client.get(
            "/api/v1/operator/cameras/CAM-001/intelligence",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        intel = res.json()["intelligence"]
        assert intel["camera_id"] == "CAM-001"
        assert intel["mapping"]["segment_id"] == "SEG-MALL-01"
        assert intel["mapping"]["corridor_id"] == "CORR-MALL-RD"

    # 4. Vehicle Flow Telemetry
    def test_06_vehicle_flow_telemetry_ingestion(self, setup_environment, operator_token):
        payload = {
            "camera_id": "CAM-001",
            "road_segment_id": "SEG-MALL-01",
            "cars_count": 35,
            "bikes_count": 20,
            "buses_count": 4,
            "trucks_count": 2,
            "other_count": 1,
            "vehicles_per_minute": 62,
            "average_speed_kmh": 28.0,
            "queue_length": 180.0,
            "direction": "WESTBOUND",
            "source": "NVR_EDGE_AI"
        }
        res = client.post(
            "/api/v1/operator/vehicle-telemetry",
            json=payload,
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200

        # Verify flow snapshots via V5 endpoint
        flow_res = client.get(
            "/api/v1/operator/vehicle-flow?camera_id=CAM-001",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert flow_res.status_code == 200
        data = flow_res.json()
        assert data["count"] >= 1
        latest = data["vehicle_flow"][0]
        assert latest["cars"] == 35
        assert latest["total"] == 62

    # 5. Anomaly Detection & Lifecycle
    def test_07_anomaly_detection_and_acknowledgement(self, setup_environment, operator_token):
        # Trigger sudden speed drop anomaly by recording very low speed
        v5_engine.record_road_traffic_state(
            segment_id="SEG-VIP-01",
            speed=15.0,
            free_flow_speed=50.0,
            queue_length_m=350.0,
            source="TOMTOM_TRAFFIC_API"
        )
        anomalies = v5_engine.get_anomalies()
        assert len(anomalies) >= 1
        anom = anomalies[0]
        assert anom["type"] in ["SUDDEN_SPEED_DROP", "QUEUE_GROWTH"]
        assert len(anom["evidence"]) >= 1

        # Acknowledge anomaly via endpoint
        ack_res = client.post(
            f"/api/v1/operator/anomalies/{anom['anomaly_id']}/ack",
            json={"notes": "Investigating speed drop at VIP Road"},
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert ack_res.status_code == 200
        assert ack_res.json()["anomaly"]["status"] == "ACKNOWLEDGED"

        # Update status to RESOLVED
        status_res = client.post(
            f"/api/v1/operator/anomalies/{anom['anomaly_id']}/status",
            json={"status": "RESOLVED", "notes": "Traffic restored"},
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert status_res.status_code == 200
        assert status_res.json()["anomaly"]["status"] == "RESOLVED"

    # 6. Multi-Entity Incident Correlation
    def test_08_incident_multi_entity_correlation(self, setup_environment, operator_token):
        db = setup_environment
        # Insert test verified incident near Mall Road
        inc_id = f"INC-{uuid.uuid4().hex[:6]}"
        db.user_incidents.insert_one({
            "id": inc_id,
            "type": "ACCIDENT",
            "description": "Multi-vehicle collision near Parade",
            "lat": 26.4680,
            "lng": 80.3478,
            "status": "VERIFIED",
            "created_at": "2026-09-19T10:00:00Z"
        })

        corr = v5_engine.correlate_incident_evidence(inc_id)
        assert corr["incident_id"] == inc_id
        assert corr["evidence_count"] >= 2
        assert "disclaimer" in corr

    # 7. Forecasting Engine (+15, +30, +60 min)
    def test_09_forecasting_with_insufficient_data(self, setup_environment, operator_token):
        # Segment with < 2 snapshots returns FORECAST_UNAVAILABLE
        fc = v5_engine.get_traffic_forecast(target_type="SEGMENT", target_id="SEG-NEW-UNRECORDED")
        assert fc["status"] == "FORECAST_UNAVAILABLE"
        assert len(fc["horizons"]) == 0

    def test_10_forecasting_with_sufficient_data(self, setup_environment, operator_token):
        # Insert 2 state snapshots for SEG-GT-01
        v5_engine.record_road_traffic_state("SEG-GT-01", speed=48.0, free_flow_speed=55.0)
        v5_engine.record_road_traffic_state("SEG-GT-01", speed=42.0, free_flow_speed=55.0)

        res = client.get(
            "/api/v1/operator/forecasts?target_type=SEGMENT&target_id=SEG-GT-01",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        fc = res.json()["forecast"]
        assert fc["status"] == "FORECAST_READY"
        assert len(fc["horizons"]) == 3
        horizons_mins = [h["horizon_minutes"] for h in fc["horizons"]]
        assert horizons_mins == [15, 30, 60]

    # 8. Explainable AI Recommendations & Simulation
    def test_11_explainable_recommendation_lifecycle(self, setup_environment, operator_token):
        create_payload = {
            "category": "SIGNALS",
            "target_type": "SEGMENT",
            "target_id": "SEG-MALL-01",
            "what": "Extend East-West green phase by 18 seconds",
            "why": "Queue growth +35% with sudden speed drop to 28 km/h",
            "evidence": ["Speed dropped 38%", "Queue expanded to 180m"],
            "data_sources": ["TomTom Traffic API", "NVR Edge AI"],
            "expected_effect": "Simulated queue reduction of 22%",
            "risks_limitations": "In silico simulation only; physical signal controller not linked"
        }
        res = client.post(
            "/api/v1/operator/recommendations",
            json=create_payload,
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        rec = res.json()["recommendation"]
        assert rec["status"] == "PENDING_REVIEW"
        assert rec["is_simulation_only"] is True

        # Approve recommendation for simulation
        app_res = client.post(
            f"/api/v1/operator/recommendations/{rec['recommendation_id']}/approve",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert app_res.status_code == 200
        app_rec = app_res.json()["recommendation"]
        assert app_rec["status"] == "APPROVED_FOR_SIMULATION"
        assert app_rec["simulation_result"]["simulation_status"] == "COMPLETED_IN_SILICO"

    def test_12_recommendation_rejection(self, setup_environment, operator_token):
        rec = v5_engine.create_recommendation_v5(
            category="DISPATCH",
            target_type="SEGMENT",
            target_id="SEG-VIP-01",
            what="Deploy traffic warden team",
            why="Unusual peak congestion",
            evidence=["High congestion index 0.72"],
            data_sources=["TomTom Traffic API"],
            expected_effect="Manual bottleneck clearance",
            risks_limitations="Subject to warden team availability"
        )
        rej_res = client.post(
            f"/api/v1/operator/recommendations/{rec['recommendation_id']}/reject?reason=Sufficient+coverage+already+active",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert rej_res.status_code == 200
        assert rej_res.json()["recommendation"]["status"] == "REJECTED"

    # 9. Outcome Measurement Engine
    def test_13_outcome_measurement_delta(self, setup_environment, operator_token):
        # 1. Trigger recommendation approval to initialize outcome event baseline
        rec = v5_engine.create_recommendation_v5(
            category="SIGNALS",
            target_type="SEGMENT",
            target_id="SEG-PARADE-01",
            what="Simulate cycle re-time",
            why="Queue build-up",
            evidence=["Queue > 100m"],
            data_sources=["TomTom"],
            expected_effect="Queue dissipation",
            risks_limitations="Sim only"
        )
        v5_engine.record_road_traffic_state("SEG-PARADE-01", speed=20.0, free_flow_speed=35.0, queue_length_m=200.0)
        v5_engine.review_recommendation_v5(rec["recommendation_id"], "APPROVED_FOR_SIMULATION", "op-v5-test")

        # 2. Get the created outcome event
        outcomes_res = client.get(
            "/api/v1/operator/outcomes",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert outcomes_res.status_code == 200
        outcomes = outcomes_res.json()["outcomes"]
        assert len(outcomes) >= 1
        action_id = outcomes[0]["action_id"]

        # 3. Record improved post-action traffic state
        v5_engine.record_road_traffic_state("SEG-PARADE-01", speed=30.0, free_flow_speed=35.0, queue_length_m=80.0)

        # 4. Measure outcome
        meas_res = client.post(
            "/api/v1/operator/outcomes/measure",
            json={"action_id": action_id},
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert meas_res.status_code == 200
        res_data = meas_res.json()["outcome"]
        assert res_data["outcome_status"] == "MEASURED_IMPROVEMENT"
        assert res_data["measured_delta"]["speed_delta_kmh"] > 0

    # 10. Data Quality Matrix
    def test_14_data_quality_matrix(self, setup_environment, operator_token):
        res = client.get(
            "/api/v1/operator/data-quality",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        sources = data.get("sources", {})
        assert "traffic_api" in sources or "cctv_gateway" in sources

    # 11. Historical Intelligence Replay
    def test_15_historical_incident_replay_no_fake_video(self, setup_environment, operator_token):
        db = setup_environment
        inc_id = f"INC-HIST-{uuid.uuid4().hex[:6]}"
        db.user_incidents.insert_one({
            "id": inc_id,
            "type": "ROAD_HAZARD",
            "lat": 26.4715,
            "lng": 80.3512,
            "status": "RESOLVED",
            "created_at": "2026-09-19T08:00:00Z"
        })
        res = client.get(
            f"/api/v1/operator/incident-replay/{inc_id}",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 200
        data = res.json()["replay"]
        assert data["incident_id"] == inc_id
        assert data["video_stream_replay"]["status"] == "VIDEO_NOT_AVAILABLE"
        assert len(data["timeline"]) >= 1

    # 12. Strict Server-Side RBAC
    def test_16_user_role_rejected_on_v5_operator_endpoints(self, setup_environment, user_token):
        """USER role must receive HTTP 403 Forbidden on all operator endpoints."""
        endpoints = [
            "/api/v1/operator/road-segments",
            "/api/v1/operator/road-segments/SEG-MALL-01",
            "/api/v1/operator/corridors/CORR-MALL-RD/intelligence",
            "/api/v1/operator/cameras/CAM-001/intelligence",
            "/api/v1/operator/vehicle-flow",
            "/api/v1/operator/forecasts",
            "/api/v1/operator/recommendations",
            "/api/v1/operator/outcomes"
        ]
        for ep in endpoints:
            res = client.get(ep, headers={"Authorization": f"Bearer {user_token}"})
            assert res.status_code == 403, f"Endpoint {ep} did not reject USER with HTTP 403!"

    def test_17_admin_mobile_rejected(self, setup_environment, admin_token):
        """Admin attempting to access platform with Mobile User-Agent receives HTTP 403."""
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 TrafficAI-Android"
        }
        res = client.get("/api/v1/operator/road-segments", headers=headers)
        assert res.status_code == 403
        assert "Desktop Web" in res.json().get("detail", "")

    # 13. Dual-Identifier Authentication Resolution
    def test_18_unified_dual_identifier_resolution(self, setup_environment):
        """Single centralized account login via email and phone resolving to the same user_id."""
        suffix = uuid.uuid4().hex[:6]
        email = f"commuter_{suffix}@trafficai.org"
        phone = f"+919811{suffix[:6]}"
        password = "Password123!"

        # Register once
        reg_res = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "name": f"Commuter {suffix}",
            "phone": phone,
            "role": "USER"
        })
        assert reg_res.status_code == 200
        user_id = reg_res.json()["user"]["id"]

        # Login with email
        email_login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert email_login.status_code == 200
        assert email_login.json()["user"]["id"] == user_id

        # Login with phone
        phone_login = client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
        assert phone_login.status_code == 200
        assert phone_login.json()["user"]["id"] == user_id

    # 14. Negative Tests
    def test_19_negative_nonexistent_segment(self, setup_environment, operator_token):
        res = client.get(
            "/api/v1/operator/road-segments/NON-EXISTENT-SEG",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 404

    def test_20_negative_invalid_recommendation_approval(self, setup_environment, operator_token):
        res = client.post(
            "/api/v1/operator/recommendations/NON-EXISTENT-REC/approve",
            headers={"Authorization": f"Bearer {operator_token}"}
        )
        assert res.status_code == 404
