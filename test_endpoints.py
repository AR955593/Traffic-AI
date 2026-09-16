import requests
import json
import uuid

BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_endpoints():
    errors = []
    
    # 1. Register & Login
    unique_email = f"test_{uuid.uuid4().hex[:6]}@example.com"
    res = requests.post(f"{BASE_URL}/auth/register", json={
        "name": "Test User",
        "email": unique_email,
        "password": "Password123!",
        "city": "Kanpur"
    })
    
    if res.status_code != 200:
        errors.append(f"Register failed: {res.text}")
        return errors
        
    token = res.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test Auth Me
    res = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    if res.status_code != 200:
        errors.append(f"Auth Me failed: {res.text}")

    # Test Live Traffic
    res = requests.get(f"{BASE_URL}/traffic/live?lat=51.5074&lon=-0.1278")
    if res.status_code != 200:
        errors.append(f"Live Traffic failed: {res.text}")

    # Test Route Plan
    res = requests.post(f"{BASE_URL}/routes/plan", json={
        "origin": {"lat": 51.5074, "lon": -0.1278},
        "destination": {"lat": 51.5010, "lon": -0.1416},
        "preference": "fastest",
        "mode": "DEMO"
    })
    if res.status_code != 200:
        errors.append(f"Route Plan failed: {res.text}")
        
    # Test Assistant Chat
    res = requests.post(f"{BASE_URL}/assistant/chat", json={
        "message": "Hello, how is the traffic?",
        "context": {"lat": 51.5, "lon": -0.1}
    })
    if res.status_code != 200:
        errors.append(f"Assistant Chat failed: {res.text}")

    # Test User Places
    res = requests.get(f"{BASE_URL}/user/places", headers=headers)
    if res.status_code != 200:
        errors.append(f"User Places failed: {res.text}")
        
    # Test User Trips
    res = requests.get(f"{BASE_URL}/user/trips", headers=headers)
    if res.status_code != 200:
        errors.append(f"User Trips failed: {res.text}")

    # Print results
    if errors:
        print("ERRORS FOUND:")
        for e in errors:
            print("-", e)
    else:
        print("ALL ENDPOINTS PASSED")

if __name__ == "__main__":
    test_endpoints()
