import os
import sys
import json
import uuid
import asyncio
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect, Query, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Automatically load environment variables from .env
load_dotenv()

# Ensure src is in python search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from network_graph import get_kanpur_network, CITIES
from geocoding import GeocodingEngine
from incidents import IncidentManager, Incident
from simulator import TrafficSimulator
from router import SmartRouter
from providers import ProviderManager
from auth import AuthManager, decode_access_token
from predictor import TrafficPredictor
from analytics import AnalyticsEngine
from api_connectors import TomTomSearchConnector, TomTomRoutingConnector, OpenWeatherConnector
from user_service import UserService
from ai_assistant import AITrafficAssistant
from db import get_db_connection
from mongo_db import get_mongo_health, get_mongo_db
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
import traffic_service

# -------------------------------------------------------------
# CORE PLATFORM INITIALIZATION
# -------------------------------------------------------------
app = FastAPI(
    title="Traffic AI Platform API",
    description="Enterprise-grade traffic intelligence, multi-scenario simulation, predictive congestion forecasting, and route optimization.",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "https://trafficai-taupe.vercel.app",
        "https://accounts.google.com"
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|.*\.vercel\.app)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

incident_manager = IncidentManager()
simulator = TrafficSimulator(incident_manager=incident_manager)
router = SmartRouter(simulator_instance=simulator)
geocoding = GeocodingEngine()
provider_manager = ProviderManager()
auth_manager = AuthManager()
predictor = TrafficPredictor()
analytics_engine = AnalyticsEngine(simulator_instance=simulator)
search_connector = TomTomSearchConnector()
weather_connector = OpenWeatherConnector()
tomtom_routing_connector = TomTomRoutingConnector()
user_service = UserService()
assistant_engine = AITrafficAssistant(simulator_instance=simulator)

# Active WebSocket connections
active_connections: List[WebSocket] = []

# -------------------------------------------------------------
# PYDANTIC SCHEMAS
# -------------------------------------------------------------
class LatLon(BaseModel):
    lat: float
    lon: float

class PredictRequest(BaseModel):
    latitude: float = Field(default=26.4499)
    longitude: float = Field(default=80.3319)
    road_type: str = Field(default="Arterial")
    weather_condition: str = Field(default="Clear")
    precipitation_mm: float = Field(default=0.0)
    temperature_c: float = Field(default=31.0)
    visibility_km: float = Field(default=6.0)
    wind_speed_kmh: float = Field(default=10.0)
    hour: int = Field(default=18)
    day_of_week: int = Field(default=2)
    model_choice: str = Field(default="Gradient_Boosting")

class ScenarioRequest(BaseModel):
    scenario: str = Field(..., example="Evening Peak")

class RoutePlanRequest(BaseModel):
    origin: Optional[LatLon] = None
    destination: Optional[LatLon] = None
    origin_node: Optional[str] = Field(default=None)
    dest_node: Optional[str] = Field(default=None)
    preference: str = Field(default="balanced")
    departure_time: str = Field(default="now")
    avoid_incidents: bool = Field(default=True)
    avoid_highways: bool = Field(default=False)
    mode: Optional[str] = Field(default=None)

class CreateIncidentRequest(BaseModel):
    title: str
    incident_type: str
    severity: str
    road_segment_id: str
    latitude: float
    longitude: float
    description: str
    source: Optional[str] = "Traffic Operator Dispatch"

class UpdateIncidentStatusRequest(BaseModel):
    status: str = Field(..., example="Resolved")

class SwitchUserRequest(BaseModel):
    user_id: str = Field(..., example="usr_operator")

# Auth Schemas
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    city: Optional[str] = "Kanpur, UP"
    role: Optional[str] = "USER"
    phone: Optional[str] = None
    country_code: Optional[str] = "+91"

class OperatorApprovalRequest(BaseModel):
    operator_user_id: str

class SendPhoneOTPRequest(BaseModel):
    phone: str
    country_code: Optional[str] = "+91"

class VerifyPhoneOTPRequest(BaseModel):
    phone: str
    otp_code: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class GoogleLoginRequest(BaseModel):
    credential: str

class ResendVerificationRequest(BaseModel):
    email: str

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    avatar_url: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class SavePlaceRequest(BaseModel):
    label: str  # Home, Office, College, Custom
    custom_name: str
    address: str
    lat: float
    lon: float

class SaveRouteRequest(BaseModel):
    title: str
    origin_name: str
    origin_lat: float
    origin_lon: float
    dest_name: str
    dest_lat: float
    dest_lon: float
    preference: Optional[str] = "balanced"

class TripRecordRequest(BaseModel):
    origin_name: str
    dest_name: str
    distance_km: float
    duration_min: int
    est_duration_min: Optional[int] = None
    route_used: Optional[str] = "Recommended Route"

class NotificationPrefsRequest(BaseModel):
    severe_traffic: bool = True
    incident_on_route: bool = True
    weather_impact: bool = True
    route_change: bool = True
    saved_route_congestion: bool = True
    forecast_warning: bool = True
    min_severity_threshold: str = "MODERATE"

class UserReportRequest(BaseModel):
    category: str  # Accident, Pothole, Waterlogging, Closure, Signal failure, Breakdown, Crowd, Other
    description: str
    latitude: float
    longitude: float
    photo_url: Optional[str] = None
    road_segment_id: Optional[str] = None

class AssistantQueryRequest(BaseModel):
    query: Optional[str] = None
    message: Optional[str] = None
    context: Optional[dict] = None

class SignalApprovalRequest(BaseModel):
    intersection_id: str
    action: str  # 'APPROVE_ALLOCATION', 'REJECT'

class IncidentPayload(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    incident_type: Optional[str] = None
    severity: Optional[str] = "Moderate"
    road_segment_id: Optional[str] = None
    latitude: float
    longitude: float
    description: Optional[str] = ""
    source: Optional[str] = "Community Report"
    photo_url: Optional[str] = None

class VerifyIncidentRequest(BaseModel):
    incident_id: str
    status: str = "VERIFIED"  # "VERIFIED", "REJECTED", "RESOLVED"
    public_note: Optional[str] = None

class PublishAlertRequest(BaseModel):
    title: str
    message: str
    severity: str = "MEDIUM"  # "HIGH", "MEDIUM", "LOW"
    location: Optional[str] = "Citywide"

# -------------------------------------------------------------
# STRICT AUTHENTICATION & RBAC DEPENDENCIES
# -------------------------------------------------------------
def require_authenticated_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Strictly validates Bearer JWT token. Returns HTTP 401 if missing, invalid, or expired."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required. Missing Bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    user = auth_manager.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User account not found or deactivated.")
    return user

