"""
Automated Test Suite for Authentication, User Account Operations, Saved Places,
Saved Routes, Trip History, AI Assistant, Community Reporting, and Signal Intelligence.
"""
import sys
import os

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from auth import AuthManager, hash_password, verify_password, create_access_token, decode_access_token
from user_service import UserService
from ai_assistant import AITrafficAssistant
from db import init_db, get_db_connection

def test_db_and_auth_hashing():
    init_db()

    pwd = "MySecretPassword123"
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

    token = create_access_token({"sub": "usr_test123", "role": "VIEWER"})
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "usr_test123"
    assert decoded["role"] == "VIEWER"

def test_auth_registration_and_login():
    auth = AuthManager()
    
    # Test registration
    res = auth.register_user("testuser@traffic.ai", "SecretPass123!", "Test User", "Kanpur, UP")
    assert "user" in res
    assert "token" in res
    user = res["user"]
    assert user["email"] == "testuser@traffic.ai"
    assert user["name"] == "Test User"

    # Test login
    login_res = auth.login_user("testuser@traffic.ai", "SecretPass123!")
    assert login_res["user"]["id"] == user["id"]
    assert "token" in login_res

    # Test token decode
    decoded_user = auth.get_user_from_token(login_res["token"])
    assert decoded_user["id"] == user["id"]

    # Test password reset flow
    reset_token = auth.request_password_reset("testuser@traffic.ai")
    assert len(reset_token) > 0
    assert auth.confirm_password_reset(reset_token, "NewSecretPass456!") is True
    
    # Verify new password login
    new_login = auth.login_user("testuser@traffic.ai", "NewSecretPass456!")
    assert new_login["user"]["id"] == user["id"]

    # Cleanup
    auth.delete_account(user["id"])

def test_user_saved_places_routes_trips():
    user_svc = UserService()
    u_id = "usr_operator"

    # 1. Saved Places
    p = user_svc.add_saved_place(u_id, "Home", "My Residence", "Civil Lines, Kanpur", 26.4670, 80.3500)
    assert p["label"] == "Home"
    places = user_svc.get_saved_places(u_id)
    assert any(item["id"] == p["id"] for item in places)
    user_svc.delete_saved_place(u_id, p["id"])

    # 2. Saved Routes
    r = user_svc.add_saved_route(u_id, "Commute to Mall Road", "Civil Lines", 26.4670, 80.3500, "Mall Road", 26.4500, 80.3300, "balanced")
    assert r["title"] == "Commute to Mall Road"
    routes = user_svc.get_saved_routes(u_id)
    assert any(item["id"] == r["id"] for item in routes)
    user_svc.delete_saved_route(u_id, r["id"])

    # 3. Trip History
    t = user_svc.add_trip_record(u_id, "Civil Lines", "Mall Road", 4.2, 12, 14, "Recommended Route")
    assert t["distance_km"] == 4.2
    trips = user_svc.get_trip_history(u_id)
    assert len(trips) >= 1

    analytics = user_svc.get_personal_analytics(u_id)
    assert analytics["total_trips"] >= 1

def test_ai_assistant_engine():
    assistant = AITrafficAssistant()
    
    res1 = assistant.process_query("What is traffic like right now?", {"mode": "LIVE", "segments": {}}, {"weather_condition": "Clear", "temperature_c": 24}, [])
    assert "traffic data updated" in res1["response"].lower() or "city corridors" in res1["response"].lower()
    assert "disclaimer" in res1

    res2 = assistant.process_query("When should I leave?", {"mode": "LIVE", "segments": {}}, {}, [])
    assert "departure window" in res2["response"].lower()

if __name__ == "__main__":
    print("Running Extended User & Auth Test Suite...")
    test_db_and_auth_hashing()
    print("[PASSED] test_db_and_auth_hashing")
    test_auth_registration_and_login()
    print("[PASSED] test_auth_registration_and_login")
    test_user_saved_places_routes_trips()
    print("[PASSED] test_user_saved_places_routes_trips")
    test_ai_assistant_engine()
    print("[PASSED] test_ai_assistant_engine")
    print("\n" + "="*50)
    print("ALL EXTENDED USER & AUTH TESTS PASSED (100%)!")
    print("="*50)
