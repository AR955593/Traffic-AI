import sys
import os
import pytest
from fastapi.testclient import TestClient

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_dir)
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from app.main import app
from auth import AuthManager, compute_initials
from mongo_db import get_mongo_db

client = TestClient(app)

def test_initials_computation_specification():
    """Verifies the exact requirements from Section 3 of the prompt:
    'Ankit Rajput' -> AR
    'Rahul Sharma' -> RS
    'Ravi' -> R
    'Traffic User' -> TU
    """
    assert compute_initials("Ankit Rajput") == "AR"
    assert compute_initials("Rahul Sharma") == "RS"
    assert compute_initials("Ravi") == "R"
    assert compute_initials("Traffic User") == "TU"
    assert compute_initials("Ankit") == "A"
    assert compute_initials("") == "U"

def test_multi_user_isolation_end_to_end():
    """
    Section 14 & 60: Multi-user isolation test:
    - User A: create Home, route, trip
    - User B: verify User B CANNOT see User A's places, routes, trips
    - User A: verify data still exists
    """
    db = get_mongo_db()
    email_a = "user_a_multi@traffic.ai"
    email_b = "user_b_multi@traffic.ai"
    db.users.delete_many({"email_normalized": {"$in": [email_a, email_b]}})

    # 1. Register User A
    reg_a = client.post("/api/v1/auth/register", json={
        "email": email_a,
        "password": "PasswordA123!",
        "name": "User Alpha"
    })
    assert reg_a.status_code == 200
    token_a = reg_a.json()["token"]
    user_a_id = reg_a.json()["user"]["id"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 2. User A creates Saved Place
    place_resp = client.post("/api/v1/user/places", headers=headers_a, json={
        "label": "Home",
        "custom_name": "Alpha Residence",
        "address": "Civil Lines, Kanpur",
        "lat": 26.47,
        "lon": 80.35
    })
    assert place_resp.status_code == 200

    # 3. User A creates Saved Route
    route_resp = client.post("/api/v1/user/routes", headers=headers_a, json={
        "title": "Alpha Commute",
        "origin_name": "Home",
        "origin_lat": 26.47,
        "origin_lon": 80.35,
        "dest_name": "Work",
        "dest_lat": 26.50,
        "dest_lon": 80.30,
        "preference": "balanced"
    })
    assert route_resp.status_code == 200

    # 4. User A records a Trip
    trip_resp = client.post("/api/v1/user/trips", headers=headers_a, json={
        "origin_name": "Home",
        "dest_name": "Work",
        "distance_km": 14.5,
        "duration_min": 25,
        "est_duration_min": 22,
        "route_used": "GT Road Fast"
    })
    assert trip_resp.status_code == 200

    # 5. Register User B
    reg_b = client.post("/api/v1/auth/register", json={
        "email": email_b,
        "password": "PasswordB456!",
        "name": "User Beta"
    })
    assert reg_b.status_code == 200
    token_b = reg_b.json()["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 6. User B verifies they see ZERO places, routes, or trips
    b_places = client.get("/api/v1/user/places", headers=headers_b).json()
    b_routes = client.get("/api/v1/user/routes", headers=headers_b).json()
    b_trips = client.get("/api/v1/user/trips", headers=headers_b).json()

    assert len(b_places) == 0, "User B should not see User A's places"
    assert len(b_routes) == 0, "User B should not see User A's routes"
    assert len(b_trips["history"]) == 0, "User B should not see User A's trips"

    # 7. User A logs in or queries profile and verifies data is intact
    a_places = client.get("/api/v1/user/places", headers=headers_a).json()
    a_routes = client.get("/api/v1/user/routes", headers=headers_a).json()
    a_trips = client.get("/api/v1/user/trips", headers=headers_a).json()

    assert len(a_places) == 1
    assert a_places[0]["custom_name"] == "Alpha Residence"
    assert len(a_routes) == 1
    assert a_routes[0]["title"] == "Alpha Commute"
    assert len(a_trips["history"]) == 1
    assert a_trips["history"][0]["origin_name"] == "Home"

    # 8. Clean up
    del_a = client.delete("/api/v1/user/account", headers=headers_a)
    del_b = client.delete("/api/v1/user/account", headers=headers_b)
    assert del_a.status_code == 200
    assert del_b.status_code == 200