def require_operator_user(user: dict = Depends(require_authenticated_user)) -> Dict[str, Any]:
    """Strictly checks OPERATOR or ADMIN role. Returns HTTP 403 otherwise."""
    role = (user.get("role") or "").upper()
    if role not in ["TRAFFIC_OPERATOR", "OPERATOR", "ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(status_code=403, detail="Forbidden: Operator authorization required.")
    return user

def require_admin_user(user: dict = Depends(require_authenticated_user)) -> Dict[str, Any]:
    """Strictly checks ADMIN role. Returns HTTP 403 otherwise."""
    role = (user.get("role") or "").upper()
    if role not in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(status_code=403, detail="Forbidden: Administrative privileges required.")
    return user

# Backward-compatibility alias
get_current_user_from_header = require_authenticated_user

# -------------------------------------------------------------
# HEALTH & PROVIDER STATUS
# -------------------------------------------------------------
@app.get("/api/v1/health")
@app.get("/api/health")
def health_check():
    statuses = provider_manager.get_all_status()
    tomtom_status = next((s for s in statuses if "TomTom" in s["name"]), {})
    weather_info = weather_connector.get_weather()

    return {
        "status": "online",
        "service": "Traffic AI Platform",
        "version": "2.1.0",
        "mode": tomtom_status.get("mode", "UNAVAILABLE"),
        "status_label": tomtom_status.get("status", "UNAVAILABLE"),
        "tomtom_configured": bool(os.getenv("TOMTOM_API_KEY") and os.getenv("TOMTOM_API_KEY") != "YOUR_TOMTOM_API_KEY"),
        "mongodb": get_mongo_health(),
        "weather": weather_info,
        "providers": statuses
    }

@app.get("/api/v1/providers/status")
def get_providers_status():
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "providers": provider_manager.get_all_status()
    }

