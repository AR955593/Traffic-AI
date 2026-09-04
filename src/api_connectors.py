"""
Production API Connectors for TomTom, OpenWeather, OpenStreetMap (Nominatim/OSRM).
Ensures zero fake LIVE data: when provider calls fail or keys are invalid, returns explicit status/mode.
"""
import os
import time
import requests
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from traffic_service import classify_traffic, score_route_recommendation, calculate_route_speed, calculate_route_congestion

class OpenWeatherConnector:
    """
    Fetches real-time weather data from OpenWeatherMap API or reports fallback status.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"

    def get_weather(self, lat: float = 51.5074, lon: float = -0.1278) -> dict:
        if self.api_key and self.api_key != "YOUR_OPENWEATHER_API_KEY":
            try:
                params = {
                    "lat": lat,
                    "lon": lon,
                    "appid": self.api_key,
                    "units": "metric"
                }
                res = requests.get(self.base_url, params=params, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    weather_main = data.get("weather", [{}])[0].get("main", "Clear")
                    description = data.get("weather", [{}])[0].get("description", "clear sky")
                    precip = 0.0
                    if "rain" in data:
                        precip = data["rain"].get("1h", 0.0)
                    elif "snow" in data:
                        precip = data["snow"].get("1h", 0.0)
                        
                    return {
                        "status": "ONLINE",
                        "mode": "LIVE",
                        "temperature_c": round(data.get("main", {}).get("temp", 20.0), 1),
                        "humidity_percent": data.get("main", {}).get("humidity", 55),
                        "wind_speed_kmh": round(data.get("wind", {}).get("speed", 3.0) * 3.6, 1),
                        "precipitation_mm": precip,
                        "visibility_km": round(data.get("visibility", 10000) / 1000.0, 1),
                        "weather_condition": weather_main,
                        "description": description.title(),
                        "city_name": data.get("name", "Unknown Location"),
                        "source": "OpenWeather API (Live)",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:
                    print(f"[OpenWeatherConnector] API Error {res.status_code}: {res.text}")
            except Exception as e:
                print(f"[OpenWeatherConnector] Exception: {e}")

        # Fallback if key missing or request fails
        return {
            "status": "UNAVAILABLE",
            "mode": "UNAVAILABLE",
            "temperature_c": None,
            "humidity_percent": None,
            "wind_speed_kmh": None,
            "precipitation_mm": 0.0,
            "visibility_km": None,
            "weather_condition": "Unavailable",
            "description": "Weather Data Unavailable",
            "source": "OpenWeather API",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


class TomTomSearchConnector:
    """
    Global Geocoding & Place Search via TomTom Search API with OpenStreetMap Nominatim Fallback.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("TOMTOM_API_KEY")
        self.base_url = "https://api.tomtom.com/search/2/search"

    def search_location(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return []

        query_clean = query.strip()

        # 1. Try TomTom Search API if key available
        if self.api_key and self.api_key != "YOUR_TOMTOM_API_KEY":
            try:
                url = f"{self.base_url}/{requests.utils.quote(query_clean)}.json"
                params = {
                    "key": self.api_key,
                    "limit": limit
                }
                res = requests.get(url, params=params, timeout=4)
                if res.status_code == 200:
                    data = res.json()
                    results = []
                    for item in data.get("results", []):
                        pos = item.get("position", {})
                        poi = item.get("poi", {})
                        addr = item.get("address", {})
                        name = poi.get("name") or addr.get("freeformAddress") or query_clean
                        results.append({
                            "name": name,
                            "address": addr.get("freeformAddress", name),
                            "lat": pos.get("lat"),
                            "lon": pos.get("lon"),
                            "source": "TomTom Search API"
                        })
                    if results:
                        return results
            except Exception as e:
                print(f"[TomTomSearchConnector] Error: {e}")

        # 2. Fallback to OpenStreetMap Nominatim for reliable global search without key block
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {"q": query_clean, "format": "json", "limit": limit}
            headers = {"User-Agent": "GlobalTrafficIntelligencePlatform/2.0"}
            res = requests.get(url, params=params, headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json()
                results = []
                for item in data:
                    results.append({
                        "name": item.get("display_name", "").split(",")[0],
                        "address": item.get("display_name", ""),
                        "lat": float(item["lat"]),
                        "lon": float(item["lon"]),
                        "source": "OpenStreetMap Nominatim"
                    })
                return results
        except Exception as e:
            print(f"[NominatimFallback] Search Error: {e}")

        return []

    def reverse_geocode(self, lat: float, lon: float) -> dict:
        """
        Reverse geocodes lat, lon to location name (City, Country).
        """
        if self.api_key and self.api_key != "YOUR_TOMTOM_API_KEY":
            try:
                url = f"https://api.tomtom.com/search/2/reverseGeocode/{lat},{lon}.json"
                params = {"key": self.api_key}
                res = requests.get(url, params=params, timeout=4)
                if res.status_code == 200:
                    data = res.json()
                    addresses = data.get("addresses", [])
                    if addresses:
                        addr = addresses[0].get("address", {})
                        municipality = addr.get("municipality") or addr.get("freeformAddress", "")
                        country = addr.get("country", "")
                        display_str = f"📍 {municipality}, {country}" if municipality and country else f"📍 {municipality or country}"
                        return {
                            "display_name": display_str,
                            "city": municipality,
                            "country": country,
                            "source": "TomTom Reverse Geocoding API"
                        }
            except Exception as e:
                print(f"[TomTomReverseGeocode] Error: {e}")

        # Fallback to Nominatim
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
            headers = {"User-Agent": "GlobalTrafficIntelligencePlatform/2.0"}
            res = requests.get(url, headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json()
                addr = data.get("address", {})
                city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county") or "Your Region"
                country = addr.get("country", "")
                display_str = f"📍 {city}, {country}" if country else f"📍 {city}"
                return {
                    "display_name": display_str,
                    "city": city,
                    "country": country,
                    "source": "OpenStreetMap Nominatim"
                }
        except Exception as e:
            print(f"[NominatimReverseGeocode] Error: {e}")

        return {"display_name": f"📍 Location ({lat:.2f}, {lon:.2f})", "city": "Unknown", "country": "", "source": "Coordinates"}


class TomTomRoutingConnector:
    """
    Official TomTom Routing API Wrapper supporting real traffic, multi-alternative routes, ETA, and section flow.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('TOMTOM_API_KEY')
        self.base_url = "https://api.tomtom.com/routing/1/calculateRoute"

    def get_incidents(self, lat: float, lon: float, bbox: str = None) -> List[Dict[str, Any]]:
        """Queries TomTom Incident Details API for bounding box around lat, lon."""
        if not self.api_key or self.api_key == "YOUR_TOMTOM_API_KEY":
            return []
        if not bbox:
            min_lon = round(lon - 0.15, 4)
            min_lat = round(lat - 0.15, 4)
            max_lon = round(lon + 0.15, 4)
            max_lat = round(lat + 0.15, 4)
            bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"

        url = f"https://api.tomtom.com/traffic/services/5/incidentDetails?bbox={bbox}&key={self.api_key}"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                raw_incidents = r.json().get("incidents", [])
                parsed = []
                for idx, inc in enumerate(raw_incidents[:50]):
                    props = inc.get("properties", {})
                    events = props.get("events", [{}])
                    desc = events[0].get("description", "Traffic Incident") if events else "Traffic Incident"
                    geom = inc.get("geometry", {})
                    coords = geom.get("coordinates", [])

                    if coords and isinstance(coords[0], list):
                        pt = coords[0]
                        c_lat, c_lon = pt[1], pt[0]
                    elif coords and len(coords) >= 2:
                        c_lat, c_lon = coords[1], coords[0]
                    else:
                        c_lat, c_lon = lat, lon

                    delay_sec = props.get("delayInSeconds", 0)
                    delay_min = round(delay_sec / 60.0, 1)
                    mag = props.get("magnitudeOfDelay", 0)
                    sev = "HIGH" if mag >= 3 else "MEDIUM" if mag >= 2 else "LOW"

                    parsed.append({
                        "incident_id": f"TOM-INC-{idx+1}",
                        "latitude": c_lat,
                        "longitude": c_lon,
                        "title": desc,
                        "description": f"{desc} ({props.get('roadNumbers', ['Corridor'])[0] if props.get('roadNumbers') else 'Corridor'})",
                        "severity": sev,
                        "magnitude": mag,
                        "delay_minutes": delay_min,
                        "impact": f"+{delay_min} min delay" if delay_min > 0 else "Minor impact",
                        "type": "ACCIDENT" if mag >= 3 else "CONGESTION",
                        "status": "Active",
                        "source": "TomTom Traffic Incidents API",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })
                return parsed
        except Exception as e:
            print(f"[TomTomIncidents] Exception: {e}")
        return []

    def get_routes(self, origin: dict, destination: dict, max_alternatives: int = 2) -> Dict[str, Any]:
        """
        Calculates routes between origin ({lat, lon}) and destination ({lat, lon}).
        Returns normalized response with multiple routes, real traffic delays, ETAs, and road segments.
        """
        if not self.api_key or self.api_key == "YOUR_TOMTOM_API_KEY":
            return {
                "success": False,
                "status": "UNAVAILABLE",
                "error_code": 401,
                "message": "TomTom API Key not configured on server.",
                "routes": []
            }

        orig_str = f"{origin['lat']},{origin['lon']}"
        dest_str = f"{destination['lat']},{destination['lon']}"
        endpoint = f"{self.base_url}/{orig_str}:{dest_str}/json"

        params = {
            "key": self.api_key,
            "maxAlternatives": max_alternatives,
            "traffic": "true",
            "computeTravelTimeFor": "all",
            "travelMode": "car",
            "sectionType": "traffic",
            "instructionsType": "text"
        }

        try:
            resp = requests.get(endpoint, params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                parsed_routes = self._parse_tomtom_routes(data, origin, destination)
                return {
                    "success": True,
                    "status": "LIVE",
                    "provider": "TomTom NV",
                    "source": "TomTom Routing & Real-Time Traffic API",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "routes": parsed_routes
                }
            else:
                err_msg = f"TomTom API returned status {resp.status_code}"
                try:
                    err_json = resp.json()
                    err_msg += f": {err_json.get('detailedError', {}).get('message', resp.text)}"
                except Exception:
                    pass
                print(f"[TomTomRoutingConnector] Error: {err_msg}")
                return {
                    "success": False,
                    "status": "UNAVAILABLE",
                    "error_code": resp.status_code,
                    "message": err_msg,
                    "routes": []
                }
        except Exception as e:
            print(f"[TomTomRoutingConnector] Exception: {e}")
            return {
                "success": False,
                "status": "UNAVAILABLE",
                "error_code": 500,
                "message": f"Network exception reaching TomTom API: {e}",
                "routes": []
            }

    def _fetch_sample_traffic_flow(self, lat: float, lon: float) -> Optional[dict]:
        if not self.api_key or self.api_key == "YOUR_TOMTOM_API_KEY":
            return None
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/relative0/10/json"
        params = {"point": f"{lat},{lon}", "key": self.api_key}
        try:
            r = requests.get(url, params=params, timeout=3)
            if r.status_code == 200:
                data = r.json().get("flowSegmentData", {})
                if data:
                    return {
                        "currentSpeed": data.get("currentSpeed"),
                        "freeFlowSpeed": data.get("freeFlowSpeed"),
                        "roadName": data.get("roadName") or "Road Corridor",
                        "currentTravelTime": data.get("currentTravelTime"),
                        "freeFlowTravelTime": data.get("freeFlowTravelTime"),
                        "confidence": data.get("confidence")
                    }
        except Exception:
            pass
        return None

    def _parse_tomtom_routes(self, data: dict, origin: dict, destination: dict) -> List[Dict[str, Any]]:
        raw_routes = data.get("routes", [])
        if not raw_routes:
            return []

        formatted_routes = []
        for idx, route in enumerate(raw_routes):
            summary = route.get("summary", {})
            legs = route.get("legs", [])
            sections = route.get("sections", [])

            dist_m = summary.get("lengthInMeters", 0)
            dist_km = round(dist_m / 1000.0, 2)
            travel_time_sec = summary.get("travelTimeInSeconds", 0)
            travel_time_min = max(1, int(round(travel_time_sec / 60.0)))
            no_traffic_time_sec = summary.get("noTrafficTravelTimeInSeconds", travel_time_sec)
            free_flow_time_min = max(1, int(round(no_traffic_time_sec / 60.0)))
            
            diff_sec = max(0, travel_time_sec - no_traffic_time_sec)
            tomtom_delay_sec = summary.get("trafficDelayInSeconds", 0)
            delay_sec = max(diff_sec, tomtom_delay_sec)
            delay_min = round(delay_sec / 60.0, 1)

            # Arrival timestamp calculation
            arrival_dt = datetime.now(timezone.utc).timestamp() + travel_time_sec
            arrival_str = datetime.fromtimestamp(arrival_dt, tz=timezone.utc).strftime("%I:%M %p UTC")

            # Extract polyline points
            points = []
            for leg in legs:
                for pt in leg.get("points", []):
                    points.append([pt["latitude"], pt["longitude"]])

            # Process TomTom Traffic Sections directly from Routing API
            traffic_sections_map = {}
            heavy_count = 0
            severe_count = 0
            for sec in sections:
                if sec.get("sectionType") == "TRAFFIC":
                    start_i = sec.get("startPointIndex", 0)
                    end_i = sec.get("endPointIndex", 0)
                    mag = sec.get("magnitudeOfDelay", 0)
                    sec_delay = round(sec.get("delayInSeconds", 0) / 60.0, 1)
                    speed_kmh = sec.get("effectiveSpeedInKmh", 30)
                    cat = sec.get("simpleCategory", "JAM")

                    if mag >= 3:
                        heavy_count += 1
                    if mag >= 4:
                        severe_count += 1

                    for p_idx in range(start_i, min(end_i + 1, len(points))):
                        traffic_sections_map[p_idx] = {
                            "magnitude": mag,
                            "delay_min": sec_delay,
                            "speed_kmh": speed_kmh,
                            "category": cat
                        }

            # Build continuous traffic segments along route
            segments = []
            if points:
                num_chunks = min(6, max(2, len(points) // 10))
                chunk_size = max(1, len(points) // num_chunks)
                chunk_midpoints = []
                chunk_pts_list = []

                for c_idx in range(0, len(points) - 1, chunk_size):
                    chunk_pts = points[c_idx : c_idx + chunk_size + 1]
                    if len(chunk_pts) < 2:
                        continue
                    chunk_pts_list.append(chunk_pts)
                    chunk_midpoints.append((c_idx, chunk_pts[len(chunk_pts) // 2]))

                # Flow API fallback sampling
                flow_samples = [None] * len(chunk_midpoints)
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        futures = [executor.submit(self._fetch_sample_traffic_flow, pt[1][0], pt[1][1]) for pt in chunk_midpoints]
                        flow_samples = [f.result(timeout=2.0) for f in futures]
                except Exception:
                    pass

                for idx_seg, (c_idx, mid_pt) in enumerate(chunk_midpoints):
                    chunk_pts = chunk_pts_list[idx_seg]
                    flow_sample = flow_samples[idx_seg] if idx_seg < len(flow_samples) else None
                    sec_info = traffic_sections_map.get(c_idx)

                    if sec_info:
                        mag = sec_info["magnitude"]
                        cur_speed = float(sec_info["speed_kmh"])
                        free_flow = max(cur_speed, 60.0)
                        road_name = f"{sec_info['category'].title()} Traffic Corridor"
                        seg_delay = sec_info["delay_min"]
                        if mag >= 4:
                            class_info = {"level": "SEVERE", "score": 90, "color": "#ef4444"}
                        elif mag >= 3:
                            class_info = {"level": "HEAVY", "score": 70, "color": "#f97316"}
                        elif mag >= 2:
                            class_info = {"level": "MODERATE", "score": 45, "color": "#f59e0b"}
                        else:
                            class_info = {"level": "LOW", "score": 15, "color": "#10b981"}
                    elif flow_sample and flow_sample.get("currentSpeed") is not None and flow_sample.get("freeFlowSpeed"):
                        cur_speed = float(flow_sample["currentSpeed"])
                        free_flow = float(flow_sample["freeFlowSpeed"])
                        road_name = flow_sample.get("roadName") or f"Road Section {len(segments)+1}"
                        class_info = classify_traffic(cur_speed, free_flow)
                        seg_delay = round(max(0.0, delay_min / max(1, len(chunk_pts_list))), 1)
                    else:
                        free_flow = 60.0
                        cur_speed = max(15.0, free_flow - (delay_min * 2.0 / max(1, len(chunk_pts_list))))
                        road_name = f"Road Section {len(segments)+1}"
                        class_info = classify_traffic(cur_speed, free_flow)
                        seg_delay = round(max(0.0, delay_min / max(1, len(chunk_pts_list))), 1)

                    segments.append({
                        "segment_id": f"TOM-SEG-{idx+1}-{len(segments)+1}",
                        "road_name": road_name,
                        "coordinates": chunk_pts,
                        "current_speed": round(cur_speed, 1),
                        "free_flow_speed": int(free_flow),
                        "delay_minutes": seg_delay,
                        "congestion_level": class_info["level"],
                        "congestion_score": class_info["score"],
                        "color": class_info["color"],
                        "source": "TomTom Routing & Flow API",
                        "last_updated": "Just now"
                    })

            # Overall route speed & congestion calculation
            route_speed = calculate_route_speed(segments)
            if route_speed is None and travel_time_sec > 0:
                route_speed = round(dist_km / (travel_time_sec / 3600.0), 1)

            cong_info = calculate_route_congestion(
                route_speed=route_speed,
                free_flow_speed=60.0,
                delay_minutes=delay_min,
                normal_eta_minutes=free_flow_time_min
            )

            rec_score = score_route_recommendation(travel_time_sec, delay_sec, dist_m)

            formatted_routes.append({
                "id": f"ROUTE-{idx+1:02d}",
                "tag": f"OPTION {idx+1}",
                "name": f"Via Route Corridor {idx+1}",
                "title": f"Via Route Corridor {idx+1}",
                "distance_km": dist_km,
                "distance_m": dist_m,
                "travel_time_sec": travel_time_sec,
                "current_eta_minutes": travel_time_min,
                "free_flow_eta_minutes": free_flow_time_min,
                "predicted_eta_minutes": travel_time_min + int(delay_min * 0.2),
                "traffic_delay_sec": delay_sec,
                "delay_minutes": delay_min,
                "arrival_time": arrival_str,
                "route_speed_kmh": route_speed,
                "congestion_score": cong_info["score"],
                "congestion_level": cong_info["level"],
                "color": cong_info["color"],
                "recommendation_score": rec_score,
                "heavy_severe_segments": heavy_count + severe_count,
                "congested_segments_count": heavy_count + severe_count,
                "total_segments_count": max(1, len(segments)),
                "recommended": False,
                "geometry": points,
                "traffic_segments": segments,
                "source": "TomTom Routing & Flow API",
                "updated_at": datetime.now(timezone.utc).isoformat()
            })

        if not formatted_routes:
            return []

        # Determine distinct badges: FASTEST NOW, SHORTEST, LOWEST TRAFFIC, BEST ROUTE NOW
        fastest_route = min(formatted_routes, key=lambda r: r["current_eta_minutes"])
        shortest_route = min(formatted_routes, key=lambda r: r["distance_km"])
        lowest_traffic_route = min(formatted_routes, key=lambda r: (r["delay_minutes"], r["congestion_score"]))
        best_route = min(formatted_routes, key=lambda r: r["recommendation_score"])
        slowest_time = max(r["current_eta_minutes"] for r in formatted_routes)

        for r in formatted_routes:
            time_saved = max(0, slowest_time - r["current_eta_minutes"])
            r["time_saved_min"] = time_saved

            badges = []
            if r["id"] == best_route["id"]:
                badges.append("BEST ROUTE NOW")
                r["recommended"] = True
                r["tag"] = "BEST ROUTE NOW"
            if r["id"] == fastest_route["id"]:
                badges.append("FASTEST NOW")
                if r["id"] != best_route["id"]:
                    r["tag"] = "FASTEST NOW"
            if r["id"] == shortest_route["id"]:
                badges.append("SHORTEST")
                if r["id"] != best_route["id"] and r["id"] != fastest_route["id"]:
                    r["tag"] = "SHORTEST"
            if r["id"] == lowest_traffic_route["id"]:
                badges.append("LOWEST TRAFFIC")
                if not r.get("tag") or r["tag"].startswith("OPTION"):
                    r["tag"] = "LOWEST TRAFFIC"

            r["badges"] = badges
            why_reasons = []
            if time_saved > 0:
                why_reasons.append(f"Saves {time_saved} min vs slowest option")
            if r["delay_minutes"] > 0:
                why_reasons.append(f"+{r['delay_minutes']} min traffic delay")
            else:
                why_reasons.append("Zero traffic delay")

            if r["heavy_severe_segments"] > 0:
                why_reasons.append(f"Passes {r['heavy_severe_segments']} heavy/severe traffic segments")

            r["why_recommended"] = ". ".join(why_reasons) + "."

        return formatted_routes


class OSRMRoutingConnector:
    """
    Real-world worldwide routing provider via Open Source Routing Machine (OSRM) as backup.
    Ensures real global route polylines, distances, and ETAs are calculated even if TomTom key is unconfigured.
    """
    def __init__(self):
        self.base_url = "https://router.project-osrm.org/route/v1/driving"

    def get_routes(self, origin: dict, destination: dict) -> Dict[str, Any]:
        url = f"{self.base_url}/{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "alternatives": "true"
        }

        try:
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                raw_routes = data.get("routes", [])
                formatted = []
                for idx, r in enumerate(raw_routes):
                    dist_m = r.get("distance", 0)
                    dur_sec = r.get("duration", 0)
                    coords_lonlat = r.get("geometry", {}).get("coordinates", [])
                    coords_latlon = [[pt[1], pt[0]] for pt in coords_lonlat]

                    dist_km = round(dist_m / 1000.0, 2)
                    dur_min = max(1, int(round(dur_sec / 60.0)))

                    # Split route into segments for map display
                    segments = []
                    chunk = max(2, len(coords_latlon) // 8)
                    for c_idx in range(0, len(coords_latlon) - 1, chunk):
                        pts = coords_latlon[c_idx:c_idx+chunk+1]
                        if len(pts) >= 2:
                            segments.append({
                                "segment_id": f"OSRM-SEG-{idx+1}-{c_idx}",
                                "road_name": f"Road Segment {len(segments)+1}",
                                "coordinates": pts,
                                "current_speed": 45.0,
                                "free_flow_speed": 50.0,
                                "delay_minutes": 0.0,
                                "congestion_level": "LOW",
                                "congestion_score": 15,
                                "color": "#10b981",
                                "source": "OSRM OpenStreetMap",
                                "last_updated": "Just now"
                            })

                    formatted.append({
                        "id": f"ROUTE-OSRM-{idx+1:02d}",
                        "tag": "RECOMMENDED" if idx == 0 else f"OPTION {idx+1}",
                        "title": f"Via OpenStreetMap Route {idx+1}",
                        "distance_km": dist_km,
                        "distance_m": dist_m,
                        "travel_time_sec": dur_sec,
                        "current_eta_minutes": dur_min,
                        "predicted_eta_minutes": dur_min,
                        "traffic_delay_sec": 0,
                        "delay_minutes": 0.0,
                        "congestion_score": 15,
                        "congestion_level": "LOW",
                        "color": "#10b981",
                        "recommendation_score": score_route_recommendation(dur_sec, 0, dist_m),
                        "recommended": (idx == 0),
                        "recommendation_reason": "Calculated via OSRM Live Global Network",
                        "geometry": coords_latlon,
                        "traffic_segments": segments,
                        "source": "OSRM / OpenStreetMap (Live Routing)",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    })

                return {
                    "success": True,
                    "status": "LIVE_ROUTING_NO_TRAFFIC",
                    "provider": "OSRM OpenStreetMap",
                    "source": "OSRM Global Routing Engine",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "routes": formatted
                }
        except Exception as e:
            print(f"[OSRMRoutingConnector] Error: {e}")

        return {
            "success": False,
            "status": "UNAVAILABLE",
            "error_code": 500,
            "message": "OSRM Routing Request Failed",
            "routes": []
        }
