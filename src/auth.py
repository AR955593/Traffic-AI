"""
Authentication & Role-Based Access Control (RBAC) System.
Roles: ADMIN, TRAFFIC_OPERATOR, ANALYST, VIEWER.
Audit logger records administrative interventions and threshold adjustments.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import uuid

class AuditLogger:
    def __init__(self):
        self.logs: List[Dict[str, Any]] = []
        self._seed_initial_logs()

    def _seed_initial_logs(self):
        self.log_action("SYSTEM_INIT", "System", "TraffiSense Core Engine initialized in DEMO MODE.")
        self.log_action("INCIDENT_DISPATCH", "R. Awasthi (Operator)", "Dispatched emergency units to Mall Road (INC-101).")
        self.log_action("MODEL_HOTSWAP", "Admin", "Active model set to HistGradientBoosting (v1.3-xgb).")

    def log_action(self, action_type: str, actor: str, details: str) -> Dict[str, Any]:
        entry = {
            "log_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "actor": actor,
            "details": details
        }
        self.logs.insert(0, entry)
        if len(self.logs) > 200:
            self.logs = self.logs[:200]
        return entry

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.logs[:limit]


class AuthManager:
    def __init__(self):
        self.audit_logger = AuditLogger()
        self.users = {
            "usr_operator": {
                "id": "usr_operator",
                "name": "R. Awasthi",
                "initials": "RA",
                "email": "rawasthi@kanpur.traffic.gov",
                "role": "TRAFFIC_OPERATOR",
                "role_display": "Traffic Operator",
                "city": "Kanpur, UP",
                "permissions": ["view_operations", "modify_incidents", "change_scenarios", "run_predictions", "plan_routes"]
            },
            "usr_admin": {
                "id": "usr_admin",
                "name": "S. Verma (Chief Admin)",
                "initials": "SV",
                "email": "admin@traffisense.gov",
                "role": "ADMIN",
                "role_display": "System Administrator",
                "city": "Kanpur, UP",
                "permissions": ["all"]
            },
            "usr_analyst": {
                "id": "usr_analyst",
                "name": "P. Sharma",
                "initials": "PS",
                "email": "analyst@traffisense.gov",
                "role": "ANALYST",
                "role_display": "Senior Traffic Analyst",
                "city": "Kanpur, UP",
                "permissions": ["view_analytics", "export_csv", "monitor_models"]
            },
            "usr_viewer": {
                "id": "usr_viewer",
                "name": "Public Commuter",
                "initials": "PC",
                "email": "viewer@city.gov",
                "role": "VIEWER",
                "role_display": "Public Viewer",
                "city": "Kanpur, UP",
                "permissions": ["view_live", "plan_routes"]
            }
        }
        self.current_user = self.users["usr_operator"]  # Default active user matching screenshot

    def get_current_user(self) -> Dict[str, Any]:
        return self.current_user

    def switch_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        if user_id in self.users:
            self.current_user = self.users[user_id]
            self.audit_logger.log_action("USER_SWITCH", self.current_user["name"], f"Session switched to {self.current_user['role_display']}.")
            return self.current_user
        return None

    def list_users(self) -> List[Dict[str, Any]]:
        return list(self.users.values())