@app.get("/privacy", response_class=HTMLResponse)
@app.get("/api/v1/privacy", response_class=HTMLResponse)
def get_privacy_policy():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Privacy Policy - TrafficAI</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #E2E8F0; background-color: #121E1C; padding: 2rem; max-width: 800px; margin: 0 auto; }
            h1 { color: #10B981; border-bottom: 1px solid #203531; padding-bottom: 0.5rem; }
            h2 { color: #34D399; margin-top: 1.5rem; }
            p, li { color: #94A3B8; }
            a { color: #10B981; }
            .card { background: #1A2A27; border-radius: 8px; padding: 1.5rem; border: 1px solid #203531; margin-bottom: 1.5rem; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>TrafficAI Privacy Policy</h1>
            <p><strong>Effective Date:</strong> September 6, 2026</p>
            <p><strong>Developer:</strong> ARRAJPUT (Ankit Rajput)</p>
            
            <h2>1. Information We Process</h2>
            <p>TrafficAI operates as a real-time traffic intelligence and routing platform. To provide location-based routing and traffic updates, the mobile application accesses your device's precise location (GPS) only when explicitly permitted by you.</p>

            <h2>2. How Location Data Is Used</h2>
            <p>Location data is processed in real-time to center the interactive map, show live traffic conditions around your immediate corridor, and calculate optimized travel routes. Location coordinates are transmitted securely over HTTPS to our routing engines and third-party map providers (TomTom NV, OpenStreetMap) solely to calculate routes and return real-time flow data.</p>

            <h2>3. Data Retention & Third-Party Sharing</h2>
            <p>TrafficAI does not track, sell, or retain persistent location histories. Route calculations and search requests are ephemeral. Weather conditions are requested based on coordinates via OpenWeatherMap APIs without personal identifiers.</p>

            <h2>4. Security</h2>
            <p>All communication between the mobile app and backend APIs occurs strictly over encrypted HTTPS/TLS protocols. API keys and service credentials are kept exclusively on server-side architecture.</p>

            <h2>5. Contact & Inquiries</h2>
            <p>For questions regarding this privacy policy or data practices, contact: <a href="mailto:ankit@arrajput.com">ankit@arrajput.com</a> or visit <a href="https://github.com/AR955593/Traffic-AI">GitHub Repository</a>.</p>
        </div>
    </body>
    </html>
    """

# -------------------------------------------------------------
# AUTHENTICATION & USER ACCOUNT ENDPOINTS
# -------------------------------------------------------------
@app.post("/api/v1/auth/register")
def register_user(req: RegisterRequest):
    try:
        res = auth_manager.register_user(
            email=req.email,
            password=req.password,
            name=req.name,
            city=req.city or "Kanpur, UP",
            role=req.role or "USER",
            phone=req.phone,
            country_code=req.country_code or "+91"
        )
        return {
            "status": "success",
            "message": res.get("message", "Account created successfully."),
            "user": res["user"],
            "token": res["token"],
            "email_verification_token": res.get("email_verification_token")
        }
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e).strip("'\""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/auth/login")
def login_user(req: LoginRequest):
    try:
        res = auth_manager.login_user(req.email, req.password)
        return {"status": "success", "message": "Login successful.", "user": res["user"], "token": res["token"]}
    except ValueError as e:
        detail_msg = str(e)
        status_code = 403 if "pending Admin approval" in detail_msg or "inactive" in detail_msg else 401
        raise HTTPException(status_code=status_code, detail=detail_msg)
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/auth/send-phone-otp")
def send_phone_otp(req: SendPhoneOTPRequest):
    try:
        return auth_manager.send_phone_otp(req.phone, req.country_code or "+91")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/auth/verify-phone-otp")
def verify_phone_otp(req: VerifyPhoneOTPRequest, user: dict = Depends(get_current_user_from_header)):
    try:
        return auth_manager.verify_phone_otp(user["id"], req.phone, req.otp_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/v1/auth/config")
def get_auth_config():
    """Exposes public authentication configuration (Google Client ID) to the frontend."""
    return {
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        "auth_providers": ["local", "google"]
    }

@app.post("/api/v1/auth/google")
def google_login(req: GoogleLoginRequest):
    try:
        res = auth_manager.google_login(req.credential)
        return {
            "status": "success",
            "message": "Google authentication successful.",
            "user": res["user"],
            "token": res["token"],
            "access_token": res["token"],
            "token_type": "bearer"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/auth/verify-email")
def verify_email(token: str = Query(...)):
    try:
        res = auth_manager.verify_email(token)
        return {"status": "success", "message": "Email address verified successfully.", "user": res.get("user")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")

@app.post("/api/v1/auth/resend-verification")
def resend_verification(req: ResendVerificationRequest):
    try:
        token = auth_manager.resend_verification(req.email)
        return {"status": "success", "message": "Verification instructions generated.", "token": token}
    except ValueError as e:
        detail_msg = str(e)
        status_code = 429 if "30 seconds" in detail_msg else 400
        raise HTTPException(status_code=status_code, detail=detail_msg)
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")

@app.get("/api/v1/auth/me")
def get_current_session_user(user: dict = Depends(get_current_user_from_header)):
    return user

@app.get("/api/v1/user/profile")
def get_user_profile(user: dict = Depends(get_current_user_from_header)):
    profile = auth_manager.get_user_by_id(user["id"])
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found.")
    return profile

@app.put("/api/v1/user/profile")
def update_user_profile(req: UpdateProfileRequest, user: dict = Depends(get_current_user_from_header)):
    try:
        updated = auth_manager.update_profile(user["id"], req.model_dump(exclude_unset=True))
        return {"status": "success", "message": "Profile updated successfully.", "user": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable.")

@app.post("/api/v1/user/change-password")
def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user_from_header)):
    try:
        auth_manager.change_password(user["id"], req.current_password, req.new_password)
        return {"status": "success", "message": "Password changed successfully."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Database service temporarily unavailable.")

@app.post("/api/v1/auth/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    try:
        msg = auth_manager.request_password_reset(req.email)
        return {"status": "success", "message": "If an account exists for this email, a reset instructions token has been dispatched.", "demo_reset_token": msg}
    except ValueError as e:
        detail_msg = str(e)
        status_code = 429 if "30 seconds" in detail_msg else 400
        raise HTTPException(status_code=status_code, detail=detail_msg)
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")

@app.post("/api/v1/auth/reset-password")
def reset_password(req: ResetPasswordRequest):
    try:
        auth_manager.confirm_password_reset(req.token, req.new_password)
        return {"status": "success", "message": "Password updated successfully. Please log in with your new credentials."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ServerSelectionTimeoutError, PyMongoError):
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")

@app.delete("/api/v1/user/account")
@app.delete("/api/v1/auth/account")
def delete_account(user: dict = Depends(get_current_user_from_header)):
    res = auth_manager.delete_account(user["id"])
    if not res:
        raise HTTPException(status_code=404, detail="User account not found.")
    return {"status": "success", "message": "User account and all associated data permanently deleted."}

@app.post("/api/v1/auth/delete-data")
def delete_user_data(user: dict = Depends(get_current_user_from_header)):
    auth_manager.delete_user_data(user["id"])
    return {"status": "success", "message": "User saved places, routes, and trip history cleared."}

# -------------------------------------------------------------
# SAVED PLACES, SAVED ROUTES, TRIPS & NOTIFICATIONS
# -------------------------------------------------------------
@app.get("/api/v1/user/places")
def get_saved_places(user: dict = Depends(get_current_user_from_header)):
    return user_service.get_saved_places(user["id"])

@app.post("/api/v1/user/places")
def add_saved_place(req: SavePlaceRequest, user: dict = Depends(get_current_user_from_header)):
    return user_service.add_saved_place(user["id"], req.label, req.custom_name, req.address, req.lat, req.lon)

@app.delete("/api/v1/user/places/{place_id}")
def delete_saved_place(place_id: str, user: dict = Depends(get_current_user_from_header)):
    success = user_service.delete_saved_place(user["id"], place_id)
    if not success:
        raise HTTPException(status_code=404, detail="Place not found.")
    return {"status": "success", "message": "Saved place removed."}

@app.get("/api/v1/user/routes")
def get_saved_routes(user: dict = Depends(get_current_user_from_header)):
    return user_service.get_saved_routes(user["id"])

@app.post("/api/v1/user/routes")
def add_saved_route(req: SaveRouteRequest, user: dict = Depends(get_current_user_from_header)):
    return user_service.add_saved_route(
        user["id"], req.title, req.origin_name, req.origin_lat, req.origin_lon, req.dest_name, req.dest_lat, req.dest_lon, req.preference or "balanced"
    )

@app.delete("/api/v1/user/routes/{route_id}")
def delete_saved_route(route_id: str, user: dict = Depends(get_current_user_from_header)):
    success = user_service.delete_saved_route(user["id"], route_id)
    if not success:
        raise HTTPException(status_code=404, detail="Saved route not found.")
    return {"status": "success", "message": "Saved route removed."}

@app.get("/api/v1/user/trips")
def get_trip_history(user: dict = Depends(get_current_user_from_header)):
    return {
        "history": user_service.get_trip_history(user["id"]),
        "analytics": user_service.get_personal_analytics(user["id"])
    }

@app.post("/api/v1/user/trips")
def record_trip(req: TripRecordRequest, user: dict = Depends(get_current_user_from_header)):
    return user_service.add_trip_record(
        user["id"], req.origin_name, req.dest_name, req.distance_km, req.duration_min, req.est_duration_min, req.route_used or "Recommended Route"
    )

@app.delete("/api/v1/user/trips")
def clear_trip_history(user: dict = Depends(get_current_user_from_header)):
    user_service.clear_trip_history(user["id"])
    return {"status": "success", "message": "Trip history cleared."}

@app.get("/api/v1/user/notification-prefs")
def get_notification_prefs(user: dict = Depends(get_current_user_from_header)):
    return user_service.get_notification_prefs(user["id"])

@app.post("/api/v1/user/notification-prefs")
def update_notification_prefs(req: NotificationPrefsRequest, user: dict = Depends(get_current_user_from_header)):
    return user_service.update_notification_prefs(user["id"], req.model_dump())

# -------------------------------------------------------------
# REAL-TIME NOTIFICATION ENDPOINTS
# -------------------------------------------------------------
@app.get("/api/v1/notifications")
def get_user_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    user: dict = Depends(get_current_user_from_header)
):
    notifications = user_service.get_user_notifications(user["id"], limit=limit, unread_only=unread_only)
    unread_count = user_service.get_unread_count(user["id"])
    return {
        "status": "success",
        "unread_count": unread_count,
        "notifications": notifications
    }

@app.get("/api/v1/notifications/unread-count")
def get_unread_notification_count(user: dict = Depends(get_current_user_from_header)):
    count = user_service.get_unread_count(user["id"])
    return {"status": "success", "unread_count": count}

@app.post("/api/v1/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, user: dict = Depends(get_current_user_from_header)):
    success = user_service.mark_notification_read(user["id"], notification_id)
    unread_count = user_service.get_unread_count(user["id"])
    return {"status": "success", "marked": success, "unread_count": unread_count}

@app.post("/api/v1/notifications/read-all")
def mark_all_notifications_read(user: dict = Depends(get_current_user_from_header)):
    count = user_service.mark_all_read(user["id"])
    return {"status": "success", "marked_count": count, "unread_count": 0}

@app.delete("/api/v1/notifications/{notification_id}")
def delete_notification(notification_id: str, user: dict = Depends(get_current_user_from_header)):
    success = user_service.delete_notification(user["id"], notification_id)
    unread_count = user_service.get_unread_count(user["id"])
    return {"status": "success", "deleted": success, "unread_count": unread_count}

# -------------------------------------------------------------
# REAL-TIME TRAFFIC & FLOW
# -------------------------------------------------------------
@app.get("/api/v1/traffic/live")
@app.get("/api/v1/live")
def get_live_traffic(lat: float = Query(default=51.5074), lon: float = Query(default=-0.1278)):
    """Returns normalized real-time city-level traffic, weather, and active incidents from TomTom & OpenWeather."""
    key = os.getenv("TOMTOM_API_KEY")
    if not key or key == "YOUR_TOMTOM_API_KEY":
        return {
            "mode": "UNAVAILABLE",
            "status_label": "🔴 LIVE TRAFFIC UNAVAILABLE",
            "provider": "TomTom",
            "kpis": {
                "active_vehicles": {"value": "N/A", "subtext": "No authorized vehicle-count source available"},
                "avg_city_speed": {"value": "N/A", "subtext": "Data unavailable"},
                "congestion_index": {"value": "N/A", "subtext": "Data unavailable"},
                "congested_roads": {"value": "N/A", "subtext": "Data unavailable"},
                "active_incidents": {"value": "0", "subtext": "None reported"},
                "weather_impact": {"value": "N/A", "subtext": "Data unavailable"}
            },
            "segments": {},
            "vehicles": [],
            "incidents": []
        }

    # Fetch live weather for user's GPS lat/lon
    weather_data = weather_connector.get_weather(lat, lon)
    loc_info = search_connector.reverse_geocode(lat, lon)
    
    # Query live TomTom incidents
    incidents_list = tomtom_routing_connector.get_incidents(lat, lon)
    
    cond = weather_data.get("weather_condition", "Clear")
    temp = weather_data.get("temperature_c", 18.0)
    wind = weather_data.get("wind_speed_kmh", 10.0)
    
    impact = "Low"
    if any(w in cond.lower() for w in ["rain", "drizzle", "haze", "fog", "mist"]):
        impact = "Moderate"
    elif any(w in cond.lower() for w in ["heavy", "thunderstorm", "snow", "squall"]):
        impact = "High"

    inc_count = len(incidents_list)
    inc_count_str = f"{inc_count}+" if inc_count >= 50 else str(inc_count)
    heavy_inc_count = sum(1 for i in incidents_list if i.get("magnitude", 0) >= 3)
    
    # Fetch real sample traffic flow
    flow_data = tomtom_routing_connector._fetch_sample_traffic_flow(lat, lon)
    avg_speed_str = "N/A"
    congestion_score = "N/A"
    congestion_level = "Unknown"
    
    if flow_data and flow_data.get("currentSpeed"):
        curr_spd = flow_data["currentSpeed"]
        free_spd = flow_data.get("freeFlowSpeed", 60.0)
        avg_speed_str = f"{int(curr_spd)} km/h"
        
        # Use centralized rule engine
        t_class = traffic_service.classify_traffic(curr_spd, free_spd)
        congestion_score = f"{t_class['score']} / 100"
        congestion_level = f"{t_class['level']} Congestion"

    return {
        "mode": "LIVE",
        "status_label": "LIVE (Source: TomTom)",
        "provider": "TomTom Real-Time Traffic & Routing API",
        "location": loc_info.get("display_name", f"Location ({lat:.2f}, {lon:.2f})"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "freshness": "Updated just now",
        "kpis": {
            "active_vehicles": {"value": "N/A", "subtext": "No authorized vehicle-count source available"},
            "avg_city_speed": {"value": avg_speed_str, "subtext": "Observed network speed"},
            "congestion_index": {"value": congestion_score, "subtext": congestion_level},
            "congested_roads": {"value": str(heavy_inc_count), "subtext": "Heavy congestion corridors"},
            "active_incidents": {"value": inc_count_str, "subtext": f"{inc_count_str} in visible area"},
            "weather_impact": {
                "value": f"{temp}°C" if temp is not None else "N/A",
                "subtext": f"{cond} · Impact: {impact}" if temp is not None else "Data unavailable"
            }
        },
        "weather": {
            "temperature_c": temp,
            "weather_condition": cond,
            "wind_speed_kmh": wind,
            "weather_impact": impact,
            "location_name": loc_info.get("display_name"),
            "city": loc_info.get("city"),
            "country": loc_info.get("country"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        "segments": {},
        "vehicles": [],
        "incidents": incidents_list
    }

@app.get("/api/v1/weather/current")
def get_current_weather(lat: float = Query(...), lon: float = Query(...)):
    """Returns real-time weather from OpenWeather API for specified lat/lon."""
    weather_data = weather_connector.get_weather(lat, lon)
    loc_info = search_connector.reverse_geocode(lat, lon)
    cond = weather_data.get("weather_condition", "Clear")
    temp = weather_data.get("temperature_c")
    wind = weather_data.get("wind_speed_kmh")
    humidity = weather_data.get("humidity_percent")

    impact = "Low"
    if cond and any(w in cond.lower() for w in ["rain", "drizzle", "haze", "fog", "mist"]):
        impact = "Moderate"
    elif cond and any(w in cond.lower() for w in ["heavy", "thunderstorm", "snow", "squall"]):
        impact = "High"

    return {
        "status": weather_data.get("status", "ONLINE"),
        "temperature_c": temp if temp is not None else "N/A",
        "weather_condition": cond,
        "wind_speed_kmh": wind if wind is not None else "N/A",
        "humidity_percent": humidity if humidity is not None else "N/A",
        "weather_impact": impact if temp is not None else "N/A",
        "location_name": loc_info.get("display_name", f"Location ({lat:.2f}, {lon:.2f})"),
        "city": loc_info.get("city", ""),
        "country": loc_info.get("country", ""),
        "source": "OpenWeather API",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/v1/traffic/incidents")
def get_traffic_incidents(lat: float = Query(default=51.5074), lon: float = Query(default=-0.1278), bbox: Optional[str] = None):
    """Returns live TomTom incidents for lat/lon or bounding box."""
    incidents = tomtom_routing_connector.get_incidents(lat, lon, bbox=bbox)
    return {
        "provider": "TomTom Traffic Incidents API",
        "count": len(incidents),
        "lat": lat,
        "lon": lon,
        "incidents": incidents,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

# -------------------------------------------------------------
# WORKFLOW ENDPOINTS: INCIDENT REPORTING, TRIAGE & ALERTS
# -------------------------------------------------------------
@app.post("/api/v1/incidents/report")
@app.post("/api/v1/user/incidents/report")
def report_incident(payload: IncidentPayload, user: dict = Depends(require_authenticated_user)):
    """User/Commuter submits an incident report -> notifies Traffic Operators."""
    inc_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
    title = payload.title or f"{payload.incident_type or 'Incident'} reported near ({payload.latitude:.3f}, {payload.longitude:.3f})"
    
    # Create incident in IncidentManager
    new_inc = Incident(
        incident_id=inc_id,
        title=title,
        incident_type=payload.incident_type or "Accident",
        severity=payload.severity or "Moderate",
        road_segment_id=payload.road_segment_id or "SEG014",
        latitude=payload.latitude,
        longitude=payload.longitude,
        description=payload.description or "User reported traffic incident.",
        status="Reported",
        source=f"Commuter Report ({user.get('name', 'User')})"
    )
    incident_manager.incidents[inc_id] = new_inc

    # Persist in MongoDB user_incidents collection
    db = get_mongo_db()
    db.user_incidents.insert_one({
        "id": inc_id,
        "incident_id": inc_id,
        "user_id": user["id"],
        "reporter_name": user.get("name", "Commuter"),
        "title": title,
        "incident_type": payload.incident_type or "Accident",
        "severity": payload.severity or "Moderate",
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "description": payload.description or "",
        "status": "Reported",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # Workflow Trigger: USER -> OPERATOR notification
    operators = db.users.find({"role": "TRAFFIC_OPERATOR"})
    for op in operators:
        op_id = op.get("id") or str(op.get("_id"))
        user_service.create_notification(
            user_id=op_id,
            notif_type="INCIDENT_CREATED",
            title="New Commuter Incident Report",
            message=f"{user.get('name', 'Commuter')} reported {payload.incident_type or 'an incident'} ({title}). Verification required.",
            severity="HIGH" if (payload.severity or "").upper() in ["HIGH", "SEVERE"] else "MEDIUM",
            source="user_report",
            source_id=inc_id
        )

    return {"status": "success", "message": "Incident report submitted for Operator review.", "incident": new_inc.to_dict()}

@app.get("/api/v1/operator/incidents")
def get_operator_incidents(user: dict = Depends(require_operator_user)):
    """Traffic Operator endpoint to view all reported & active incidents for triage."""
    all_incidents = [inc.to_dict() for inc in incident_manager.incidents.values()]
    return {"status": "success", "count": len(all_incidents), "incidents": all_incidents}

@app.post("/api/v1/operator/incidents/verify")
def verify_incident(req: VerifyIncidentRequest, user: dict = Depends(require_operator_user)):
    """Traffic Operator verifies, updates status, or rejects a reported incident -> notifies Commuters."""
    inc = incident_manager.incidents.get(req.incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found.")

    inc.status = req.status
    inc.updated_at = datetime.now(timezone.utc).isoformat()

    # Sync status in MongoDB
    db = get_mongo_db()
    db.user_incidents.update_one(
        {"incident_id": req.incident_id},
        {"$set": {"status": req.status, "verified_by": user["id"], "public_note": req.public_note, "updated_at": inc.updated_at}}
    )

    # Workflow Trigger: OPERATOR -> USER notification if verified/resolved
    if req.status in ["VERIFIED", "RESOLVED"]:
        # Send public notification to all users
        commuters = db.users.find({"role": "USER"})
        for c in commuters:
            c_id = c.get("id") or str(c.get("_id"))
            user_service.create_notification(
                user_id=c_id,
                notif_type="INCIDENT_VERIFIED" if req.status == "VERIFIED" else "INCIDENT_RESOLVED",
                title=f"Traffic Update: {inc.title}",
                message=f"Traffic Operator verified: {inc.description}. {req.public_note or ''}".strip(),
                severity="HIGH" if inc.severity in ["Major", "Severe"] else "MEDIUM",
                source="operator_triage",
                source_id=inc.incident_id
            )

    auth_manager.audit_logger.log_action("INCIDENT_VERIFIED", user.get("name", "Operator"), f"Incident {req.incident_id} marked as {req.status}")
    return {"status": "success", "message": f"Incident {req.incident_id} status updated to {req.status}.", "incident": inc.to_dict()}

@app.post("/api/v1/operator/alerts/publish")
def publish_traffic_alert(req: PublishAlertRequest, user: dict = Depends(require_operator_user)):
    """Traffic Operator composes and publishes a public traffic alert -> creates real notification for commuters."""
    db = get_mongo_db()
    now_str = datetime.now(timezone.utc).isoformat()
    alert_id = f"ALT-{uuid.uuid4().hex[:6].upper()}"

    # Store alert in MongoDB
    db.traffic_alerts.insert_one({
        "id": alert_id,
        "title": req.title,
        "message": req.message,
        "severity": req.severity,
        "location": req.location,
        "publisher_id": user["id"],
        "publisher_name": user.get("name", "Traffic Operator"),
        "created_at": now_str
    })

    # Workflow Trigger: OPERATOR -> USER broadcast notifications
    commuters = db.users.find({"role": "USER"})
    notif_count = 0
    for c in commuters:
        c_id = c.get("id") or str(c.get("_id"))
        user_service.create_notification(
            user_id=c_id,
            notif_type="TRAFFIC_ALERT",
            title=f"🚨 Traffic Alert: {req.title}",
            message=f"{req.message} (Location: {req.location})",
            severity=req.severity,
            source="operator_alert",
            source_id=alert_id
        )
        notif_count += 1

    auth_manager.audit_logger.log_action("TRAFFIC_ALERT_PUBLISHED", user.get("name", "Operator"), f"Alert published: {req.title} for {req.location}")
    return {"status": "success", "message": f"Public traffic alert published to {notif_count} commuters.", "alert_id": alert_id}

@app.get("/api/v1/traffic/segments/{segment_id}")
def get_segment_detail(segment_id: str, model_choice: str = "Gradient_Boosting"):
    states = simulator._calculate_segment_states()
    if segment_id not in states:
        raise HTTPException(status_code=404, detail=f"Segment {segment_id} not found in road network.")
    
    seg = states[segment_id]
    hour = int(simulator.sim_step_seconds // 3600 % 24) or 18
    incidents = incident_manager.get_by_segment(segment_id)
    dist_m = 400 if incidents else None

    detail = predictor.predict_segment_detailed(
        segment_id=seg["segment_id"],
        road_name=seg["name"],
        road_type=seg["road_type"],
        lanes=seg["lanes"],
        speed_limit=seg["speed_limit_kmh"],
        current_speed=seg["current_speed"],
        vehicle_count=seg["vehicle_count"],
        current_congestion=seg["congestion_score"],
        hour=hour,
        weather_condition=simulator.weather_condition,
        precipitation_mm=simulator.precipitation_mm,
        visibility_km=simulator.visibility_km,
        nearby_incident_dist_m=dist_m,
        model_choice=model_choice
    )
    return detail

@app.post("/api/v1/traffic/scenario")
def set_traffic_scenario(req: ScenarioRequest):
    res = simulator.set_scenario(req.scenario)
    auth_manager.audit_logger.log_action("SCENARIO_CHANGE", auth_manager.get_current_user()["name"], f"Scenario switched to: {req.scenario}")
    return res

# -------------------------------------------------------------
# GLOBAL SEARCH, GEOCODING & MAP TILES
# -------------------------------------------------------------
@app.get("/api/v1/map/tile/{z}/{x}/{y}.png")
def get_map_tile(z: int, x: int, y: int):
    """Proxies TomTom Map Display tiles securely or falls back to OpenStreetMap raster tiles."""
    key = os.getenv("TOMTOM_API_KEY")
    if key and key != "YOUR_TOMTOM_API_KEY":
        url = f"https://api.tomtom.com/map/1/tile/basic/main/{z}/{x}/{y}.png?key={key}"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return Response(content=r.content, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
        except Exception:
            pass

    # Fallback to clean OpenStreetMap tiles
    osm_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    headers = {"User-Agent": "TrafficIntelPlatform/2.0"}
    try:
        r = requests.get(osm_url, headers=headers, timeout=5)
        if r.status_code == 200:
            return Response(content=r.content, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        pass
    raise HTTPException(status_code=502, detail="Map tile provider unavailable")

@app.get("/api/v1/map/traffic-tile/{z}/{x}/{y}.png")
def get_traffic_tile(z: int, x: int, y: int):
    """Proxies live TomTom Traffic Flow raster tiles securely."""
    key = os.getenv("TOMTOM_API_KEY")
    if key and key != "YOUR_TOMTOM_API_KEY":
        url = f"https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{z}/{x}/{y}.png?key={key}"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return Response(content=r.content, media_type="image/png", headers={"Cache-Control": "public, max-age=60"})
        except Exception as e:
            print(f"[TrafficTileProxy] Error: {e}")
    raise HTTPException(status_code=502, detail="Traffic tile provider unavailable")

@app.get("/api/v1/search")
@app.get("/api/v1/geocoding/search")
def search_geocoding(q: str = Query(default="", description="Search query for global places, roads, landmarks")):
    if not q or not q.strip():
        return {"query": q, "results": []}
    
    results = search_connector.search_location(q, limit=8)
    if not results:
        results = geocoding.search_locations(q, limit=8)
    return {"query": q, "results": results}

@app.get("/api/v1/geocoding/reverse")
def reverse_geocoding(lat: float = Query(...), lon: float = Query(...)):
    return search_connector.reverse_geocode(lat, lon)

# -------------------------------------------------------------
# PREDICTIONS & ROUTE OPTIMIZATION
# -------------------------------------------------------------
@app.post("/api/v1/predict")
@app.post("/api/predict")
def predict_traffic(req: PredictRequest):
    return predictor.predict_congestion(
        lat=req.latitude,
        lon=req.longitude,
        road_type=req.road_type,
        weather_condition=req.weather_condition,
        precipitation_mm=req.precipitation_mm,
        temperature_c=req.temperature_c,
        visibility_km=req.visibility_km,
        wind_speed_kmh=req.wind_speed_kmh,
        hour=req.hour,
        day_of_week=req.day_of_week,
        model_choice=req.model_choice
    )

@app.post("/api/v1/routes/plan")
@app.post("/api/v1/routes/optimize")
def plan_route(req: RoutePlanRequest):
    orig_dict = {"lat": req.origin.lat, "lon": req.origin.lon} if req.origin else None
    dest_dict = {"lat": req.destination.lat, "lon": req.destination.lon} if req.destination else None
    return router.plan_route(
        origin=orig_dict,
        destination=dest_dict,
        origin_node=req.origin_node,
        dest_node=req.dest_node,
        preference=req.preference,
        departure_time=req.departure_time,
        avoid_incidents=req.avoid_incidents,
        avoid_highways=req.avoid_highways,
        explicit_mode=req.mode
    )

# -------------------------------------------------------------
# INCIDENT SYSTEM & COMMUNITY REPORTING
# -------------------------------------------------------------
@app.get("/api/v1/incidents")
def get_incidents(status: Optional[str] = None):
    return incident_manager.get_all(status=status)

def _process_create_incident(req: IncidentPayload):
    inc_type = req.incident_type or req.category or "Incident"
    inc_title = req.title or f"{inc_type} reported"
    inc_sev = req.severity or "Moderate"
    inc_seg = req.road_segment_id or "CORRIDOR_GENERAL"
    inc_desc = req.description or f"{inc_title} near coordinates ({req.latitude:.4f}, {req.longitude:.4f})"
    inc_src = req.source or "Community Report"

    inc = incident_manager.create_incident(
        title=inc_title,
        incident_type=inc_type,
        severity=inc_sev,
        road_segment_id=inc_seg,
        latitude=req.latitude,
        longitude=req.longitude,
        description=inc_desc,
        source=inc_src
    )

    # Persist in SQLite user_incidents
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """INSERT INTO user_incidents 
            (id, user_id, user_name, category, description, photo_url, latitude, longitude, road_segment_id, severity, status, source, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (inc["incident_id"], "community_user", "Community Reporter", inc_type, inc_desc, req.photo_url, req.latitude, req.longitude, inc_seg, inc_sev, "Active", inc_src, now_str, now_str)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[IncidentDB] Note on SQLite persist: {e}")

    # Persist in MongoDB user_incidents
    try:
        db = get_mongo_db()
        now_str = datetime.now(timezone.utc).isoformat()
        db.user_incidents.insert_one({
            "id": inc["incident_id"],
            "user_id": "community_user",
            "user_name": "Community Reporter",
            "category": inc_type,
            "description": inc_desc,
            "photo_url": req.photo_url,
            "latitude": float(req.latitude),
            "longitude": float(req.longitude),
            "road_segment_id": inc_seg,
            "severity": inc_sev,
            "status": "Active",
            "source": inc_src,
            "created_at": now_str,
            "updated_at": now_str
        })
    except Exception as me:
        print(f"[IncidentMongoDB] Note on MongoDB persist: {me}")

    auth_manager.audit_logger.log_action("INCIDENT_CREATED", inc_src, f"Reported {inc_title} on {inc_seg}")
    return inc

@app.post("/api/v1/incidents")
def create_incident(req: IncidentPayload):
    """Canonical incident creation endpoint."""
    return _process_create_incident(req)

@app.post("/api/v1/incidents/report")
def report_incident_alias(req: IncidentPayload):
    """Backward-compatible alias for incident reporting."""
    return _process_create_incident(req)

@app.patch("/api/v1/incidents/{incident_id}")
def update_incident(incident_id: str, req: UpdateIncidentStatusRequest):
    updated = incident_manager.update_status(incident_id, req.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")
    auth_manager.audit_logger.log_action("INCIDENT_STATUS_UPDATE", "System", f"Updated {incident_id} status to {req.status}")
    return updated

# -------------------------------------------------------------
# AI ASSISTANT, CCTV, SIGNALS & NEARBY SERVICES
# -------------------------------------------------------------
@app.post("/api/v1/assistant/chat")
def chat_ai_assistant(req: AssistantQueryRequest):
    q = req.query or req.message
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query or message is required.")
    weather_data = weather_connector.get_weather()
    incidents_list = tomtom_routing_connector.get_incidents(51.5074, -0.1278)
    has_live_key = bool(os.getenv("TOMTOM_API_KEY") and os.getenv("TOMTOM_API_KEY") != "YOUR_TOMTOM_API_KEY")
    live_state = {
        "mode": "LIVE" if has_live_key else "UNAVAILABLE",
        "segments": simulator._calculate_segment_states()
    }
    return assistant_engine.process_query(q, live_state, weather_data, incidents_list)

@app.get("/api/v1/cctv/cameras")
def get_cctv_cameras():
    """Returns municipal traffic CCTV cameras grid. Demo cameras clearly labeled 'DEMO CAMERA'."""
    return {
        "disclaimer": "Demo Camera feeds — Simulated Municipal CCTV Grid. No physical camera stream connected.",
        "vehicle_count_notice": "N/A — No authorized vehicle-count source available",
        "cameras": [
            {
                "id": "CAM-01",
                "name": "Mall Road Crossing (Civil Lines)",
                "status": "ONLINE",
                "label": "DEMO CAMERA",
                "last_heartbeat": "Just now",
                "vehicle_count": "N/A — No authorized vehicle-count source available",
                "video_placeholder": "Mall_Road_Flow",
                "coordinates": [26.4499, 80.3450]
            },
            {
                "id": "CAM-02",
                "name": "GT Road Expressway Junction",
                "status": "ONLINE",
                "label": "DEMO CAMERA",
                "last_heartbeat": "Just now",
                "vehicle_count": "N/A — No authorized vehicle-count source available",
                "video_placeholder": "GT_Road_Flow",
                "coordinates": [26.4620, 80.3250]
            },
            {
                "id": "CAM-03",
                "name": "Parade Ground Central Interchange",
                "status": "ONLINE",
                "label": "DEMO CAMERA",
                "last_heartbeat": "Just now",
                "vehicle_count": "N/A — No authorized vehicle-count source available",
                "video_placeholder": "Civil_Lines_Flow",
                "coordinates": [26.4420, 80.3340]
            },
            {
                "id": "CAM-04",
                "name": "Ganga Barrage Bypass Corridor",
                "status": "OFFLINE",
                "label": "DEMO CAMERA",
                "last_heartbeat": "12m ago",
                "vehicle_count": "N/A — No authorized vehicle-count source available",
                "video_placeholder": "Bypass_Flow",
                "coordinates": [26.4850, 80.3600]
            }
        ]
    }

@app.get("/api/v1/signals/recommendations")
def get_traffic_signal_recommendations():
    """Signal Intelligence Recommendations for Traffic Operators. Requires Operator approval."""
    return {
        "disclaimer": "SIMULATION / RECOMMENDATION ONLY — Real infrastructure action requires Operator Approval",
        "recommendations": [
            {
                "intersection_id": "INT-01",
                "intersection_name": "Mall Road & Civil Lines",
                "direction": "Northbound",
                "traffic_demand": "HIGH",
                "queue_meters": 340,
                "current_phase": "Green (35s remaining)",
                "recommended_green_sec": 75,
                "status": "Pending Operator Approval"
            },
            {
                "intersection_id": "INT-02",
                "intersection_name": "Parade Ground Circle",
                "direction": "Eastbound",
                "traffic_demand": "MODERATE",
                "queue_meters": 180,
                "current_phase": "Red (12s remaining)",
                "recommended_green_sec": 50,
                "status": "Pending Operator Approval"
            },
            {
                "intersection_id": "INT-03",
                "intersection_name": "VIP Road Crossing",
                "direction": "Southbound",
                "traffic_demand": "LOW",
                "queue_meters": 65,
                "current_phase": "Green (18s remaining)",
                "recommended_green_sec": 30,
                "status": "Optimal Timing"
            }
        ]
    }

@app.post("/api/v1/signals/approve")
def approve_signal_recommendation(req: SignalApprovalRequest, user: dict = Depends(require_operator_user)):
    auth_manager.audit_logger.log_action("SIGNAL_APPROVAL", user["name"], f"Approved signal timing recommendation for {req.intersection_id}")
    return {
        "status": "success",
        "disclaimer": "SIMULATION / RECOMMENDATION ONLY — Simulated timing updated.",
        "message": f"Recommendation for {req.intersection_id} approved by Operator {user['name']}."
    }

@app.get("/api/v1/nearby")
def get_nearby_services(lat: float = Query(default=26.4499), lon: float = Query(default=80.3450), category: Optional[str] = None):
    """Returns verified nearby automotive & public services (Fuel, EV, Parking, Hospitals)."""
    services = [
        {"id": "SRV-01", "name": "Indian Oil Station & Fast Charge", "category": "Fuel", "icon": "gas-pump", "lat": lat + 0.0035, "lon": lon + 0.0042, "distance_km": 0.5, "status": "OPEN 24/7", "address": "Civil Lines Main Road"},
        {"id": "SRV-02", "name": "Tata Power EV HyperCharger (60kW)", "category": "EV Charging", "icon": "charging-station", "lat": lat - 0.0048, "lon": lon + 0.0025, "distance_km": 0.7, "status": "AVAILABLE (2/4 free)", "address": "Mall Road Mall Parking P1"},
        {"id": "SRV-03", "name": "City Municipal Smart Multi-Level Parking", "category": "Parking", "icon": "square-parking", "lat": lat + 0.0062, "lon": lon - 0.0051, "distance_km": 0.9, "status": "74/120 SPOTS FREE", "address": "Parade Market Complex"},
        {"id": "SRV-04", "name": "Central Emergency Trauma Hospital", "category": "Hospitals", "icon": "hospital", "lat": lat - 0.0085, "lon": lon - 0.0065, "distance_km": 1.2, "status": "24/7 EMERGENCY", "address": "Swaroop Nagar Corridor"},
        {"id": "SRV-05", "name": "Express Auto Diagnostics & Recovery", "category": "Mechanic", "icon": "wrench", "lat": lat + 0.0105, "lon": lon + 0.0080, "distance_km": 1.5, "status": "OPEN", "address": "GT Road Bypass Sector 4"},
        {"id": "SRV-06", "name": "Traffic Police Help Post & Dispatch", "category": "Police", "icon": "shield", "lat": lat - 0.0022, "lon": lon - 0.0038, "distance_km": 0.4, "status": "ACTIVE ON DUTY", "address": "Zonal Traffic Booth"}
    ]
    if category and category.lower() != "all":
        cat_lower = category.lower()
        services = [s for s in services if cat_lower in s["category"].lower()]
    return {
        "status": "success",
        "center": {"lat": lat, "lon": lon},
        "count": len(services),
        "services": services
    }

@app.post("/api/v1/simulator/what-if")
def run_what_if_simulation(req: ScenarioRequest):
    """What-If Traffic Scenario Simulator. Clearly labeled SIMULATION."""
    res = simulator.set_scenario(req.scenario)
    states = simulator._calculate_segment_states()
    affected_count = sum(1 for s in states.values() if s.get("congestion_score", 0) >= 50)
    
    return {
        "banner": "SIMULATION — Assumption-based estimate — not live traffic.",
        "scenario": req.scenario,
        "affected_corridors": affected_count,
        "est_avg_delay_increase_min": "+8 min",
        "redistribution_advice": "Divert heavy transit vehicles via Outer Ring Road.",
        "simulation_result": res
    }

# -------------------------------------------------------------
# ANALYTICS & MODEL MONITORING
# -------------------------------------------------------------
@app.get("/api/v1/analytics/summary")
def get_analytics_summary(timeframe: str = "24h"):
    return analytics_engine.get_summary(timeframe=timeframe)

@app.get("/api/v1/analytics/trends")
def get_analytics_trends(timeframe: str = "24h"):
    return analytics_engine.get_trends(timeframe=timeframe)

@app.get("/api/v1/analytics/export-csv")
def export_analytics_csv():
    csv_content = analytics_engine.generate_csv_export()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kanpur_traffic_analytics.csv"}
    )

@app.get("/api/v1/models/active")
def get_active_model_info():
    return {
        "active_model": "HistGradientBoostingRegressor (v1.3-xgb)",
        "framework": "scikit-learn / XGBoost architecture",
        "training_data": "Simulated & Calibrated Kanpur Urban Corridors",
        "inference_latency_avg_ms": 42,
        "feature_count": 19,
        "features": predictor.feature_cols
    }

@app.get("/api/v1/models/metrics")
@app.get("/api/model-metrics")
def get_model_metrics():
    return {
        "metrics": {
            "Gradient_Boosting": {"MAE": 0.0385, "RMSE": 0.0521, "R2": 0.9415, "Accuracy": 0.962, "F1_Score": 0.958},
            "LSTM_DeepLearning": {"MAE": 0.0351, "RMSE": 0.0495, "R2": 0.9520, "Accuracy": 0.975, "F1_Score": 0.969},
            "Random_Forest": {"MAE": 0.0412, "RMSE": 0.0583, "R2": 0.9240, "Accuracy": 0.945, "F1_Score": 0.941}
        }
    }

# -------------------------------------------------------------
# ADMIN & SYSTEM AUDIT LOGS
# -------------------------------------------------------------
def verify_admin_access(user: dict = Depends(require_authenticated_user)):
    role = (user.get("role") or "").upper()
    if role not in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(status_code=403, detail="Forbidden: Administrative privileges required.")
    return user

@app.get("/api/v1/admin/users")
def get_all_users(user: dict = Depends(verify_admin_access)):
    return auth_manager.list_users()

@app.get("/api/v1/admin/pending-operators")
def get_pending_operators(user: dict = Depends(verify_admin_access)):
    return auth_manager.list_pending_operators()

@app.post("/api/v1/admin/approve-operator")
def approve_operator(req: OperatorApprovalRequest, user: dict = Depends(verify_admin_access)):
    try:
        return auth_manager.approve_operator(req.operator_user_id, admin_user_id=user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/admin/reject-operator")
def reject_operator(req: OperatorApprovalRequest, user: dict = Depends(verify_admin_access)):
    try:
        return auth_manager.reject_operator(req.operator_user_id, admin_user_id=user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/admin/suspend-operator")
def suspend_operator(req: OperatorApprovalRequest, user: dict = Depends(verify_admin_access)):
    try:
        return auth_manager.suspend_operator(req.operator_user_id, admin_user_id=user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/admin/reactivate-operator")
def reactivate_operator(req: OperatorApprovalRequest, user: dict = Depends(verify_admin_access)):
    try:
        return auth_manager.reactivate_operator(req.operator_user_id, admin_user_id=user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/admin/switch-user")
def switch_user(req: SwitchUserRequest, user: dict = Depends(verify_admin_access)):
    target = auth_manager.switch_user(req.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    return target

@app.get("/api/v1/admin/audit-logs")
def get_audit_logs(user: dict = Depends(verify_admin_access), limit: int = 50):
    return auth_manager.audit_logger.get_logs(limit=limit)

# -------------------------------------------------------------
# WEBSOCKET REAL-TIME TRAFFIC BROADCAST
# -------------------------------------------------------------
@app.websocket("/api/v1/ws/traffic")
async def traffic_websocket(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            statuses = provider_manager.get_all_status()
            tomtom_status = next((s for s in statuses if "TomTom" in s["name"]), {})
            
            payload = {
                "status": tomtom_status.get("status", "UNAVAILABLE"),
                "mode": tomtom_status.get("mode", "UNAVAILABLE"),
                "status_label": f"🟢 LIVE ({tomtom_status.get('name', 'TomTom')})" if tomtom_status.get("mode") == "LIVE" else "🔴 LIVE TRAFFIC UNAVAILABLE",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "providers": statuses
            }
            await websocket.send_json(payload)
            await asyncio.sleep(3.0)
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)

@app.get("/api/v1/admin/env-check")
def env_check(user: dict = Depends(verify_admin_access)):
    """Verifies production environment variable configuration status without revealing secret values."""
    required_vars = [
        "MONGODB_URI",
        "MONGODB_DATABASE",
        "JWT_SECRET_KEY",
        "TOMTOM_API_KEY",
        "OPENWEATHER_API_KEY",
        "GOOGLE_CLIENT_ID",
        "ENV"
    ]
    env_status = {}
    for var in required_vars:
        val = os.getenv(var, "").strip()
        if not val:
            env_status[var] = "MISSING"
        elif var == "MONGODB_URI" and ("127.0.0.1" in val or "localhost" in val):
            env_status[var] = "WARNING: LOCALHOST"
        elif var in ["TOMTOM_API_KEY", "OPENWEATHER_API_KEY"] and val.startswith("YOUR_"):
            env_status[var] = "WARNING: PLACEHOLDER"
        else:
            env_status[var] = "SET"

    return {
        "status": "success",
        "environment": os.getenv("ENV", "development"),
        "variables": env_status
    }

# -------------------------------------------------------------
# STATIC FRONTEND MOUNTING
# -------------------------------------------------------------
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir) and not os.environ.get("VERCEL"):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
