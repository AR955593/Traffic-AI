"""
Comprehensive Automated Test Suite for AI Traffic Intelligence & Smart Route Platform.
Tests network graph, simulator, geocoding, multi-criteria routing with discrete traffic segments,
ML predictor, incidents, providers, and auth/RBAC.
"""
import sys
import os
try:
    import pytest
except ImportError:
    pass

# Ensure src and app are in path
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from network_graph import get_kanpur_network, haversine_distance
from simulator import TrafficSimulator
from incidents import IncidentManager
from geocoding import GeocodingEngine
from router import SmartRouter
from predictor import TrafficPredictor
from providers import ProviderManager
from auth import AuthManager
from analytics import AnalyticsEngine

def test_network_graph():
    nodes, segments = get_kanpur_network()
    assert len(nodes) >= 16
    assert len(segments) == 32
    assert "SEG014" in segments
    seg14 = segments["SEG014"]
    assert seg14.name == "Mall Road Commercial Corridor"
    assert seg14.speed_limit_kmh == 50.0
    assert seg14.lanes == 4
    assert seg14.length_km > 0.0

def test_geocoding_and_snapping():
    geo = GeocodingEngine()
    
    # 1. Search landmark POIs
    results = geo.search_locations("JK Temple")
    assert len(results) > 0
    assert "JK Temple" in results[0]["name"]
    
    results2 = geo.search_locations("Z Square Mall")
    assert len(results2) > 0
    assert "Z Square" in results2[0]["name"]
    
    # 2. Snap arbitrary GPS coordinates to nearest graph node
    node_id, coords, dist = geo.snap_to_nearest_node(26.4621, 80.3452)
    assert node_id in geo.nodes
    assert dist < 1.0  # Within 1 km

def test_simulator_and_scenarios():
    inc_mgr = IncidentManager()
    sim = TrafficSimulator(incident_manager=inc_mgr)
    
    state1 = sim.tick()
    assert "kpis" in state1
    assert "segments" in state1
    assert len(state1["segments"]) == 32
    assert len(state1["vehicles"]) > 50
    assert "active_vehicles" in state1["kpis"]
    assert "avg_city_speed" in state1["kpis"]
    
    # Switch scenario to Heavy Rain
    res = sim.set_scenario("Heavy Rain")
    assert res["status"] == "success"
    assert sim.scenario == "Heavy Rain"
    assert sim.precipitation_mm > 10.0
    
    state2 = sim.tick()
    assert state2["weather"]["condition"] == "Heavy Rain"

def test_smart_router_with_traffic_segments():
    sim = TrafficSimulator()
    router = SmartRouter(simulator_instance=sim)
    
    # 1. Test DEMO mode route calculation
    route_plan = router.plan_route(
        origin={"lat": 26.4620, "lon": 80.3450},
        destination={"lat": 26.4250, "lon": 80.3650},
        preference="balanced",
        explicit_mode="DEMO"
    )
    
    assert "routes" in route_plan
    assert len(route_plan["routes"]) == 3
    
    rec_route = route_plan["routes"][0]
    assert rec_route["tag"] == "RECOMMENDED"
    assert rec_route["distance_km"] > 0
    assert rec_route["current_eta_minutes"] > 0
    assert rec_route["predicted_eta_minutes"] > 0
    assert "recommendation_reason" in rec_route
    
    # Verify discrete traffic segments
    traffic_segs = rec_route["traffic_segments"]
    assert len(traffic_segs) > 0
    seg0 = traffic_segs[0]
    assert "segment_id" in seg0
    assert "road_name" in seg0
    assert "current_speed" in seg0
    assert "free_flow_speed" in seg0
    assert "congestion_score" in seg0
    assert "color" in seg0
    assert seg0["color"].startswith("#")

    # 2. Test Worldwide Live Routing mode (OSRM / TomTom)
    live_plan = router.plan_route(
        origin={"lat": 51.5074, "lon": -0.1278},
        destination={"lat": 51.5010, "lon": -0.1416}
    )
    assert live_plan["success"] is True
    assert len(live_plan["routes"]) >= 1
    assert live_plan["routes"][0]["distance_km"] > 0

