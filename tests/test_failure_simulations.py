"""
Non-Destructive Failure Simulation & Resilience Test Suite for TrafficAI.
Covers:
- Database unavailable (ServerSelectionTimeoutError -> HTTP 503)
- Expired & Tampered JWT tokens (-> HTTP 401)
- Write idempotency & deduplication for saved places & routes (prevents duplicate documents)
- SQLite WAL mode & concurrency verification
- AI Assistant boundary validation & Kanpur metropolitan coordinates verification
"""
import sys
import os
import time
import threading
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from main import app
from auth import AuthManager, generate_jwt_token, decode_access_token
from user_service import UserService
from db import get_db_connection
from mongo_db import get_mongo_db

client = TestClient(app)
auth = AuthManager()
user_service = UserService()

# -------------------------------------------------------------------
# 1. DATABASE UNAVAILABILITY (SCENARIO 1 & 37)
# -------------------------------------------------------------------
def test_sim_database_unavailable_returns_503():
    """
    Simulates a complete MongoDB connection timeout/outage.
    Verifies that FastAPI catches ServerSelectionTimeoutError and returns a clean HTTP 503 JSON envelope.
    """
    token = generate_jwt_token("usr_resilience_test", "resilience@test.com", "USER", "Resilience User")
    headers = {"Authorization": f"Bearer {token}"}

    with patch("main.auth_manager.get_user_by_id", side_effect=ServerSelectionTimeoutError("Timed out reaching MongoDB server")):
        response = client.get("/api/v1/user/places", headers=headers)
        assert response.status_code == 503
        data = response.json()
        assert data.get("code") == "DATABASE_UNAVAILABLE" or "temporarily unavailable" in data.get("detail", "").lower()

