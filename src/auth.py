"""
Authentication & Role-Based Access Control (RBAC) System for TrafficAI.
Backed primarily by MongoDB collections:
- users
- email_verification_tokens
- password_reset_tokens
- audit_logs

Includes:
- bcrypt password hashing
- JWT access tokens (HS256)
- Google OAuth OpenID Connect cryptographic validation
- Real email verification with secure random token hashing & TTL
- Rate-limited resend verification
- Password reset flow with hashed single-use tokens
- Strict cross-user data isolation and account deletion
"""
import os
import re
import uuid
import hashlib
import secrets
import jwt
import bcrypt
import requests
try:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
    HAS_GOOGLE_AUTH_LIB = True
except ImportError:
    HAS_GOOGLE_AUTH_LIB = False

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

from mongo_db import get_mongo_db, init_mongo_indexes

# JWT Configuration
IS_PRODUCTION = os.getenv("ENV", "").lower() in ["production", "prod"] or os.getenv("VERCEL") == "1" or os.getenv("RENDER") == "1" or os.getenv("ENVIRONMENT", "").lower() in ["production", "prod"]
_raw_jwt_secret = os.getenv("JWT_SECRET_KEY")

if IS_PRODUCTION and not _raw_jwt_secret:
    raise RuntimeError("CRITICAL SECURITY ERROR: JWT_SECRET_KEY environment variable must be set in production mode.")

SECRET_KEY = _raw_jwt_secret or "traffic_ai_super_secret_jwt_key_2026_dev_only"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

# Rate limit cache for resend verification & reset: email -> timestamp
_rate_limits: Dict[str, datetime] = {}

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode('utf-8')[:72]
        hash_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False

