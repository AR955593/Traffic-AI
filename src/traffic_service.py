"""
Centralized Traffic Classification & Route Scoring Service.
Ensures uniform traffic thresholds, color mapping, and transparent route recommendation scoring across the application.
"""
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timezone

def classify_traffic(current_speed: Optional[float], free_flow_speed: Optional[float] = 60.0) -> Dict[str, Any]:
    """
    Classifies traffic condition based on current_speed thresholds and speed ratio vs free_flow_speed.
    Exact speed bands:
      0 - 20 km/h   -> SEVERE (RED #ef4444)
      >20 - 40 km/h -> HEAVY (ORANGE #f97316)
      >40 - 70 km/h -> MODERATE (YELLOW #f59e0b)
      >70 km/h       -> LOW / FREE FLOW (GREEN #10b981)
      None / Stale  -> STALE / GRAY (#80928e)
    """
    if current_speed is None:
        return {
            "level": "STALE",
            "score": 0,
            "color": "#80928e",  # Slate / Stale Gray
            "label": "No / Stale Data",
            "speed_ratio": None
        }

    speed = float(current_speed)
    free_flow = float(free_flow_speed) if free_flow_speed and free_flow_speed > 0 else 60.0
    ratio = speed / free_flow

    if speed <= 20.0:
        level = "SEVERE"
        color = "#ef4444"  # Red
        label = "Severe Congestion"
        score = int(min(100, 75 + (20.0 - speed) * 1.25))
    elif speed <= 40.0:
        level = "HEAVY"
        color = "#f97316"  # Orange
        label = "Heavy Traffic"
        score = int(51 + (40.0 - speed) * 1.2)
    elif speed <= 70.0:
        level = "MODERATE"
        color = "#f59e0b"  # Yellow
        label = "Moderate Traffic"
        score = int(26 + (70.0 - speed) * 0.8)
    else:
        level = "LOW"
        color = "#10b981"  # Green
        label = "Free Flow"
        score = int(max(0, min(25, (1.0 - ratio) * 100)))

    return {
        "level": level,
        "score": score,
        "color": color,
        "label": label,
        "speed_ratio": round(ratio, 3)
    }


def calculate_route_speed(segments: List[Dict[str, Any]]) -> Optional[float]:
    """
    Calculates length-weighted average speed across route segments:
    routeSpeed = sum(currentSpeed_i * segmentLength_i) / sum(segmentLength_i)
    """
    if not segments:
        return None

    total_weighted_speed = 0.0
    total_length = 0.0

    for seg in segments:
        speed = seg.get("current_speed")
        coords = seg.get("coordinates", [])
        if speed is not None and len(coords) >= 2:
            # Estimate segment length in arbitrary coordinate distance units
            seg_len = 0.0
            for i in range(len(coords) - 1):
                dlat = coords[i+1][0] - coords[i][0]
                dlon = coords[i+1][1] - coords[i][1]
                seg_len += (dlat**2 + dlon**2)**0.5
            seg_len = max(0.0001, seg_len)
            total_weighted_speed += float(speed) * seg_len
            total_length += seg_len

    if total_length > 0:
        return round(total_weighted_speed / total_length, 1)

    # Fallback to simple average if coordinates were missing
    valid_speeds = [float(s["current_speed"]) for s in segments if s.get("current_speed") is not None]
    if valid_speeds:
        return round(sum(valid_speeds) / len(valid_speeds), 1)

    return None


def calculate_route_congestion(
    route_speed: Optional[float],
    free_flow_speed: float = 60.0,
    delay_minutes: float = 0.0,
    normal_eta_minutes: float = 1.0
) -> Dict[str, Any]:
    """
    Calculates a normalized 0-100 route congestion score from length-weighted speed ratio and traffic delay.
    """
    if route_speed is None:
        return {
            "score": 0,
            "level": "N/A",
            "color": "#80928e"
        }

    speed_ratio = route_speed / max(1.0, free_flow_speed)
    delay_ratio = delay_minutes / max(1.0, normal_eta_minutes)

    # Composite normalized congestion score (0 to 100)
    raw_score = ((1.0 - speed_ratio) * 65.0) + (delay_ratio * 35.0)
    score = int(max(0, min(100, round(raw_score))))

    class_info = classify_traffic(route_speed, free_flow_speed)
    return {
        "score": score,
        "level": class_info["level"],
        "color": class_info["color"]
    }


def score_route_recommendation(
    travel_time_sec: float,
    traffic_delay_sec: float,
    distance_m: float,
    w_time: float = 1.0,
    w_delay: float = 1.5,
    w_dist: float = 0.2
) -> float:
    """
    Calculates a transparent composite recommendation score for a route.
    Lower score = Better route.
    """
    dist_km = distance_m / 1000.0
    time_min = travel_time_sec / 60.0
    delay_min = traffic_delay_sec / 60.0

    score = (time_min * w_time) + (delay_min * w_delay) + (dist_km * w_dist)
    return round(score, 2)

