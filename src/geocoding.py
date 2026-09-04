"""
Geocoding, Landmark POI Lookup, and Spatial Snapping Engine.
Provides free, zero-key landmark search and snaps arbitrary GPS coordinates to road network nodes.
"""
from typing import Dict, List, Any, Tuple, Optional
import math
from network_graph import get_kanpur_network, haversine_distance

# Comprehensive Landmark & POI Database for Kanpur, UP
KANPUR_POIS = [
    {
        "id": "poi_jk_temple",
        "name": "JK Temple (Radha Krishna Mandir)",
        "address": "Kamla Nagar, Govind Nagar West, Kanpur",
        "type": "Landmark / Temple",
        "node_id": "N04",
        "lat": 26.4620,
        "lon": 80.3120,
        "coordinates": [26.4620, 80.3120]
    },
    {
        "id": "poi_z_square",
        "name": "Z Square Mall",
        "address": "16/113, The Mall, Phool Bagh, Kanpur",
        "type": "Commercial Mall / Shopping",
        "node_id": "N10",
        "lat": 26.4420,
        "lon": 80.3450,
        "coordinates": [26.4420, 80.3450]
    },
    {
        "id": "poi_central_station",
        "name": "Kanpur Central Railway Station",
        "address": "Station Road, Cantt, Kanpur",
        "type": "Transit / Railway Hub",
        "node_id": "N13",
        "lat": 26.4250,
        "lon": 80.3450,
        "coordinates": [26.4250, 80.3450]
    },
    {
        "id": "poi_motijheel",
        "name": "Motijheel & Municipal Corporation",
        "address": "Harsh Nagar, Benajhabar, Kanpur",
        "type": "Public Park / City Center",
        "node_id": "N06",
        "lat": 26.4620,
        "lon": 80.3450,
        "coordinates": [26.4620, 80.3450]
    },
    {
        "id": "poi_iit_kanpur",
        "name": "IIT Kanpur Metro Station / Swaroop Nagar",
        "address": "Kalyanpur GT Road, Kanpur",
        "type": "Educational / Metro Station",
        "node_id": "N05",
        "lat": 26.4620,
        "lon": 80.3240,
        "coordinates": [26.4620, 80.3240]
    },
    {
        "id": "poi_ganga_barrage",
        "name": "Ganga Barrage (Lav Kush Barrage)",
        "address": "Nawabganj North, Kanpur",
        "type": "Scenic / Riverfront Corridor",
        "node_id": "N01",
        "lat": 26.4780,
        "lon": 80.3120,
        "coordinates": [26.4780, 80.3120]
    },
    {
        "id": "poi_civil_lines",
        "name": "Civil Lines / VIP Road Crossing",
        "address": "Civil Lines District Court, Kanpur",
        "type": "Government / Commercial Arterial",
        "node_id": "N07",
        "lat": 26.4620,
        "lon": 80.3650,
        "coordinates": [26.4620, 80.3650]
    },
    {
        "id": "poi_kidwai_nagar",
        "name": "Kidwai Nagar Bypass Crossing",
        "address": "South Bypass, Kidwai Nagar, Kanpur",
        "type": "Residential / Arterial Hub",
        "node_id": "N14",
        "lat": 26.4250,
        "lon": 80.3650,
        "coordinates": [26.4250, 80.3650]
    },
    {
        "id": "poi_parade_ground",
        "name": "Parade Ground & Naveen Market",
        "address": "Mall Road West, Kanpur",
        "type": "Market / City Center",
        "node_id": "N10",
        "lat": 26.4420,
        "lon": 80.3450,
        "coordinates": [26.4420, 80.3450]
    },
    {
        "id": "poi_fazalganj",
        "name": "Fazalganj Industrial Area",
        "address": "GT Road South, Fazalganj, Kanpur",
        "type": "Industrial / Freight Corridor",
        "node_id": "N12",
        "lat": 26.4250,
        "lon": 80.3120,
        "coordinates": [26.4250, 80.3120]
    },
    {
        "id": "poi_jajmau",
        "name": "Jajmau Ganga Bridge",
        "address": "NH-27 Highway, Jajmau, Kanpur",
        "type": "Expressway / Interstate Bridge",
        "node_id": "N16",
        "lat": 26.4350,
        "lon": 80.3780,
        "coordinates": [26.4350, 80.3780]
    },
    {
        "id": "poi_nawabganj",
        "name": "Nawabganj Bird Sanctuary Link",
        "address": "Nawabganj, Kanpur",
        "type": "Sanctuary / Arterial Link",
        "node_id": "N02",
        "lat": 26.4780,
        "lon": 80.3240,
        "coordinates": [26.4780, 80.3240]
    }
]

class GeocodingEngine:
    def __init__(self):
        self.nodes, self.segments = get_kanpur_network()
        self.pois = KANPUR_POIS

    def search_locations(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """
        Searches POIs and road segments with case-insensitive token matching.
        """
        q = query.lower().strip()
        if not q:
            return self.pois[:limit]

        results = []
        for poi in self.pois:
            score = 0
            if q in poi["name"].lower():
                score += 10
            if q in poi["address"].lower():
                score += 5
            if q in poi["type"].lower():
                score += 3
            
            if score > 0:
                results.append((score, poi))

        # Also search road segments
        for s_id, seg in self.segments.items():
            if q in seg.name.lower() or q in s_id.lower():
                results.append((7, {
                    "id": s_id,
                    "name": seg.name,
                    "address": f"{seg.road_type} · {seg.lanes} lanes ({s_id})",
                    "type": "Road Corridor",
                    "node_id": seg.start_node,
                    "lat": seg.coordinates[0][0],
                    "lon": seg.coordinates[0][1],
                    "coordinates": [seg.coordinates[0][0], seg.coordinates[0][1]]
                }))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def snap_to_nearest_node(self, lat: float, lon: float) -> Tuple[str, Tuple[float, float], float]:
        """
        Finds the closest node in the road network for any GPS coordinate.
        Returns: (node_id, (node_lat, node_lon), distance_km)
        """
        best_node = "N01"
        best_dist = float('inf')
        best_coords = self.nodes["N01"]

        for node_id, coords in self.nodes.items():
            dist = haversine_distance(lat, lon, coords[0], coords[1])
            if dist < best_dist:
                best_dist = dist
                best_node = node_id
                best_coords = coords

        return best_node, best_coords, round(best_dist, 2)
