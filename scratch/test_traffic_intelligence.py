import requests

def test_routes():
    test_cases = [
        ("Delhi -> Gurugram", {'lat': 28.6139, 'lon': 77.2090}, {'lat': 28.4595, 'lon': 77.0266}),
        ("London -> Heathrow", {'lat': 51.5074, 'lon': -0.1278}, {'lat': 51.4700, 'lon': -0.4543}),
        ("New York -> JFK Airport", {'lat': 40.7128, 'lon': -74.0060}, {'lat': 40.6413, 'lon': -73.7781})
    ]

    for title, orig, dest in test_cases:
        print(f"\n==========================================")
        print(f"TESTING: {title}")
        print(f"==========================================")
        payload = {'origin': orig, 'destination': dest, 'preference': 'balanced'}
        r = requests.post('http://127.0.0.1:8000/api/v1/routes/plan', json=payload)
        print("HTTP Status:", r.status_code)
        data = r.json()
        print("Provider:", data.get("provider"))
        print("Routes Count:", len(data.get("routes", [])))
        
        for i, route in enumerate(data.get("routes", [])):
            print(f"\n--- ROUTE {i+1}: {route.get('tag')} ---")
            print("Badges:", route.get("badges"))
            print("Current ETA:", route.get("current_eta_minutes"), "min")
            print("Normal ETA:", route.get("free_flow_eta_minutes"), "min")
            print("Traffic Delay:", route.get("delay_minutes"), "min")
            print("Distance:", route.get("distance_km"), "km")
            print("Congestion Level:", route.get("congestion_level"))
            print("Heavy/Severe Segs:", route.get("heavy_severe_segments"))
            print("Time Saved:", route.get("time_saved_min"), "min")
            print("Why Recommended:", route.get("why_recommended"))
            print("Traffic Segments Count:", len(route.get("traffic_segments", [])))
            if route.get("traffic_segments"):
                first_seg = route["traffic_segments"][0]
                print("Segment 1:", first_seg["road_name"], "-", first_seg["congestion_level"], f"({first_seg['current_speed']} km/h vs {first_seg['free_flow_speed']} km/h)")

if __name__ == "__main__":
    test_routes()
