import os
import sys
import unittest
from fastapi.testclient import TestClient

# Ensure root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

from app.main import app
from src.db import init_db
from src.auth import create_access_token

class TestTrafficAIV4RealIntelligence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.op_token = create_access_token(data={
            "sub": "op-test-v4",
            "email": "operator_v4@trafficai.gov.in",
            "name": "Operator V4",
            "role": "TRAFFIC_OPERATOR"
        })
        cls.admin_token = create_access_token(data={
            "sub": "admin-test-v4",
            "email": "admin_v4@trafficai.gov.in",
            "name": "Admin V4",
            "role": "ADMIN"
        })
        cls.user_token = create_access_token(data={
            "sub": "user-test-v4",
            "email": "commuter_v4@gmail.com",
            "name": "Commuter V4",
            "role": "USER"
        })

    def test_01_cctv_4state_probing(self):
        """Test CCTV 4-state diagnostic pipeline"""
        res = self.client.post(
            "/api/v1/operator/cctv/cam-001/diagnose",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        diag = data.get("probe", {}) or data.get("diagnostics", {})
        self.assertIn("camera_status", diag)
        self.assertIn("stream_status", diag)
        self.assertIn("ai_status", diag)
        self.assertIn("vehicle_data_status", diag)

    def test_02_camera_calibration(self):
        """Test configuring and retrieving camera ROI calibration"""
        calib_payload = {
            "road_segment_id": "VIP Road",
            "direction": "NORTHBOUND",
            "roi_polygon": [[100, 200], [500, 200], [600, 800], [50, 800]],
            "counting_line": [[100, 400], [550, 400]],
            "confidence_threshold": 0.8
        }
        res = self.client.post(
            "/api/v1/operator/cctv/cam-001/calibration",
            json=calib_payload,
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res.status_code, 200)
        
        get_res = self.client.get(
            "/api/v1/operator/cctv/cam-001/calibration",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(get_res.status_code, 200)
        cal = get_res.json().get("calibration", {})
        self.assertEqual(cal.get("road_segment_id"), "VIP Road")
        self.assertEqual(cal.get("direction"), "NORTHBOUND")
        self.assertEqual(cal.get("calibration_status"), "READY")

    def test_03_vehicle_telemetry_ingestion(self):
        """Test vehicle classification telemetry ingestion and retrieval"""
        telemetry_payload = {
            "camera_id": "cam-001",
            "road_segment_id": "VIP Road",
            "cars_count": 42,
            "bikes_count": 28,
            "buses_count": 5,
            "trucks_count": 3,
            "other_count": 1,
            "average_speed_kmh": 36.5,
            "occupancy_rate": 64.2
        }
        res = self.client.post(
            "/api/v1/operator/vehicle-telemetry",
            json=telemetry_payload,
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        telemetry = data.get("telemetry", {})
        self.assertIn(telemetry.get("status"), ("LIVE", "INGESTED"))
        self.assertEqual(telemetry.get("vehicle_count"), 79)

        # Query telemetry endpoint
        get_res = self.client.get(
            "/api/v1/operator/vehicle-telemetry?camera_id=cam-001",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(get_res.status_code, 200)
        records = get_res.json().get("telemetry", [])
        self.assertGreaterEqual(len(records), 1)

    def test_04_traffic_anomaly_detection_and_ack(self):
        """Test rule-based traffic anomaly detection and operator acknowledgment"""
        res = self.client.get(
            "/api/v1/operator/anomalies",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        anomalies = data.get("anomalies", [])
        self.assertIsInstance(anomalies, list)
        self.assertGreaterEqual(len(anomalies), 1)
        
        anomaly_id = anomalies[0]["id"]
        ack_res = self.client.post(
            f"/api/v1/operator/anomalies/{anomaly_id}/acknowledge",
            json={"action": "ACKNOWLEDGED", "notes": "Shift review completed"},
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(ack_res.status_code, 200)
        self.assertEqual(ack_res.json().get("anomaly_status"), "ACKNOWLEDGED")

    def test_05_multi_entity_incident_correlation(self):
        """Test multi-entity incident correlation connecting cameras, anomalies, weather, and queues"""
        res = self.client.get(
            "/api/v1/operator/incidents/inc-001/correlation",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res.status_code, 200)
        corr = res.json()
        self.assertIn("incident", corr)
        self.assertIn("nearby_cameras", corr)
        self.assertIn("correlated_anomalies", corr)
        self.assertIn("weather_condition", corr)
        self.assertIn("correlation_score", corr)

    def test_06_ai_recommendation_center(self):
        """Test listing and reviewing AI optimization proposals"""
        res = self.client.get(
            "/api/v1/operator/ai/recommendations",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res.status_code, 200)
        recs = res.json().get("recommendations", [])
        self.assertGreaterEqual(len(recs), 1)

        rec_id = recs[0]["id"]
        review_res = self.client.post(
            f"/api/v1/operator/ai/recommendations/{rec_id}/review",
            json={"action": "APPROVED_FOR_SIMULATION", "notes": "Verified against corridor flow"},
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(review_res.status_code, 200)
        self.assertEqual(review_res.json().get("recommendation_status"), "APPROVED_FOR_SIMULATION")

    def test_07_historical_incident_replay(self):
        """Test chronological step-by-step incident replay timeline"""
        res = self.client.get(
            "/api/v1/operator/incidents/INC-C6DCDD/replay",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res.status_code, 200)
        replay = res.json()
        self.assertEqual(replay.get("incident_id"), "INC-C6DCDD")
        steps = replay.get("timeline_steps", [])
        self.assertGreaterEqual(len(steps), 3)

    def test_08_zone_intelligence_and_workload(self):
        """Test duty-zone intelligence breakdown and operator workload balance"""
        res_zone = self.client.get(
            "/api/v1/operator/zones/ZONE-CENTRAL/intelligence",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res_zone.status_code, 200)
        z = res_zone.json()
        self.assertEqual(z.get("zone_id"), "ZONE-CENTRAL")
        self.assertIn("active_incidents", z)
        self.assertIn("monitored_corridors", z)

        res_work = self.client.get(
            "/api/v1/operator/workload",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res_work.status_code, 200)
        work = res_work.json()
        self.assertIn("active_operators_count", work)

    def test_09_data_quality_matrix(self):
        """Test system-wide ingestion latency, source uptime, and freshness matrix"""
        res = self.client.get(
            "/api/v1/operator/data-quality",
            headers={"Authorization": f"Bearer {self.op_token}"}
        )
        self.assertEqual(res.status_code, 200)
        dq = res.json()
        pipelines = dq.get("pipelines", [])
        self.assertGreaterEqual(len(pipelines), 4)
        names = [p["name"] for p in pipelines]
        self.assertIn("Municipal CCTV Ingestion Stream", names)
        self.assertIn("TomTom Real-Time Traffic API", names)

    def test_10_rbac_access_controls(self):
        """Test strict RBAC: Commuters cannot access operator intelligence endpoints"""
        res = self.client.get(
            "/api/v1/operator/anomalies",
            headers={"Authorization": f"Bearer {self.user_token}"}
        )
        self.assertEqual(res.status_code, 403)

        res_rec = self.client.get(
            "/api/v1/operator/ai/recommendations",
            headers={"Authorization": f"Bearer {self.user_token}"}
        )
        self.assertEqual(res_rec.status_code, 403)

if __name__ == "__main__":
    unittest.main()