# -------------------------------------------------------------------
# 2. TOKEN EXPIRATION & TAMPERING (SCENARIO 14 & 15)
# -------------------------------------------------------------------
def test_sim_expired_token_returns_401():
    """
    Simulates a request with an expired JWT access token.
    Verifies HTTP 401 is strictly enforced.
    """
    import jwt
    from datetime import datetime, timezone, timedelta
    from auth import SECRET_KEY, ALGORITHM

    expired_payload = {
        "sub": "usr_expired_123",
        "email": "expired@test.com",
        "role": "USER",
        "exp": datetime.now(timezone.utc) - timedelta(hours=2)
    }
    expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)

    response = client.get("/api/v1/user/places", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()

def test_sim_tampered_token_returns_401():
    """
    Simulates a request with an invalid or tampered JWT.
    Verifies HTTP 401 is strictly enforced.
    """
    response = client.get("/api/v1/user/places", headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.tampered.signature"})
    assert response.status_code == 401

# -------------------------------------------------------------------
# 3. WRITE IDEMPOTENCY & DEDUPLICATION (SCENARIOS 19, 20, 21)
# -------------------------------------------------------------------
def test_sim_idempotent_place_saving_prevents_duplicate():
    """
    Simulates a double-tap / retry on saved places.
    Verifies that the second call returns the existing record without inserting duplicate documents.
    """
    test_user_id = "usr_idempotency_test"
    db = get_mongo_db()
    db.saved_places.delete_many({"user_id": test_user_id})

    # Call 1
    place1 = user_service.add_saved_place(
        user_id=test_user_id,
        label="Home",
        custom_name="My Sweet Home",
        address="100 Civil Lines, Kanpur",
        lat=26.4670,
        lon=80.3500
    )
    assert place1 is not None
    place_id_1 = place1["id"]

    # Call 2 (identical submission simulated from retry or double click)
    place2 = user_service.add_saved_place(
        user_id=test_user_id,
        label="Home",
        custom_name="My Sweet Home",
        address="100 Civil Lines, Kanpur",
        lat=26.4670,
        lon=80.3500
    )
    assert place2 is not None
    # Idempotency check: must return existing record
    assert place2["id"] == place_id_1

    # Verify database count is exactly 1, not 2
    count = db.saved_places.count_documents({"user_id": test_user_id})
    assert count == 1

    # Cleanup
    db.saved_places.delete_many({"user_id": test_user_id})

def test_sim_idempotent_route_saving_prevents_duplicate():
    """
    Simulates a duplicate route save retry.
    Verifies that identical coordinates return the existing route without duplicate insertion.
    """
    test_user_id = "usr_idempotency_route_test"
    db = get_mongo_db()
    db.saved_routes.delete_many({"user_id": test_user_id})

    # Call 1
    route1 = user_service.add_saved_route(
        user_id=test_user_id,
        title="Office Commute",
        origin_name="Civil Lines",
        origin_lat=26.4700,
        origin_lon=80.3500,
        dest_name="IIT Kanpur",
        dest_lat=26.5123,
        dest_lon=80.2329
    )
    route_id_1 = route1["id"]

    # Call 2 (retry)
    route2 = user_service.add_saved_route(
        user_id=test_user_id,
        title="Office Commute",
        origin_name="Civil Lines",
        origin_lat=26.4700,
        origin_lon=80.3500,
        dest_name="IIT Kanpur",
        dest_lat=26.5123,
        dest_lon=80.2329
    )
    assert route2["id"] == route_id_1

    # Verify count is 1
    count = db.saved_routes.count_documents({"user_id": test_user_id})
    assert count == 1

    # Cleanup
    db.saved_routes.delete_many({"user_id": test_user_id})

# -------------------------------------------------------------------
# 4. SQLITE WAL MODE & CONCURRENCY (SCENARIO 22)
# -------------------------------------------------------------------
def test_sim_sqlite_wal_mode_and_concurrency():
    """
    Verifies SQLite is configured with WAL journal mode and handles concurrent writes without lock errors.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"

    # Multi-threaded concurrent write test
    errors = []
    def write_worker(idx):
        try:
            c = get_db_connection()
            c.execute(
                "INSERT INTO audit_logs (id, user_id, user_name, action, entity_type, entity_id, details, timestamp, client_ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"test_conc_{idx}_{time.time()}", "u_conc", "Conc User", "TEST_CONC", "SYSTEM", "NONE", f"Worker {idx}", "2026-09-22T00:00:00Z", "127.0.0.1")
            )
            c.commit()
            c.close()
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=write_worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent SQLite writes raised errors: {errors}"

    # Cleanup test records
    cleanup_conn = get_db_connection()
    cleanup_conn.execute("DELETE FROM audit_logs WHERE user_id = 'u_conc'")
    cleanup_conn.commit()
    cleanup_conn.close()

# -------------------------------------------------------------------
# 5. BOUNDARY INPUT & KANPUR COORDINATES (SCENARIO 38, 40)
# -------------------------------------------------------------------
def test_sim_ai_assistant_empty_or_null_query_returns_400():
    """
    Sends empty / null query to /api/v1/assistant/chat.
    Verifies clean HTTP 400 response without unhandled AttributeError.
    """
    response = client.post("/api/v1/assistant/chat", json={"query": "", "message": None})
    assert response.status_code == 400
    assert "required" in response.json()["detail"].lower()

def test_sim_ai_assistant_uses_kanpur_coordinates():
    """
    Verifies that AI assistant queries Kanpur coordinates (26.4499, 80.3319) rather than London coordinates.
    """
    with patch("main.tomtom_routing_connector.get_incidents") as mock_incidents, \
         patch("main.weather_connector.get_weather") as mock_weather:
        mock_incidents.return_value = []
        mock_weather.return_value = {"weather_condition": "Clear", "temperature_c": 28.0}

        response = client.post("/api/v1/assistant/chat", json={"query": "What is traffic like right now?"})
        assert response.status_code == 200

        # Verify called with Kanpur coordinates
        mock_incidents.assert_called_once()
        call_args = mock_incidents.call_args[0]
        lat, lon = call_args[0], call_args[1]
        assert abs(lat - 26.4499) < 0.01
        assert abs(lon - 80.3319) < 0.01
