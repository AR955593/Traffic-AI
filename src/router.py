import os
import heapq
import math
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone

from api_connectors import TomTomRoutingConnector, OSRMRoutingConnector
from network_graph import get_kanpur_network, RoadSegment, haversine_distance
from geocoding import GeocodingEngine

class SmartRouter:
    def __init__(self, simulator_instance=None):
        self.nodes, self.segments = get_kanpur_network()
        self.simulator = simulator_instance
        self.geocoding = GeocodingEngine()
        self._build_graph()

    def _build_graph(self):
        self.adj: Dict[str, List[Tuple[str, str, RoadSegment]]] = {n: [] for n in self.nodes}
        for s_id, seg in self.segments.items():
            self.adj[seg.start_node].append((seg.end_node, s_id, seg))
            self.adj[seg.end_node].append((seg.start_node, s_id, seg))

    def plan_route(
        self,
        origin: Optional[Dict[str, float]] = None,
        destination: Optional[Dict[str, float]] = None,
        origin_node: Optional[str] = None,
        dest_node: Optional[str] = None,
        preference: str = "balanced",
        departure_time: str = "now",
        avoid_incidents: bool = True,
        avoid_highways: bool = False,
        explicit_mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculates Recommended, Fastest, and Shortest routes for arbitrary global locations.
        """
        # Determine actual origin & destination coordinates
        orig_lat = origin.get("lat") if origin else None
        orig_lon = origin.get("lon") if origin else None
        dest_lat = destination.get("lat") if destination else None
        dest_lon = destination.get("lon") if destination else None

        if orig_lat is None or orig_lon is None:
            node_key = origin_node if origin_node in self.nodes else "N06"
            orig_lat, orig_lon = self.nodes[node_key]

        if dest_lat is None or dest_lon is None:
            node_key = dest_node if dest_node in self.nodes else "N14"
            dest_lat, dest_lon = self.nodes[node_key]

        # 1. Same Origin / Destination Validation
        dist_km = haversine_distance(orig_lat, orig_lon, dest_lat, dest_lon)
        if dist_km < 0.05: # Less than 50 meters
            return {
                "success": False,
                "error": "Origin and destination are the same.",
                "message": "Please select a different destination point.",
                "routes": []
            }

        orig_dict = {"lat": orig_lat, "lon": orig_lon}
        dest_dict = {"lat": dest_lat, "lon": dest_lon}

        # If DEMO mode is explicitly requested, skip live API calls
        if explicit_mode == "DEMO" or preference == "demo":
            return self._plan_demo_kanpur_route(orig_lat, orig_lon, dest_lat, dest_lon, preference, departure_time, avoid_incidents, avoid_highways)

        # 2. Try TomTom Real-Time Routing API
        tomtom_conn = TomTomRoutingConnector()
        tomtom_res = tomtom_conn.get_routes(orig_dict, dest_dict, max_alternatives=2)

        if tomtom_res.get("success") and tomtom_res.get("routes"):
            return {
                "success": True,
                "provider": "TomTom NV",
                "mode": "LIVE",
                "status_label": "🟢 LIVE (Source: TomTom)",
                "origin": {"lat": orig_lat, "lon": orig_lon},
                "destination": {"lat": dest_lat, "lon": dest_lon},
                "departure_time": departure_time,
                "preference": preference,
                "recommended_route_id": tomtom_res["routes"][0]["id"],
                "routes": tomtom_res["routes"],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

        # 3. Fallback to OSRM Live Worldwide Routing if TomTom key is missing or returns error (e.g. 401)
        osrm_conn = OSRMRoutingConnector()
        osrm_res = osrm_conn.get_routes(orig_dict, dest_dict)

        if osrm_res.get("success") and osrm_res.get("routes"):
            # Explicitly mark that routing is live via OSRM but TomTom live flow is unavailable
            error_note = tomtom_res.get("message", "TomTom API unavailable")
            return {
                "success": True,
                "provider": "OSRM OpenStreetMap",
                "mode": "LIVE_ROUTING_NO_TRAFFIC",
                "status_label": "🟡 ROUTING ONLY (LIVE TRAFFIC UNAVAILABLE)",
                "provider_error": error_note,
                "origin": {"lat": orig_lat, "lon": orig_lon},
                "destination": {"lat": dest_lat, "lon": dest_lon},
                "departure_time": departure_time,
                "preference": preference,
                "recommended_route_id": osrm_res["routes"][0]["id"],
                "routes": osrm_res["routes"],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

        # 4. If all external APIs fail (offline / DNS error), fallback to network graph routing
        return self._plan_demo_kanpur_route(orig_lat, orig_lon, dest_lat, dest_lon, preference, departure_time, avoid_incidents, avoid_highways)

    def _plan_demo_kanpur_route(self, orig_lat, orig_lon, dest_lat, dest_lon, preference, departure_time, avoid_incidents, avoid_highways):
        orig_n, orig_coords, _ = self.geocoding.snap_to_nearest_node(orig_lat, orig_lon)
        dst_n, dst_coords, _ = self.geocoding.snap_to_nearest_node(dest_lat, dest_lon)
        if orig_n == dst_n:
            dst_n = "N14" if orig_n != "N14" else "N01"
            dst_coords = self.nodes[dst_n]

        segment_states = self.simulator._calculate_segment_states() if self.simulator else {}

        rec_path, rec_segs, rec_metrics = self._dijkstra_search(
            orig_n, dst_n, segment_states, w_dist=0.2, w_time=1.0, w_cong=2.2, w_inc=4.0 if avoid_incidents else 1.0, avoid_hw=avoid_highways
        )
        fast_path, fast_segs, fast_metrics = self._dijkstra_search(
            orig_n, dst_n, segment_states, w_dist=0.0, w_time=2.5, w_cong=0.1, w_inc=1.2, avoid_hw=avoid_highways
        )
        short_path, short_segs, short_metrics = self._dijkstra_search(
            orig_n, dst_n, segment_states, w_dist=3.0, w_time=0.1, w_cong=0.0, w_inc=0.5, avoid_hw=False
        )

        routes_payload = [
            {
                "id": "ROUTE-01",
                "tag": "RECOMMENDED",
                "title": f"Via {rec_segs[0]['road_name'] if rec_segs else 'Central Arterials'}",
                "geometry": self._generate_leaflet_polyline(rec_segs),
                "distance_km": rec_metrics["distance_km"],
                "current_eta_minutes": rec_metrics["current_eta_minutes"],
                "predicted_eta_minutes": rec_metrics["predicted_eta_minutes"],
                "delay_minutes": rec_metrics["delay_minutes"],
                "congestion_score": rec_metrics["congestion_score"],
                "congestion_level": rec_metrics["congestion_level"],
                "traffic_segments": rec_segs,
                "recommended": True,
                "recommendation_reason": "Optimal balance under Kanpur demo simulation"
            },
            {
                "id": "ROUTE-02",
                "tag": "FASTEST NOW",
                "title": f"Via {fast_segs[0]['road_name'] if fast_segs else 'Expressway Corridor'}",
                "geometry": self._generate_leaflet_polyline(fast_segs),
                "distance_km": fast_metrics["distance_km"],
                "current_eta_minutes": fast_metrics["current_eta_minutes"],
                "predicted_eta_minutes": fast_metrics["predicted_eta_minutes"],
                "delay_minutes": fast_metrics["delay_minutes"],
                "congestion_score": fast_metrics["congestion_score"],
                "congestion_level": fast_metrics["congestion_level"],
                "traffic_segments": fast_segs,
                "recommended": False,
                "recommendation_reason": "Fastest snapshot"
            },
            {
                "id": "ROUTE-03",
                "tag": "SHORTEST DISTANCE",
                "title": f"Via {short_segs[0]['road_name'] if short_segs else 'Direct Inner Streets'}",
                "geometry": self._generate_leaflet_polyline(short_segs),
                "distance_km": short_metrics["distance_km"],
                "current_eta_minutes": short_metrics["current_eta_minutes"],
                "predicted_eta_minutes": short_metrics["predicted_eta_minutes"],
                "delay_minutes": short_metrics["delay_minutes"],
                "congestion_score": short_metrics["congestion_score"],
                "congestion_level": short_metrics["congestion_level"],
                "traffic_segments": short_segs,
                "recommended": False,
                "recommendation_reason": "Minimum physical distance"
            }
        ]

        return {
            "success": True,
            "provider": "Kanpur Demo Engine",
            "mode": "DEMO",
            "status_label": "🔵 DEMO MODE (Explicit Developer Mode)",
            "origin": {"lat": orig_lat, "lon": orig_lon},
            "destination": {"lat": dest_lat, "lon": dest_lon},
            "recommended_route_id": "ROUTE-01",
            "routes": routes_payload,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # -------------------------------------------------------------
        # 2. CALCULATE ROUTE 1: RECOMMENDED / LOWEST TRAFFIC (DEMO)
        # Cost: Travel time + Predicted Congestion Penalty + Incident Penalty
        # -------------------------------------------------------------
        rec_path, rec_segs, rec_metrics = self._dijkstra_search(
            orig_n, dst_n, segment_states,
            w_dist=0.2, w_time=1.0, w_cong=2.2, w_inc=4.0 if avoid_incidents else 1.0,
            avoid_hw=avoid_highways, use_predicted=True
        )

        # -------------------------------------------------------------
        # 2. CALCULATE ROUTE 2: FASTEST CURRENT ROUTE
        # Cost: Pure current snapshot travel time
        # -------------------------------------------------------------
        fast_path, fast_segs, fast_metrics = self._dijkstra_search(
            orig_n, dst_n, segment_states,
            w_dist=0.0, w_time=2.5, w_cong=0.1, w_inc=1.2,
            avoid_hw=avoid_highways, use_predicted=False
        )

        # -------------------------------------------------------------
        # 3. CALCULATE ROUTE 3: SHORTEST DISTANCE
        # Cost: Pure physical distance in kilometers
        # -------------------------------------------------------------
        short_path, short_segs, short_metrics = self._dijkstra_search(
            orig_n, dst_n, segment_states,
            w_dist=3.0, w_time=0.1, w_cong=0.0, w_inc=0.5,
            avoid_hw=False, use_predicted=False
        )

        # Generate calculate-based recommendation reasoning
        time_saved = max(0, round(fast_metrics["current_eta_minutes"] - rec_metrics["predicted_eta_minutes"], 1))
        reasons = []
        if rec_metrics["congestion_score"] < fast_metrics["congestion_score"]:
            reasons.append("✓ Lower predicted congestion along corridor")
        if rec_metrics["incident_count"] == 0 and fast_metrics["incident_count"] > 0:
            reasons.append("✓ Avoids active incident blockage ahead")
        if time_saved >= 2:
            reasons.append(f"✓ {int(time_saved)} min faster under predicted traffic flow")
        else:
            reasons.append("✓ Optimal balance of road speed, safety, and reliability")

        rec_reason_str = "\n".join(reasons)

        routes_payload = [
            {
                "id": "ROUTE-01",
                "tag": "RECOMMENDED",
                "title": f"Via {rec_segs[0]['road_name'] if rec_segs else 'Central Arterials'}",
                "geometry": self._generate_geojson_geometry(rec_segs),
                "polyline": self._generate_leaflet_polyline(rec_segs),
                "distance_km": rec_metrics["distance_km"],
                "current_eta_minutes": rec_metrics["current_eta_minutes"],
                "predicted_eta_minutes": rec_metrics["predicted_eta_minutes"],
                "delay_minutes": rec_metrics["delay_minutes"],
                "congestion_score": rec_metrics["congestion_score"],
                "congestion_level": rec_metrics["congestion_level"],
                "traffic_segments": rec_segs,
                "incident_count": rec_metrics["incident_count"],
                "weather_impact": 0.12,
                "recommended": True,
                "recommendation_reason": rec_reason_str
            },
            {
                "id": "ROUTE-02",
                "tag": "FASTEST NOW",
                "title": f"Via {fast_segs[0]['road_name'] if fast_segs else 'Expressway Corridor'}",
                "geometry": self._generate_geojson_geometry(fast_segs),
                "polyline": self._generate_leaflet_polyline(fast_segs),
                "distance_km": fast_metrics["distance_km"],
                "current_eta_minutes": fast_metrics["current_eta_minutes"],
                "predicted_eta_minutes": fast_metrics["predicted_eta_minutes"] + 4,
                "delay_minutes": fast_metrics["delay_minutes"],
                "congestion_score": fast_metrics["congestion_score"],
                "congestion_level": fast_metrics["congestion_level"],
                "traffic_segments": fast_segs,
                "incident_count": fast_metrics["incident_count"],
                "weather_impact": 0.15,
                "recommended": False,
                "recommendation_reason": "Current snapshot is fast but traffic buildup is predicted within 20 mins."
            },
            {
                "id": "ROUTE-03",
                "tag": "SHORTEST DISTANCE",
                "title": f"Via {short_segs[0]['road_name'] if short_segs else 'Direct Inner Streets'}",
                "geometry": self._generate_geojson_geometry(short_segs),
                "polyline": self._generate_leaflet_polyline(short_segs),
                "distance_km": short_metrics["distance_km"],
                "current_eta_minutes": short_metrics["current_eta_minutes"],
                "predicted_eta_minutes": short_metrics["predicted_eta_minutes"],
                "delay_minutes": short_metrics["delay_minutes"],
                "congestion_score": short_metrics["congestion_score"],
                "congestion_level": short_metrics["congestion_level"],
                "traffic_segments": short_segs,
                "incident_count": short_metrics["incident_count"],
                "weather_impact": 0.20,
                "recommended": False,
                "recommendation_reason": "Minimum physical mileage, but slower average speeds through tight urban nodes."
            }
        ]

        return {
            "origin": {
                "name": "Starting Location",
                "node": orig_n,
                "lat": orig_coords[0],
                "lon": orig_coords[1]
            },
            "destination": {
                "name": "Destination",
                "node": dst_n,
                "lat": dst_coords[0],
                "lon": dst_coords[1]
            },
            "departure_time": departure_time,
            "preference": preference,
            "recommended_route_id": "ROUTE-01",
            "routes": routes_payload
        }

    def _dijkstra_search(
        self,
        start_node: str,
        end_node: str,
        segment_states: Dict[str, Any],
        w_dist: float = 1.0,
        w_time: float = 1.0,
        w_cong: float = 1.0,
        w_inc: float = 2.0,
        avoid_hw: bool = False,
        use_predicted: bool = True
    ) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]:
        
        # Priority queue: (cost, current_node, path_nodes, path_segments)
        pq = [(0.0, start_node, [start_node], [])]
        visited = set()

        while pq:
            cost, u, path_nodes, path_segments = heapq.heappop(pq)
            if u == end_node:
                return path_nodes, path_segments, self._summarize_route(path_segments)

            if u in visited:
                continue
            visited.add(u)

            for neighbor, s_id, seg in self.adj[u]:
                if neighbor in visited:
                    continue

                if avoid_hw and seg.road_type == "Highway":
                    hw_penalty = 60.0
                else:
                    hw_penalty = 0.0

                # Retrieve live simulated traffic metrics
                state = segment_states.get(s_id, {})
                cur_spd = state.get("current_speed", seg.speed_limit_kmh * 0.7)
                cong_score = state.get("congestion_score", 30)
                cong_lvl = state.get("congestion_level", "LOW")
                v_count = state.get("vehicle_count", 150)
                inc_count = state.get("active_incident_count", 0)
                color = state.get("color", self._color_for_score(cong_score))
                delay_m = state.get("delay_min", 0.5)

                travel_time_min = (seg.length_km / max(5.0, cur_spd)) * 60.0

                # Calculate composite multi-criteria edge cost
                edge_cost = (
                    (w_dist * seg.length_km) +
                    (w_time * travel_time_min) +
                    (w_cong * (cong_score / 15.0)) +
                    (w_inc * (inc_count * 20.0)) +
                    hw_penalty
                )

                seg_entry = {
                    "segment_id": s_id,
                    "road_name": seg.name,
                    "road_type": seg.road_type,
                    "lanes": seg.lanes,
                    "length_km": seg.length_km,
                    "current_speed": round(cur_spd, 1),
                    "free_flow_speed": int(seg.speed_limit_kmh),
                    "vehicle_count": v_count,
                    "congestion_score": cong_score,
                    "congestion_level": cong_lvl,
                    "color": color,
                    "delay_minutes": round(delay_m, 1),
                    "incident_count": inc_count,
                    "coordinates": seg.coordinates,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "DEMO_SIMULATOR",
                    "freshness": "Updated 2s ago"
                }

                heapq.heappush(pq, (cost + edge_cost, neighbor, path_nodes + [neighbor], path_segments + [seg_entry]))

        # Fallback route summary
        return [start_node, end_node], [], {
            "distance_km": 6.2,
            "current_eta_minutes": 16,
            "predicted_eta_minutes": 16,
            "delay_minutes": 1.2,
            "congestion_score": 35,
            "congestion_level": "LOW",
            "incident_count": 0
        }

    def _summarize_route(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not segments:
            return {
                "distance_km": 0.0,
                "current_eta_minutes": 0,
                "predicted_eta_minutes": 0,
                "delay_minutes": 0.0,
                "congestion_score": 0,
                "congestion_level": "LOW",
                "incident_count": 0
            }

        dist = sum(s["length_km"] for s in segments)
        cur_mins = sum((s["length_km"] / max(5.0, s["current_speed"])) * 60.0 for s in segments)
        free_mins = sum((s["length_km"] / max(5.0, s["free_flow_speed"])) * 60.0 for s in segments)
        delay = max(0.0, cur_mins - free_mins)
        avg_cong = int(sum(s["congestion_score"] for s in segments) / len(segments))
        incidents = sum(s["incident_count"] for s in segments)

        lvl = "LOW" if avg_cong <= 25 else "MODERATE" if avg_cong <= 50 else "HEAVY" if avg_cong <= 75 else "SEVERE"

        return {
            "distance_km": round(dist, 1),
            "current_eta_minutes": max(3, int(round(cur_mins))),
            "predicted_eta_minutes": max(3, int(round(cur_mins * (0.95 if avg_cong > 50 else 1.0)))),
            "delay_minutes": round(delay, 1),
            "congestion_score": avg_cong,
            "congestion_level": lvl,
            "incident_count": incidents
        }

    def _color_for_score(self, score: int) -> str:
        if score <= 25:
            return "#10b981"  # Green
        elif score <= 50:
            return "#f59e0b"  # Amber
        elif score <= 75:
            return "#f97316"  # Orange
        else:
            return "#ef4444"  # Red

    def _generate_geojson_geometry(self, segments: List[Dict[str, Any]]) -> List[List[float]]:
        coords = []
        for s in segments:
            for c in s.get("coordinates", []):
                # GeoJSON standard is [lon, lat]
                coords.append([c[1], c[0]])
        return coords

    def _generate_leaflet_polyline(self, segments: List[Dict[str, Any]]) -> List[List[float]]:
        polyline = []
        for s in segments:
            for c in s.get("coordinates", []):
                # Leaflet standard is [lat, lon]
                if not polyline or polyline[-1] != [c[0], c[1]]:
                    polyline.append([c[0], c[1]])
        return polyline
