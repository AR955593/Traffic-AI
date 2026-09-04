import os
import requests
from dotenv import load_dotenv

load_dotenv()
key = os.getenv('TOMTOM_API_KEY')

cities = [
    ("London", 51.5074, -0.1278),
    ("New York", 40.7128, -74.0060),
    ("Kanpur", 26.4499, 80.3319),
    ("Delhi", 28.6139, 77.2090)
]

for name, lat, lon in cities:
    min_lon = round(lon - 0.15, 4)
    min_lat = round(lat - 0.15, 4)
    max_lon = round(lon + 0.15, 4)
    max_lat = round(lat + 0.15, 4)
    bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    
    url = f"https://api.tomtom.com/traffic/services/5/incidentDetails?bbox={bbox}&key={key}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            incidents = r.json().get("incidents", [])
            print(f"City: {name:10s} | BBox: {bbox} | Incidents Count: {len(incidents)}")
            if incidents:
                inc0 = incidents[0].get("properties", {})
                events = inc0.get("events", [{}])
                desc = events[0].get("description", "Traffic Incident") if events else "Traffic Incident"
                delay = round(inc0.get("delayInSeconds", 0) / 60.0, 1)
                print(f"   Sample Incident: {desc} | Delay: +{delay} min | Magnitude: {inc0.get('magnitudeOfDelay')}")
        else:
            print(f"City: {name:10s} | HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"City: {name:10s} | Exception: {e}")
