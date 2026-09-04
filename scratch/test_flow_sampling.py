import os
import requests
from dotenv import load_dotenv

load_dotenv()
key = os.getenv('TOMTOM_API_KEY')

points = [
    ('Midtown Manhattan', 40.7580, -73.9855),
    ('BQE Brooklyn', 40.7012, -73.9880),
    ('Lincoln Tunnel', 40.7615, -74.0010),
    ('JFK Expressway', 40.6550, -73.7890),
    ('Queens Blvd', 40.7300, -73.8700)
]

for name, lat, lon in points:
    url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/relative0/10/json?point={lat},{lon}&key={key}"
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json().get('flowSegmentData', {})
        cur = data.get('currentSpeed', 0)
        ff = data.get('freeFlowSpeed', 1)
        ratio = round(cur / max(1, ff), 3)
        cat = "LOW" if ratio >= 0.85 else "MODERATE" if ratio >= 0.65 else "HEAVY" if ratio >= 0.45 else "SEVERE"
        print(f"Location: {name:20s} | Current: {cur:2d} km/h | FreeFlow: {ff:2d} km/h | Ratio: {ratio:.3f} | Level: {cat}")
    else:
        print(f"Location: {name:20s} | HTTP Error {r.status_code}")