def test_traffic_predictor_and_factors():
    predictor = TrafficPredictor()
    detail = predictor.predict_segment_detailed(
        segment_id="SEG014",
        road_name="Mall Road",
        road_type="Arterial",
        lanes=4,
        speed_limit=50.0,
        current_speed=19.0,
        vehicle_count=312,
        current_congestion=68,
        hour=18,
        day_of_week=2,
        nearby_incident_dist_m=400
    )
    
    assert detail["segment_id"] == "SEG014"
    assert detail["congestion_level"] in ["LOW", "MODERATE", "HEAVY", "SEVERE"]
    assert len(detail["predictions"]) == 3
    assert detail["predictions"][0]["horizon"] == "+15m"
    assert detail["predictions"][1]["horizon"] == "+30m"
    assert detail["predictions"][2]["horizon"] == "+60m"
    
    factors = detail["contributing_factors"]
    assert len(factors) >= 2
    factor_names = [f["factor"] for f in factors]
    assert any("peak" in f.lower() for f in factor_names)
    assert any("incident" in f.lower() for f in factor_names)

def test_incident_lifecycle():
    mgr = IncidentManager()
    initial_count = len(mgr.get_all())
    assert initial_count >= 2
    
    new_inc = mgr.create_incident(
        title="Overturned Tanker on Ganga Barrage",
        incident_type="Accident",
        severity="Major",
        road_segment_id="SEG002",
        latitude=26.4780,
        longitude=80.3240,
        description="Hazardous fluid spill, traffic diverted."
    )
    assert new_inc["incident_id"].startswith("INC-")
    assert len(mgr.get_all()) == initial_count + 1
    
    updated = mgr.update_status(new_inc["incident_id"], "Resolved")
    assert updated["status"] == "Resolved"

def test_providers_and_analytics():
    prov_mgr = ProviderManager()
    statuses = prov_mgr.get_all_status()
    assert len(statuses) >= 2
    assert any(s["name"] == "Kanpur Metro Simulator (Demo Engine)" for s in statuses)
    
    analytics = AnalyticsEngine()
    summary = analytics.get_summary(timeframe="24h")
    assert "avg_city_speed" in summary
    
    trends = analytics.get_trends(timeframe="24h")
    assert "hourly_trend" in trends
    assert len(trends["hourly_trend"]["labels"]) == 24
    assert len(trends["top_congested_roads"]) > 0
    
    csv_str = analytics.generate_csv_export()
    assert "Timestamp,Segment_ID,Road_Name" in csv_str

def test_auth_and_rbac():
    auth = AuthManager()
    user = auth.get_current_user()
    assert user["name"] == "R. Awasthi"
    assert user["role"] == "TRAFFIC_OPERATOR"
    
    switched = auth.switch_user("usr_admin")
    assert switched["role"] == "ADMIN"
    
    logs = auth.audit_logger.get_logs()
    assert len(logs) > 0

if __name__ == "__main__":
    print("Running Traffic Platform Test Suite...")
    test_network_graph()
    print("[PASSED] test_network_graph")
    test_geocoding_and_snapping()
    print("[PASSED] test_geocoding_and_snapping")
    test_simulator_and_scenarios()
    print("[PASSED] test_simulator_and_scenarios")
    test_smart_router_with_traffic_segments()
    print("[PASSED] test_smart_router_with_traffic_segments")
    test_traffic_predictor_and_factors()
    print("[PASSED] test_traffic_predictor_and_factors")
    test_incident_lifecycle()
    print("[PASSED] test_incident_lifecycle")
    test_providers_and_analytics()
    print("[PASSED] test_providers_and_analytics")
    test_auth_and_rbac()
    print("[PASSED] test_auth_and_rbac")
    print("\n" + "="*50)
    print("ALL 8 AUTOMATED TEST SUITES PASSED (100%)!")
    print("="*50)
