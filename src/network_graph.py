"""
Road Network Graph Definition for Kanpur, UP and Multi-City Metro Networks.
Includes realistic coordinates, nodes, interconnected segments, speed limits, and geometric paths.
"""
from typing import Dict, List, Any, Tuple
import math

class RoadSegment:
    def __init__(
        self,
        segment_id: str,
        name: str,
        road_type: str,
        lanes: int,
        speed_limit_kmh: float,
        start_node: str,
        end_node: str,
        coordinates: List[Tuple[float, float]],
        base_capacity: int = 400
    ):
        self.segment_id = segment_id
        self.name = name
        self.road_type = road_type
        self.lanes = lanes
        self.speed_limit_kmh = speed_limit_kmh
        self.start_node = start_node
        self.end_node = end_node
        self.coordinates = coordinates  # [(lat, lon), ...]
        self.base_capacity = base_capacity
        self.length_km = self._calculate_length()

    def _calculate_length(self) -> float:
        total = 0.0
        for i in range(len(self.coordinates) - 1):
            lat1, lon1 = self.coordinates[i]
            lat2, lon2 = self.coordinates[i + 1]
            total += haversine_distance(lat1, lon1, lat2, lon2)
        return max(0.2, round(total, 2))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "name": self.name,
            "road_type": self.road_type,
            "lanes": self.lanes,
            "speed_limit_kmh": self.speed_limit_kmh,
            "start_node": self.start_node,
            "end_node": self.end_node,
            "length_km": self.length_km,
            "base_capacity": self.base_capacity,
            "coordinates": self.coordinates
        }


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# -------------------------------------------------------------
# KANPUR, UP METROPOLITAN ROAD NETWORK
# Center: 26.4499, 80.3319 (Mall Road / Civil Lines / Parade / GT Road)
# -------------------------------------------------------------
def get_kanpur_network() -> Tuple[Dict[str, Tuple[float, float]], Dict[str, RoadSegment]]:
    nodes = {
        "N01": (26.4780, 80.3120),  # Ganga Barrage North
        "N02": (26.4780, 80.3240),  # Nawabganj Junction
        "N03": (26.4780, 80.3450),  # Azad Nagar Crossing
        "N04": (26.4620, 80.3120),  # Rawatpur West
        "N05": (26.4620, 80.3240),  # IIT Kanpur Metro Link / Swaroop Nagar
        "N06": (26.4620, 80.3450),  # Motijheel / Harsh Nagar
        "N07": (26.4620, 80.3650),  # VIP Road Junction / Civil Lines
        "N08": (26.4420, 80.3120),  # Govind Nagar West
        "N09": (26.4420, 80.3240),  # Shastri Nagar Crossing
        "N10": (26.4420, 80.3450),  # Parade Ground Central
        "N11": (26.4420, 80.3650),  # Phool Bagh / Mall Road East
        "N12": (26.4250, 80.3120),  # Fazalganj Industrial
        "N13": (26.4250, 80.3450),  # Kanpur Central Station South
        "N14": (26.4250, 80.3650),  # Kidwai Nagar Bypass South
        "N15": (26.4520, 80.3780),  # Cantt Railway Overbridge
        "N16": (26.4350, 80.3780),  # Jajmau Ganga Bridge
    }

    segments_def = [
        # Segment ID, Name, Road Type, Lanes, Speed Limit, Start Node, End Node, Intermediate Coords
        ("SEG001", "GT Road North Corridor", "Highway", 6, 80.0, "N01", "N02", [nodes["N01"], nodes["N02"]]),
        ("SEG002", "Ganga Barrage Arterial", "Arterial", 4, 60.0, "N02", "N03", [nodes["N02"], nodes["N03"]]),
        ("SEG003", "Nawabganj Connecting Way", "City_Street", 2, 40.0, "N01", "N04", [nodes["N01"], nodes["N04"]]),
        ("SEG004", "Swaroop Nagar Boulevard", "Arterial", 4, 50.0, "N02", "N05", [nodes["N02"], nodes["N05"]]),
        ("SEG005", "Azad Nagar Ring Link", "Arterial", 4, 50.0, "N03", "N06", [nodes["N03"], nodes["N06"]]),
        ("SEG006", "Rawatpur Metro Corridor", "Arterial", 4, 50.0, "N04", "N05", [nodes["N04"], nodes["N05"]]),
        ("SEG007", "Motijheel Promenade Road", "City_Street", 4, 45.0, "N05", "N06", [nodes["N05"], nodes["N06"]]),
        ("SEG008", "VIP Road Civil Lines", "Highway", 6, 70.0, "N06", "N07", [nodes["N06"], nodes["N07"]]),
        ("SEG009", "Govind Nagar North Arterial", "Arterial", 4, 50.0, "N04", "N08", [nodes["N04"], nodes["N08"]]),
        ("SEG010", "Shastri Nagar Cross Way", "City_Street", 2, 35.0, "N05", "N09", [nodes["N05"], nodes["N09"]]),
        ("SEG011", "Harsh Nagar Express Link", "Arterial", 4, 50.0, "N06", "N10", [nodes["N06"], nodes["N10"]]),
        ("SEG012", "Civil Lines Central Corridor", "Arterial", 4, 50.0, "N07", "N11", [nodes["N07"], nodes["N11"]]),
        ("SEG013", "Govind Nagar Main Street", "City_Street", 2, 35.0, "N08", "N09", [nodes["N08"], nodes["N09"]]),
        ("SEG014", "Mall Road Commercial Corridor", "Arterial", 4, 50.0, "N09", "N10", [nodes["N09"], nodes["N10"]]),
        ("SEG015", "Phool Bagh Promenade", "City_Street", 4, 40.0, "N10", "N11", [nodes["N10"], nodes["N11"]]),
        ("SEG016", "Fazalganj Transit Line", "Arterial", 4, 50.0, "N08", "N12", [nodes["N08"], nodes["N12"]]),
        ("SEG017", "Kanpur Central Station Arterial", "Arterial", 4, 45.0, "N10", "N13", [nodes["N10"], nodes["N13"]]),
        ("SEG018", "Kidwai Nagar Flyover", "Highway", 6, 70.0, "N11", "N14", [nodes["N11"], nodes["N14"]]),
        ("SEG019", "Fazalganj-Central Connector", "City_Street", 2, 35.0, "N12", "N13", [nodes["N12"], nodes["N13"]]),
        ("SEG020", "Southern Express Bypass", "Highway", 6, 80.0, "N13", "N14", [nodes["N13"], nodes["N14"]]),
        ("SEG021", "Cantt Diagonal Bypass", "Arterial", 4, 55.0, "N06", "N15", [nodes["N06"], (26.4570, 80.3620), nodes["N15"]]),
        ("SEG022", "Jajmau Industrial Highway", "Highway", 6, 80.0, "N15", "N16", [nodes["N15"], nodes["N16"]]),
        ("SEG023", "Ganga Barrage East Link", "Arterial", 4, 60.0, "N07", "N15", [nodes["N07"], nodes["N15"]]),
        ("SEG024", "Kidwai-Jajmau Express Spur", "Highway", 4, 65.0, "N14", "N16", [nodes["N14"], nodes["N16"]]),
        ("SEG025", "Parade Diagonal Flyover", "Arterial", 4, 55.0, "N05", "N10", [nodes["N05"], (26.4520, 80.3340), nodes["N10"]]),
        ("SEG026", "Civil Lines Overpass", "Arterial", 4, 50.0, "N03", "N07", [nodes["N03"], (26.4700, 80.3550), nodes["N07"]]),
        ("SEG027", "GT Road South Corridor", "Highway", 6, 75.0, "N09", "N13", [nodes["N09"], (26.4330, 80.3340), nodes["N13"]]),
        ("SEG028", "Phool Bagh - Cantt Connector", "City_Street", 2, 40.0, "N11", "N15", [nodes["N11"], nodes["N15"]]),
        ("SEG029", "Rawatpur-Fazalganj Link", "City_Street", 2, 35.0, "N04", "N12", [nodes["N04"], (26.4430, 80.3120), nodes["N12"]]),
        ("SEG030", "Ganga Riverside Boulevard", "Arterial", 4, 50.0, "N01", "N03", [nodes["N01"], (26.4850, 80.3280), nodes["N03"]]),
        ("SEG031", "Kidwai Nagar Ring Road", "Arterial", 4, 55.0, "N10", "N14", [nodes["N10"], (26.4330, 80.3550), nodes["N14"]]),
        ("SEG032", "Grand Trunk Heritage Way", "City_Street", 2, 35.0, "N07", "N10", [nodes["N07"], (26.4520, 80.3550), nodes["N10"]])
    ]

    segments = {}
    for s_id, name, r_type, lanes, speed, start_n, end_n, coords in segments_def:
        segments[s_id] = RoadSegment(
            segment_id=s_id,
            name=name,
            road_type=r_type,
            lanes=lanes,
            speed_limit_kmh=speed,
            start_node=start_n,
            end_node=end_n,
            coordinates=coords,
            base_capacity=lanes * 120
        )

    return nodes, segments


# Multi-City registry
CITIES = {
    "Kanpur, UP": {
        "center": (26.4499, 80.3319),
        "zoom": 13,
        "region": "UP Region",
        "getter": get_kanpur_network
    }
}
