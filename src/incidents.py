"""
Incident Management System for Traffic Intelligence Platform.
Tracks lifecycle: Reported -> Verified -> Active -> Resolved -> Expired.
Calculates spatial impact on neighboring road segments and feeds into router & simulator.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import uuid

class Incident:
    def __init__(
        self,
        incident_id: str,
        title: str,
        incident_type: str,
        severity: str,
        road_segment_id: str,
        latitude: float,
        longitude: float,
        description: str,
        status: str = "Active",
        source: str = "Traffic Camera AI / Operator",
        impact_radius_km: float = 0.8,
        speed_reduction_pct: float = 40.0,
        expected_duration_min: int = 45
    ):
        self.incident_id = incident_id
        self.title = title
        self.incident_type = incident_type  # Accident, Road Closure, Construction, Flooding, Event, Vehicle Breakdown
        self.severity = severity            # Minor, Moderate, Major, Severe
        self.road_segment_id = road_segment_id
        self.latitude = latitude
        self.longitude = longitude
        self.description = description
        self.status = status                # Reported, Verified, Active, Resolved, Expired
        self.source = source
        self.impact_radius_km = impact_radius_km
        self.speed_reduction_pct = speed_reduction_pct
        self.expected_duration_min = expected_duration_min
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "incident_type": self.incident_type,
            "severity": self.severity,
            "road_segment_id": self.road_segment_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "description": self.description,
            "status": self.status,
            "source": self.source,
            "impact_radius_km": self.impact_radius_km,
            "speed_reduction_pct": self.speed_reduction_pct,
            "expected_duration_min": self.expected_duration_min,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class IncidentManager:
    def __init__(self):
        self.incidents: Dict[str, Incident] = {}
        self._seed_default_incidents()

    def _seed_default_incidents(self):
        """Initializes realistic active incidents matching the screenshot (2 active, 1 severe)."""
        inc1 = Incident(
            incident_id="INC-101",
            title="Multi-Vehicle Collision on Mall Road",
            incident_type="Accident",
            severity="Severe",
            road_segment_id="SEG014",
            latitude=26.4420,
            longitude=80.3340,
            description="Two private buses collided near Parade Crossing blocking 2 lanes. Police and ambulance on scene.",
            status="Active",
            source="CCTV AI Vision & 112 Dispatch",
            impact_radius_km=1.2,
            speed_reduction_pct=65.0,
            expected_duration_min=60
        )
        inc2 = Incident(
            incident_id="INC-102",
            title="Road Surface Maintenance & Metro Work",
            incident_type="Construction",
            severity="Moderate",
            road_segment_id="SEG008",
            latitude=26.4620,
            longitude=80.3550,
            description="Kanpur Metro pier barricading and lane narrowing along VIP Road.",
            status="Active",
            source="UP Metro Rail Corp (UPMRC)",
            impact_radius_km=0.6,
            speed_reduction_pct=30.0,
            expected_duration_min=180
        )
        self.incidents[inc1.incident_id] = inc1
        self.incidents[inc2.incident_id] = inc2

    def get_all(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        results = list(self.incidents.values())
        if status:
            results = [inc for inc in results if inc.status.lower() == status.lower()]
        return [inc.to_dict() for inc in results]

    def get_by_id(self, incident_id: str) -> Optional[Dict[str, Any]]:
        inc = self.incidents.get(incident_id)
        return inc.to_dict() if inc else None

    def get_by_segment(self, segment_id: str) -> List[Incident]:
        return [
            inc for inc in self.incidents.values()
            if inc.road_segment_id == segment_id and inc.status in ["Active", "Verified"]
        ]

    def create_incident(
        self,
        title: str,
        incident_type: str,
        severity: str,
        road_segment_id: str,
        latitude: float,
        longitude: float,
        description: str,
        source: str = "Operator Dispatch",
        status: str = "Active"
    ) -> Dict[str, Any]:
        inc_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        reduction = 70.0 if severity == "Severe" else 45.0 if severity == "Major" else 25.0
        inc = Incident(
            incident_id=inc_id,
            title=title,
            incident_type=incident_type,
            severity=severity,
            road_segment_id=road_segment_id,
            latitude=latitude,
            longitude=longitude,
            description=description,
            status=status,
            source=source,
            speed_reduction_pct=reduction
        )
        self.incidents[inc_id] = inc
        return inc.to_dict()

    def update_status(self, incident_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        if incident_id in self.incidents:
            self.incidents[incident_id].status = new_status
            self.incidents[incident_id].updated_at = datetime.now(timezone.utc).isoformat()
            return self.incidents[incident_id].to_dict()
        return None