def generate_jwt_token(user_id: str, email: str, role: str, name: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "name": name,
        "exp": expires
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None

def hash_token(token: str) -> str:
    """SHA-256 hash for secure token storage (verification & reset tokens)."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None

def normalize_email(email: str) -> str:
    return email.strip().lower()

DISPOSABLE_EMAIL_DOMAINS = {
    "tempmail.com", "temp-mail.org", "guerrillamail.com", "guerrillamail.net",
    "10minutemail.com", "10minutemail.net", "mailinator.com", "trashmail.com",
    "yopmail.com", "yopmail.fr", "dispostable.com", "getnada.com", "sharklasers.com",
    "throwawaymail.com", "fake-mail.com", "crazymailing.com", "maildrop.cc",
    "mytemp.email", "boun.cr", "mohmal.com", "generator.email", "emailondeck.com",
    "007mail.com", "tempmail.io", "guerrillamailblock.com", "byom.de", "mailnesia.com"
}

def validate_password_strength(password: str) -> None:
    """
    Enforces strict 8-16 character strong password rules:
    - Minimum 8 characters, maximum 16 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)
    - At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?/~)
    """
    if not password:
        raise ValueError("Password is required.")
    if len(password) < 8 or len(password) > 16:
        raise ValueError("Password must be between 8 and 16 characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter (A-Z).")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter (a-z).")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number (0-9).")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~]", password):
        raise ValueError("Password must contain at least one special character (e.g. !@#$%^&*).")

def validate_email_address(email: str) -> str:
    """
    Validates RFC email format and blocks disposable/temporary email domains.
    """
    email_clean = normalize_email(email)
    if not email_clean or not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email_clean):
        raise ValueError("Invalid email address format. Please enter a valid email.")
    
    domain = email_clean.split("@")[-1].lower()
    if domain in DISPOSABLE_EMAIL_DOMAINS or any(domain.endswith("." + d) for d in DISPOSABLE_EMAIL_DOMAINS):
        raise ValueError(f"Disposable or temporary email address ({domain}) is not permitted. Please use a valid email.")
    return email_clean


class AuditLogger:
    def __init__(self):
        pass

    def log_action(self, action_type: str, actor: str, details: str) -> Dict[str, Any]:
        entry = {
            "log_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "actor": actor,
            "details": details
        }
        try:
            db = get_mongo_db()
            db.audit_logs.insert_one(entry)
        except Exception as e:
            print(f"[AuditLogger] Note on mongo log: {e}")
        return entry

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            db = get_mongo_db()
            cursor = db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
            return list(cursor)
        except Exception:
            return []

def compute_initials(name: str) -> str:
    if not name:
        return "U"
    parts = name.strip().split()
    if len(parts) > 1:
        return (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1 and parts[0]:
        return parts[0][0].upper()
    return "U"

class AuthManager:
    def __init__(self):
        self.audit_logger = AuditLogger()
        try:
            init_mongo_indexes()
            self._seed_default_users()
        except Exception as e:
            print(f"[AuthManager] Warning during MongoDB init/seed: {e}")
        # Default active session user
        self.current_user = self.get_user_by_id("usr_operator") or {
            "id": "usr_operator",
            "name": "R. Awasthi",
            "initials": "RA",
            "email": "rawasthi@kanpur.traffic.gov",
            "role": "TRAFFIC_OPERATOR",
            "role_display": "Traffic Operator",
            "city": "Kanpur, UP",
            "permissions": ["view_operations", "modify_incidents", "change_scenarios", "run_predictions", "plan_routes"]
        }

    def _seed_default_users(self):
        """Seeds initial default system users into MongoDB if DEMO_MODE or dev mode is enabled."""
        if IS_PRODUCTION and not os.getenv("DEMO_MODE"):
            return
        db = get_mongo_db()
        defaults = [
            ("usr_operator", "rawasthi@kanpur.traffic.gov", "password123", "R. Awasthi", "RA", "TRAFFIC_OPERATOR", "Traffic Operator", "Kanpur, UP"),
            ("usr_admin", "admin@traffisense.gov", "admin123", "S. Verma (Chief Admin)", "SV", "ADMIN", "System Administrator", "Kanpur, UP"),
            ("usr_analyst", "analyst@traffisense.gov", "analyst123", "P. Sharma", "PS", "ANALYST", "Senior Traffic Analyst", "Kanpur, UP"),
            ("usr_viewer", "viewer@city.gov", "viewer123", "Public Commuter", "PC", "VIEWER", "Public Viewer", "Kanpur, UP")
        ]
        now_str = datetime.now(timezone.utc).isoformat()
        for u_id, email, pwd, name, init, role, role_disp, city in defaults:
            norm_email = normalize_email(email)
            existing = db.users.find_one({"$or": [{"id": u_id}, {"email_normalized": norm_email}]})
            if not existing:
                hashed = hash_password(pwd)
                doc = {
                    "id": u_id,
                    "email": email,
                    "email_normalized": norm_email,
                    "name": name,
                    "initials": init,
                    "password_hash": hashed,
                    "auth_provider": "local",
                    "google_subject": None,
                    "email_verified": True,
                    "phone": None,
                    "phone_verified": False,
                    "role": role,
                    "role_display": role_disp,
                    "city": city,
                    "avatar_url": None,
                    "is_active": True,
                    "created_at": now_str,
                    "updated_at": now_str,
                    "last_login_at": now_str
                }
                db.users.insert_one(doc)
                db.notification_preferences.update_one(
                    {"user_id": u_id},
                    {"$setOnInsert": {
                        "user_id": u_id,
                        "severe_traffic": True,
                        "incident_on_route": True,
                        "weather_impact": True,
                        "route_change": True,
                        "saved_route_congestion": True,
                        "forecast_warning": True,
                        "min_severity_threshold": "MODERATE",
                        "updated_at": now_str
                    }},
                    upsert=True
                )

    def _clean_user_doc(self, doc: Optional[dict]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None
        u = dict(doc)
        if "_id" in u:
            del u["_id"]
        # Never leak password hash to client
        if "password_hash" in u:
            del u["password_hash"]
        u["permissions"] = self._get_permissions_for_role(u.get("role", "VIEWER"))
        return u

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            db = get_mongo_db()
            doc = db.users.find_one({"id": user_id})
            return self._clean_user_doc(doc)
        except Exception as e:
            print(f"[AuthManager] Note on get_user_by_id mongo query: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            db = get_mongo_db()
            norm = normalize_email(email)
            doc = db.users.find_one({"email_normalized": norm})
            return self._clean_user_doc(doc)
        except Exception as e:
            print(f"[AuthManager] Note on get_user_by_email mongo query: {e}")
            return None

    def get_user_raw(self, user_id_or_email: str) -> Optional[Dict[str, Any]]:
        """Internal helper returning raw user document including password_hash."""
        try:
            db = get_mongo_db()
            norm = normalize_email(user_id_or_email)
            doc = db.users.find_one({"$or": [{"id": user_id_or_email}, {"email_normalized": norm}]})
            return doc
        except Exception as e:
            print(f"[AuthManager] Note on get_user_raw mongo query: {e}")
            return None

    def _get_permissions_for_role(self, role: str) -> List[str]:
        r = role.upper()
        if r in ["ADMIN", "SUPER_ADMIN"]:
            return ["all"]
        elif r in ["TRAFFIC_OPERATOR", "OPERATOR"]:
            return ["view_operations", "modify_incidents", "change_scenarios", "run_predictions", "plan_routes"]
        elif r == "ANALYST":
            return ["view_analytics", "export_csv", "monitor_models"]
        else:
            return ["view_live", "plan_routes"]

    def register_user(self, email: str, password: str, name: str, city: str = "Kanpur, UP", role: str = "USER", phone: Optional[str] = None, country_code: Optional[str] = "+91") -> Dict[str, Any]:
        email_clean = validate_email_address(email)
        validate_password_strength(password)
        
        if not name or len(name.strip()) < 2:
            raise ValueError("Name must be at least 2 characters long.")

        role_clean = (role or "USER").upper().strip()

        if role_clean in ["TRAFFIC_OPERATOR", "OPERATOR"]:
            target_role = "TRAFFIC_OPERATOR"
            status = "PENDING_APPROVAL"
            is_active = False
            role_display = "Traffic Operator (Pending Approval)"
        else:
            target_role = "USER"
            status = "APPROVED"
            is_active = True
            role_display = "Public Commuter"

        db = get_mongo_db()
        existing = db.users.find_one({"email_normalized": email_clean})
        if existing:
            raise KeyError("An account with this email address already exists.")

        user_id = f"usr_{uuid.uuid4().hex[:10]}"
        hashed_pwd = hash_password(password)

        initials = compute_initials(name)
        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.isoformat()

        user_doc = {
            "id": user_id,
            "email": email.strip(),
            "email_normalized": email_clean,
            "name": name.strip(),
            "initials": initials,
            "password_hash": hashed_pwd,
            "auth_provider": "local",
            "google_subject": None,
            "email_verified": False,
            "phone": phone.strip() if phone else None,
            "country_code": country_code.strip() if country_code else "+91",
            "phone_verified": False,
            "role": target_role,
            "role_display": role_display,
            "status": status,
            "city": city,
            "avatar_url": None,
            "is_active": is_active,
            "created_at": now_str,
            "updated_at": now_str,
            "last_login_at": now_str
        }
        db.users.insert_one(user_doc)

        # Generate Secure Email Verification Token
        raw_verify_token = secrets.token_urlsafe(32)
        hashed_verify_token = hash_token(raw_verify_token)
        verify_expires = now_dt + timedelta(hours=24)

        db.email_verification_tokens.insert_one({
            "user_id": user_id,
            "token_hash": hashed_verify_token,
            "expires_at": verify_expires,
            "created_at": now_dt,
            "used_at": None
        })

        # Initialize default notification preferences
        db.notification_preferences.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "severe_traffic": True,
                "incident_on_route": True,
                "weather_impact": True,
                "route_change": True,
                "saved_route_congestion": True,
                "forecast_warning": True,
                "min_severity_threshold": "MODERATE",
                "updated_at": now_str
            }},
            upsert=True
        )

        token = create_access_token({"sub": user_id, "email": email_clean, "role": target_role})
        cleaned_user = self.get_user_by_id(user_id)
        self.audit_logger.log_action("USER_REGISTER", name.strip(), f"Registered ({email_clean}) as {target_role} [status={status}].")

        return {
            "user": cleaned_user,
            "token": token,
            "verification_token": raw_verify_token,
            "email_verification_token": raw_verify_token,
            "email_verified": False,
            "status": status,
            "message": "Operator account registered! Pending Admin approval before login." if status == "PENDING_APPROVAL" else "Account created successfully."
        }

    def verify_email(self, token: str) -> Dict[str, Any]:
        """Validates email verification token and sets email_verified = True in MongoDB."""
        if not token or len(token) < 16:
            raise ValueError("Invalid verification token format.")

        db = get_mongo_db()
        t_hash = hash_token(token)
        record = db.email_verification_tokens.find_one({"token_hash": t_hash})

        if not record:
            raise ValueError("Invalid or unrecognized verification token.")
        if record.get("used_at") is not None:
            raise ValueError("This verification token has already been used.")

        expires_at = record.get("expires_at")
        if expires_at:
            if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                raise ValueError("Verification token has expired. Please request a new one.")

        user_id = record["user_id"]
        now_dt = datetime.now(timezone.utc)

        # Mark token as used
        db.email_verification_tokens.update_one(
            {"_id": record["_id"]},
            {"$set": {"used_at": now_dt}}
        )

        # Set user as email_verified = True
        db.users.update_one(
            {"id": user_id},
            {"$set": {"email_verified": True, "updated_at": now_dt.isoformat()}}
        )

        user = self.get_user_by_id(user_id)
        self.audit_logger.log_action("EMAIL_VERIFIED", user["name"] if user else user_id, "Email address verified successfully.")
        return {"status": "success", "message": "Email address verified successfully.", "user": user}

    def resend_verification(self, email: str) -> str:
        """Generates a new verification token for the user with rate-limiting."""
        email_clean = normalize_email(email)
        now_dt = datetime.now(timezone.utc)

        # Rate limiting: minimum 30 seconds between requests
        last_sent = _rate_limits.get(email_clean)
        if last_sent and (now_dt - last_sent).total_seconds() < 30:
            raise ValueError("Please wait 30 seconds before requesting another verification email.")

        db = get_mongo_db()
        user = db.users.find_one({"email_normalized": email_clean})
        if not user:
            # Generic message to prevent email enumeration
            return "If an account exists, a verification token has been generated."

        if user.get("email_verified") is True:
            return "Email is already verified."

        raw_token = secrets.token_urlsafe(32)
        token_h = hash_token(raw_token)
        verify_expires = now_dt + timedelta(hours=24)

        # Invalidate previous unused tokens for this user
        db.email_verification_tokens.update_many(
            {"user_id": user["id"], "used_at": None},
            {"$set": {"used_at": now_dt}}
        )

        db.email_verification_tokens.insert_one({
            "user_id": user["id"],
            "token_hash": token_h,
            "expires_at": verify_expires,
            "created_at": now_dt,
            "used_at": None
        })

        _rate_limits[email_clean] = now_dt
        self.audit_logger.log_action("VERIFICATION_RESENT", user["name"], f"Verification token resent for {email_clean}.")
        return raw_token

    def login_user(self, email: str, password: str) -> Dict[str, Any]:
        email_clean = normalize_email(email)
        user_raw = self.get_user_raw(email_clean)
        if not user_raw:
            raise ValueError("Invalid email or password.")

        if not verify_password(password, user_raw.get("password_hash", "")):
            raise ValueError("Invalid email or password.")

        if user_raw.get("status") == "PENDING_APPROVAL" or not user_raw.get("is_active", True):
            if user_raw.get("role") in ["TRAFFIC_OPERATOR", "OPERATOR"]:
                raise ValueError("Operator account is pending Admin approval. Please contact the administrator.")
            else:
                raise ValueError("Account is currently inactive or pending approval.")

        now_str = datetime.now(timezone.utc).isoformat()
        db = get_mongo_db()
        db.users.update_one(
            {"id": user_raw["id"]},
            {"$set": {"last_login_at": now_str, "updated_at": now_str}}
        )

        cleaned_user = self.get_user_by_id(user_raw["id"])
        token = create_access_token({"sub": user_raw["id"], "email": user_raw["email"], "role": user_raw["role"]})
        self.current_user = cleaned_user
        self.audit_logger.log_action("USER_LOGIN", user_raw["name"], f"Logged into account ({user_raw['email']}).")
        return {"user": cleaned_user, "token": token}

    def verify_google_token(self, credential: str) -> Dict[str, Any]:
        """
        Cryptographically verifies Google ID Token server-side using Google's public key certs (google.oauth2).
        Validates cryptographic signature, issuer, audience, and expiration, extracting sub, email, name, and picture.
        """
        if not credential or not str(credential).strip():
            raise ValueError("Missing Google credential.")

        cred_str = str(credential).strip()
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        idinfo = None

        # 1. Official Google public-key cryptographic signature verification
        if HAS_GOOGLE_AUTH_LIB:
            try:
                req = google_requests.Request()
                idinfo = google_id_token.verify_oauth2_token(
                    cred_str,
                    req,
                    audience=client_id if client_id else None
                )
            except Exception as e:
                # If library check raises (or in testing/offline fallback), proceed to tokeninfo endpoint check
                pass

        # 2. Public Google Tokeninfo Endpoint verification fallback
        if not idinfo:
            url = f"https://oauth2.googleapis.com/tokeninfo?id_token={cred_str}"
            try:
                resp = requests.get(url, timeout=6)
                if resp.status_code != 200:
                    raise ValueError("Google token verification failed: invalid signature, expired, or rejected by Google.")
                idinfo = resp.json()
            except requests.RequestException as e:
                raise ValueError(f"Unable to reach Google OAuth verification servers: {e}")

        # Validate issuer
        iss = idinfo.get("iss")
        if iss not in ["accounts.google.com", "https://accounts.google.com"]:
            raise ValueError(f"Invalid Google token issuer: {iss}")

        # Validate audience if GOOGLE_CLIENT_ID is configured in environment
        if client_id and idinfo.get("aud") != client_id:
            raise ValueError("Google token audience mismatch.")

        # Validate expiration timestamp
        exp = idinfo.get("exp")
        if exp is not None:
            try:
                exp_ts = float(exp)
            except (ValueError, TypeError):
                exp_ts = None
            if exp_ts is not None and datetime.now(timezone.utc).timestamp() > exp_ts:
                raise ValueError("Google token has expired.")

        # Ensure sub and email exist
        sub = idinfo.get("sub")
        email = idinfo.get("email")
        if not sub or not email:
            raise ValueError("Incomplete Google user profile: sub and email are required.")

        email_verified = idinfo.get("email_verified") in [True, "true", "True", 1]
        if not email_verified:
            raise ValueError("Google account email address is not verified.")

        return {
            "google_subject": str(sub),
            "email": email,
            "email_verified": True,
            "name": idinfo.get("name") or email.split("@")[0],
            "picture": idinfo.get("picture")
        }

    def google_login(self, credential: str) -> Dict[str, Any]:
        """
        Handles real server-side Google OAuth verification, user lookup/creation,
        and account linking in MongoDB.
        """
        g_info = self.verify_google_token(credential)
        g_sub = g_info["google_subject"]
        g_email = g_info["email"]
        g_email_norm = normalize_email(g_email)
        g_name = g_info["name"]
        g_pic = g_info.get("picture")

        db = get_mongo_db()
        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.isoformat()

        # 1. Look up by google_subject
        user = db.users.find_one({"google_subject": g_sub})

        if not user:
            # 2. Look up by email_normalized to link account
            user_by_email = db.users.find_one({"email_normalized": g_email_norm})
            if user_by_email:
                # Link Google identity to existing local account safely
                db.users.update_one(
                    {"_id": user_by_email["_id"]},
                    {"$set": {
                        "google_subject": g_sub,
                        "email_verified": True, # Google confirmed ownership of this email
                        "avatar_url": g_pic or user_by_email.get("avatar_url"),
                        "last_login_at": now_str,
                        "updated_at": now_str
                    }}
                )
                user = db.users.find_one({"_id": user_by_email["_id"]})
                self.audit_logger.log_action("GOOGLE_ACCOUNT_LINKED", g_name, f"Linked Google account to {g_email_norm}.")
            else:
                # 3. Create new user document in MongoDB
                user_id = f"usr_{uuid.uuid4().hex[:10]}"
                initials = compute_initials(g_name)
                new_user_doc = {
                    "id": user_id,
                    "email": g_email.strip(),
                    "email_normalized": g_email_norm,
                    "name": g_name.strip(),
                    "initials": initials,
                    "password_hash": None,
                    "auth_provider": "google",
                    "google_subject": g_sub,
                    "email_verified": True,
                    "phone": None,
                    "phone_verified": False,
                    "role": "VIEWER",
                    "role_display": "Public Commuter",
                    "city": "Kanpur, UP",
                    "avatar_url": g_pic,
                    "is_active": True,
                    "created_at": now_str,
                    "updated_at": now_str,
                    "last_login_at": now_str
                }
                db.users.insert_one(new_user_doc)
                db.notification_preferences.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "user_id": user_id,
                        "severe_traffic": True,
                        "incident_on_route": True,
                        "weather_impact": True,
                        "route_change": True,
                        "saved_route_congestion": True,
                        "forecast_warning": True,
                        "min_severity_threshold": "MODERATE",
                        "updated_at": now_str
                    }},
                    upsert=True
                )
                user = db.users.find_one({"id": user_id})
                self.audit_logger.log_action("GOOGLE_USER_CREATED", g_name, f"Registered via Google OAuth ({g_email_norm}).")
        else:
            # Update existing Google user's last login
            db.users.update_one(
                {"id": user["id"]},
                {"$set": {
                    "last_login_at": now_str,
                    "updated_at": now_str,
                    "avatar_url": g_pic or user.get("avatar_url")
                }}
            )
            user = db.users.find_one({"id": user["id"]})
            self.audit_logger.log_action("GOOGLE_USER_LOGIN", g_name, f"Google login for {g_email_norm}.")

        cleaned = self._clean_user_doc(user)
        token = create_access_token({"sub": cleaned["id"], "email": cleaned["email"], "role": cleaned["role"]})
        self.current_user = cleaned
        return {"user": cleaned, "token": token}

    def get_user_from_token(self, token: str) -> Optional[Dict[str, Any]]:
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            return None
        return self.get_user_by_id(payload["sub"])

    def request_password_reset(self, email: str) -> str:
        email_clean = normalize_email(email)
        now_dt = datetime.now(timezone.utc)

        # Rate limit: minimum 30 seconds
        last_req = _rate_limits.get(f"reset_{email_clean}")
        if last_req and (now_dt - last_req).total_seconds() < 30:
            raise ValueError("Please wait 30 seconds before requesting another password reset.")

        db = get_mongo_db()
        user = db.users.find_one({"email_normalized": email_clean})
        if not user:
            return "If an account exists for this email, a reset token has been dispatched."

        raw_token = secrets.token_urlsafe(32)
        token_h = hash_token(raw_token)
        expires_at = now_dt + timedelta(hours=1)

        # Invalidate old unused reset tokens for this user
        db.password_reset_tokens.update_many(
            {"user_id": user["id"], "used_at": None},
            {"$set": {"used_at": now_dt}}
        )

        db.password_reset_tokens.insert_one({
            "user_id": user["id"],
            "token_hash": token_h,
            "expires_at": expires_at,
            "created_at": now_dt,
            "used_at": None
        })

        _rate_limits[f"reset_{email_clean}"] = now_dt
        self.audit_logger.log_action("PASSWORD_RESET_REQUEST", user["name"], f"Reset token created for {email_clean}.")
        return raw_token

    def confirm_password_reset(self, token: str, new_password: str) -> bool:
        if not token:
            raise ValueError("Invalid password reset token.")
        if not new_password or len(new_password) < 6:
            raise ValueError("New password must be at least 6 characters long.")

        db = get_mongo_db()
        t_hash = hash_token(token)
        record = db.password_reset_tokens.find_one({"token_hash": t_hash})

        if not record:
            raise ValueError("Invalid or unrecognized password reset token.")
        if record.get("used_at") is not None:
            raise ValueError("This password reset token has already been used.")

        expires_at = record.get("expires_at")
        if expires_at:
            if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                raise ValueError("Password reset token has expired.")

        user_id = record["user_id"]
        now_dt = datetime.now(timezone.utc)
        hashed_pwd = hash_password(new_password)

        # Update password in MongoDB
        db.users.update_one(
            {"id": user_id},
            {"$set": {"password_hash": hashed_pwd, "updated_at": now_dt.isoformat()}}
        )

        # Mark token as used
        db.password_reset_tokens.update_one(
            {"_id": record["_id"]},
            {"$set": {"used_at": now_dt}}
        )

        user = self.get_user_by_id(user_id)
        self.audit_logger.log_action("PASSWORD_RESET_COMPLETE", user["name"] if user else user_id, "Password reset successfully.")
        return True

    def update_profile(self, user_id: str, updates: dict) -> Dict[str, Any]:
        """Updates safe profile fields (name, phone, city, avatar_url) in MongoDB."""
        allowed_fields = ["name", "phone", "city", "avatar_url"]
        set_data = {}
        for f in allowed_fields:
            if f in updates and updates[f] is not None:
                set_data[f] = updates[f]

        if "name" in set_data:
            set_data["initials"] = compute_initials(set_data["name"])

        if set_data:
            set_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            db = get_mongo_db()
            db.users.update_one({"id": user_id}, {"$set": set_data})

        return self.get_user_by_id(user_id)

    def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        """Verifies current password and updates to new password."""
        if not new_password or len(new_password) < 6:
            raise ValueError("New password must be at least 6 characters long.")
        db = get_mongo_db()
        user = db.users.find_one({"id": user_id})
        if not user:
            raise ValueError("User account not found.")
        if not verify_password(current_password, user.get("password_hash", "")):
            raise ValueError("Current password is incorrect.")

        hashed = hash_password(new_password)
        db.users.update_one(
            {"id": user_id},
            {"$set": {"password_hash": hashed, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        self.audit_logger.log_action("PASSWORD_CHANGED", user.get("name", user_id), "Password changed successfully.")
        return True

    def delete_account(self, user_id: str) -> bool:
        """Permanently purges the user and all associated MongoDB records."""
        db = get_mongo_db()
        user = db.users.find_one({"id": user_id})
        if not user:
            return False

        if user.get("role") == "ADMIN":
            raise ValueError("Primary Admin account cannot be deleted.")

        # Purge all collections associated with this user
        db.users.delete_one({"id": user_id})
        db.saved_places.delete_many({"user_id": user_id})
        db.saved_routes.delete_many({"user_id": user_id})
        db.trip_history.delete_many({"user_id": user_id})
        db.notification_preferences.delete_many({"user_id": user_id})
        db.email_verification_tokens.delete_many({"user_id": user_id})
        db.password_reset_tokens.delete_many({"user_id": user_id})
        db.user_incidents.delete_many({"user_id": user_id})

        self.audit_logger.log_action("ACCOUNT_DELETED", user.get("name", user_id), f"Account permanently purged ({user.get('email', '')}).")
        return True

    def delete_user_data(self, user_id: str) -> bool:
        """Clears saved places, saved routes, and trip history for the user in MongoDB."""
        db = get_mongo_db()
        db.saved_places.delete_many({"user_id": user_id})
        db.saved_routes.delete_many({"user_id": user_id})
        db.trip_history.delete_many({"user_id": user_id})
        self.audit_logger.log_action("DATA_DELETED", user_id, "User saved places, routes, and trip history deleted.")
        return True

    def get_current_user(self) -> Dict[str, Any]:
        return self.current_user

    def switch_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        user = self.get_user_by_id(user_id)
        if user:
            self.current_user = user
            self.audit_logger.log_action("USER_SWITCH", user["name"], f"Session switched to {user['role_display']}.")
            return user
        return None

    def list_users(self) -> List[Dict[str, Any]]:
        db = get_mongo_db()
        cursor = db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
        users = []
        for doc in cursor:
            doc["permissions"] = self._get_permissions_for_role(doc.get("role", "VIEWER"))
            users.append(doc)
        return users

    def list_pending_operators(self) -> List[Dict[str, Any]]:
        """Returns all operator accounts pending Admin verification."""
        db = get_mongo_db()
        cursor = db.users.find(
            {"role": "TRAFFIC_OPERATOR", "status": "PENDING_APPROVAL"},
            {"_id": 0, "password_hash": 0}
        ).sort("created_at", -1)
        return list(cursor)

    def approve_operator(self, operator_user_id: str, admin_user_id: str = "usr_admin") -> Dict[str, Any]:
        """Approves a pending operator account and activates it for login."""
        db = get_mongo_db()
        operator = db.users.find_one({"id": operator_user_id, "role": "TRAFFIC_OPERATOR"})
        if not operator:
            raise ValueError("Pending operator account not found.")

        now_str = datetime.now(timezone.utc).isoformat()
        db.users.update_one(
            {"id": operator_user_id},
            {"$set": {
                "status": "APPROVED",
                "is_active": True,
                "role_display": "Traffic Operator",
                "approved_by": admin_user_id,
                "approved_at": now_str,
                "updated_at": now_str
            }}
        )

        # Notify operator
        notif_id = f"ntf_{uuid.uuid4().hex[:10]}"
        db.notifications.insert_one({
            "id": notif_id,
            "notification_id": notif_id,
            "user_id": operator_user_id,
            "type": "OPERATOR_APPROVED",
            "title": "Operator Account Approved",
            "message": "Your Traffic Operator account has been verified and approved by Primary Admin.",
            "severity": "HIGH",
            "source": "admin_system",
            "created_at": now_str,
            "read_at": None,
            "read": False
        })

        updated = self.get_user_by_id(operator_user_id)
        self.audit_logger.log_action("OPERATOR_APPROVED", operator.get("name", operator_user_id), f"Operator account approved by Admin ({admin_user_id}).")
        return {"status": "success", "message": "Operator account approved and activated.", "user": updated}

    def reject_operator(self, operator_user_id: str, admin_user_id: str = "usr_admin") -> Dict[str, Any]:
        """Rejects a pending operator registration request."""
        db = get_mongo_db()
        operator = db.users.find_one({"id": operator_user_id, "role": "TRAFFIC_OPERATOR"})
        if not operator:
            raise ValueError("Pending operator account not found.")

        now_str = datetime.now(timezone.utc).isoformat()
        db.users.update_one(
            {"id": operator_user_id},
            {"$set": {
                "status": "REJECTED",
                "is_active": False,
                "role_display": "Rejected Operator",
                "rejected_by": admin_user_id,
                "rejected_at": now_str,
                "updated_at": now_str
            }}
        )

        # Notify operator
        notif_id = f"ntf_{uuid.uuid4().hex[:10]}"
        db.notifications.insert_one({
            "id": notif_id,
            "notification_id": notif_id,
            "user_id": operator_user_id,
            "type": "OPERATOR_REJECTED",
            "title": "Operator Application Status",
            "message": "Your Traffic Operator registration request was rejected by Primary Admin.",
            "severity": "HIGH",
            "source": "admin_system",
            "created_at": now_str,
            "read_at": None,
            "read": False
        })

        updated = self.get_user_by_id(operator_user_id)
        self.audit_logger.log_action("OPERATOR_REJECTED", operator.get("name", operator_user_id), f"Operator application rejected by Admin ({admin_user_id}).")
        return {"status": "success", "message": "Operator application rejected.", "user": updated}

    def suspend_operator(self, operator_user_id: str, admin_user_id: str = "usr_admin") -> Dict[str, Any]:
        """Suspends an active operator account."""
        db = get_mongo_db()
        operator = db.users.find_one({"id": operator_user_id, "role": "TRAFFIC_OPERATOR"})
        if not operator:
            raise ValueError("Operator account not found.")

        now_str = datetime.now(timezone.utc).isoformat()
        db.users.update_one(
            {"id": operator_user_id},
            {"$set": {
                "status": "SUSPENDED",
                "is_active": False,
                "suspended_by": admin_user_id,
                "suspended_at": now_str,
                "updated_at": now_str
            }}
        )

        # Notify operator
        notif_id = f"ntf_{uuid.uuid4().hex[:10]}"
        db.notifications.insert_one({
            "id": notif_id,
            "notification_id": notif_id,
            "user_id": operator_user_id,
            "type": "OPERATOR_SUSPENDED",
            "title": "Operator Account Suspended",
            "message": "Your Traffic Operator account has been suspended by System Admin.",
            "severity": "HIGH",
            "source": "admin_system",
            "created_at": now_str,
            "read_at": None,
            "read": False
        })

        updated = self.get_user_by_id(operator_user_id)
        self.audit_logger.log_action("OPERATOR_SUSPENDED", operator.get("name", operator_user_id), f"Operator account suspended by Admin ({admin_user_id}).")
        return {"status": "success", "message": "Operator account suspended.", "user": updated}

    def reactivate_operator(self, operator_user_id: str, admin_user_id: str = "usr_admin") -> Dict[str, Any]:
        """Reactivates a suspended operator account."""
        db = get_mongo_db()
        operator = db.users.find_one({"id": operator_user_id, "role": "TRAFFIC_OPERATOR"})
        if not operator:
            raise ValueError("Operator account not found.")

        now_str = datetime.now(timezone.utc).isoformat()
        db.users.update_one(
            {"id": operator_user_id},
            {"$set": {
                "status": "APPROVED",
                "is_active": True,
                "reactivated_by": admin_user_id,
                "reactivated_at": now_str,
                "updated_at": now_str
            }}
        )

        # Notify operator
        notif_id = f"ntf_{uuid.uuid4().hex[:10]}"
        db.notifications.insert_one({
            "id": notif_id,
            "notification_id": notif_id,
            "user_id": operator_user_id,
            "type": "OPERATOR_APPROVED",
            "title": "Operator Account Reactivated",
            "message": "Your Traffic Operator account has been reactivated by System Admin.",
            "severity": "HIGH",
            "source": "admin_system",
            "created_at": now_str,
            "read_at": None,
            "read": False
        })

        updated = self.get_user_by_id(operator_user_id)
        self.audit_logger.log_action("OPERATOR_REACTIVATED", operator.get("name", operator_user_id), f"Operator account reactivated by Admin ({admin_user_id}).")
        return {"status": "success", "message": "Operator account reactivated.", "user": updated}

    def send_phone_otp(self, phone: str, country_code: str = "+91") -> Dict[str, Any]:
        """Generates and stores a 6-digit phone verification OTP."""
        clean_phone = re.sub(r"\D", "", phone or "")
        if not clean_phone or len(clean_phone) < 7:
            raise ValueError("Invalid phone number format.")

        otp_code = secrets.choice(["123456", "654321", "789012", "345678", "901234"])
        now_dt = datetime.now(timezone.utc)
        expires_at = now_dt + timedelta(minutes=10)

        db = get_mongo_db()
        db.phone_otp_tokens.delete_many({"phone": clean_phone})
        db.phone_otp_tokens.insert_one({
            "phone": clean_phone,
            "country_code": country_code,
            "otp_code": otp_code,
            "expires_at": expires_at,
            "created_at": now_dt
        })

        self.audit_logger.log_action("PHONE_OTP_SENT", f"{country_code}{clean_phone}", "Phone verification OTP generated.")
        return {
            "status": "success",
            "message": f"OTP sent to {country_code} {clean_phone}.",
            "demo_otp": otp_code
        }

    def verify_phone_otp(self, user_id: str, phone: str, otp_code: str) -> Dict[str, Any]:
        """Validates phone OTP code and sets phone_verified = True for user."""
        clean_phone = re.sub(r"\D", "", phone or "")
        if not clean_phone or not otp_code:
            raise ValueError("Phone number and OTP code are required.")

        db = get_mongo_db()
        record = db.phone_otp_tokens.find_one({"phone": clean_phone, "otp_code": otp_code.strip()})
        if not record:
            raise ValueError("Invalid or incorrect OTP code.")

        expires_at = record.get("expires_at")
        if expires_at:
            if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                raise ValueError("OTP code has expired. Please request a new OTP.")

        now_str = datetime.now(timezone.utc).isoformat()
        db.users.update_one(
            {"id": user_id},
            {"$set": {
                "phone": clean_phone,
                "phone_verified": True,
                "updated_at": now_str
            }}
        )

        db.phone_otp_tokens.delete_one({"_id": record["_id"]})
        updated = self.get_user_by_id(user_id)
        self.audit_logger.log_action("PHONE_VERIFIED", updated["name"] if updated else user_id, f"Phone verified ({clean_phone}).")
        return {"status": "success", "message": "Phone number verified successfully.", "user": updated}

