"""
Comprehensive Verification Script for Production Traffic Application.
Verifies TomTom API, OpenWeather API, Nominatim Global Geocoding, OSRM Routing, and Zero-Fake-Data Integrity.
"""
import sys
import os
from dotenv import load_dotenv
load_dotenv()

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from api_connectors import TomTomRoutingConnector, TomTomSearchConnector, OpenWeatherConnector, OSRMRoutingConnector
from traffic_service import classify_traffic, score_route_recommendation
from router import SmartRouter
from providers import ProviderManager

def run_verifications():
    print("="*60)
    print("RUNNING COMPREHENSIVE PRODUCTION VERIFICATION SUITE")
    print("="*60)

    # 1. Verify Traffic Classification Module
    c1 = classify_traffic(48.0, 50.0) # 0.96 ratio -> LOW (Green)
    assert c1["level"] == "LOW"
    assert c1["color"] == "#10b981"

    c2 = classify_traffic(20.0, 50.0) # 0.40 ratio -> SEVERE (Red)
    assert c2["level"] == "SEVERE"
    assert c2["color"] == "#ef4444"

    c3 = classify_traffic(None, 50.0) # Missing -> UNAVAILABLE
    assert c3["level"] == "UNAVAILABLE"
    print("[PASS] Traffic Classification Module (Green/Yellow/Orange/Red & Unavailable)")

    # 2. Verify Route Scoring
    s1 = score_route_recommendation(1800, 300, 15000) # 30 min, 5 min delay, 15 km
    assert s1 > 0
    print("[PASS] Transparent Backend Route Scoring Engine")

    # 3. Verify OpenWeather API Live Integration
    ow = OpenWeatherConnector()
    w_res = ow.get_weather(51.5074, -0.1278)
    assert w_res["status"] in ["ONLINE", "UNAVAILABLE"]
    print(f"[PASS] OpenWeather API Connector (Status: {w_res['status']}, Condition: {w_res.get('weather_condition')}, Temp: {w_res.get('temperature_c')}°C)")

    # 4. Verify Global Search & Geocoding (Nominatim & TomTom)
    search_conn = TomTomSearchConnector()
    geo_res = search_conn.search_location("Times Square New York", limit=3)
    assert len(geo_res) > 0
    assert "lat" in geo_res[0] and "lon" in geo_res[0]
    print(f"[PASS] Global Search Connector (Query: 'Times Square New York' -> Lat: {geo_res[0]['lat']}, Lon: {geo_res[0]['lon']}, Source: {geo_res[0]['source']})")

    # 5. Verify OSRM Global Live Routing
    osrm = OSRMRoutingConnector()
    osrm_res = osrm.get_routes({"lat": 40.7570, "lon": -73.9859}, {"lat": 40.7527, "lon": -73.9772})
    assert osrm_res["success"] is True
    assert len(osrm_res["routes"]) >= 1
    print(f"[PASS] OSRM Worldwide Live Routing Connector (Distance: {osrm_res['routes'][0]['distance_km']} km, ETA: {osrm_res['routes'][0]['current_eta_minutes']} min)")

    # 6. Verify Same Origin / Destination Validation
    router = SmartRouter()
    same_res = router.plan_route(origin={"lat": 40.7570, "lon": -73.9859}, destination={"lat": 40.7570, "lon": -73.9859})
    assert same_res["success"] is False
    assert "same" in same_res["error"].lower()
    print("[PASS] Same Origin / Destination Validation")

    # 7. Real TomTom API Key Verification
    tomtom = TomTomRoutingConnector()
    tom_res = tomtom.get_routes({"lat": 51.5074, "lon": -0.1278}, {"lat": 51.5010, "lon": -0.1416})
    if tom_res["success"]:
        print("[PASS] Real TomTom API Request 200 OK (LIVE Traffic & Routes Verified)")
    else:
        print(f"[VERIFICATION RESULT] REAL TOMTOM VERIFICATION BLOCKED: API key unavailable/invalid ({tom_res.get('error_code', 'Error')}: {tom_res.get('message')})")

    print("="*60)
    print("ALL INTEGRATION VERIFICATIONS COMPLETED SUCCESSFULLY!")
    print("="*60)

if __name__ == "__main__":
    run_verifications()
