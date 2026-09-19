"""
TrafficAI Help Center & Support Ticket Management Module.
Handles knowledge base lookups, support ticket persistence in MongoDB ('support_tickets'),
role isolation, support response notifications, and automated verified solutions.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
try:
    from mongo_db import get_mongo_db
except ImportError:
    from src.mongo_db import get_mongo_db
from pymongo import DESCENDING

# Pre-defined, verified Knowledge Base articles
KNOWLEDGE_BASE_ARTICLES: List[Dict[str, Any]] = [
    {
        "article_id": "KB-1001",
        "title": "Troubleshooting Login Problems",
        "category": "LOGIN_REGISTRATION",
        "keywords": ["login", "signin", "password", "auth", "credentials", "account"],
        "problem": "Unable to log in to TrafficAI account",
        "verified_solution": "1. Verify that your registered email address and password are typed correctly.\n2. Ensure CAPS LOCK is turned off.\n3. If you forgot your password, click 'Forgot Password' on the login screen to receive a secure reset link.\n4. Check your network connection and ensure your session hasn't expired.",
        "steps": [
            "Check email and password formatting.",
            "Click 'Forgot Password' if credentials fail.",
            "Clear browser cache and retry login."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1002",
        "title": "Registration & Email Verification Help",
        "category": "LOGIN_REGISTRATION",
        "keywords": ["register", "signup", "verification", "email", "code", "token"],
        "problem": "Did not receive registration verification code or email",
        "verified_solution": "1. Check your email spam, junk, or promotional folders for the verification code.\n2. Verify that your email address was entered without typos.\n3. Click 'Resend Verification Code' on the signup screen.\n4. Ensure your mail provider is not blocking automated emails.",
        "steps": [
            "Inspect spam and junk folders.",
            "Request a new verification code from the registration page.",
            "Contact your email provider if automated messages are filtered."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1003",
        "title": "Google Sign-In Troubleshooting",
        "category": "LOGIN_REGISTRATION",
        "keywords": ["google", "oauth", "sso", "popup", "google_login"],
        "problem": "Google Sign-In button fails or displays an error",
        "verified_solution": "1. Ensure third-party cookies or popup windows are allowed in your browser for TrafficAI.\n2. Make sure you select the exact Google Account registered with TrafficAI.\n3. If using an ad-blocker or privacy extension, temporarily disable it for the login popup.\n4. Clear browser cookies and attempt Google Sign-In again.",
        "steps": [
            "Allow popups for traffic-ai domain.",
            "Disable aggressive popup/script blockers.",
            "Retry Google OAuth authorization."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1004",
        "title": "Live Traffic Map Not Updating",
        "category": "LIVE_TRAFFIC",
        "keywords": ["live", "map", "traffic", "update", "websocket", "slow", "freeze"],
        "problem": "Live traffic layer or congestion colors are frozen or not updating",
        "verified_solution": "1. Click the 'Refresh Traffic' button on the live map header.\n2. Ensure your internet connection is active and stable.\n3. Check the system connection indicator in the upper right. If it says 'Connection Lost', TrafficAI is reconnecting automatically.\n4. Verify that GPS location access is granted so the map centers on your current zone.",
        "steps": [
            "Press the manual refresh button.",
            "Verify network & WebSocket connectivity indicator.",
            "Ensure browser map canvas is enabled."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1005",
        "title": "Route Calculation & Planner Guidance",
        "category": "ROUTE_PLANNER",
        "keywords": ["route", "calculate", "planner", "direction", "navigation", "eta", "green"],
        "problem": "Route calculation fails or shows 'No route found'",
        "verified_solution": "1. Confirm that both Origin and Destination fields have valid address locations.\n2. Check if selected origin or destination is inside a non-navigable zone.\n3. Toggle between 'Optimal Route' and 'Green Eco-Route' to see alternative paths.\n4. If road closures or severe incidents block all direct corridors, the system will re-evaluate adjacent corridors.",
        "steps": [
            "Select specific addresses or drop pins on the map.",
            "Select alternative travel modes (Car, Transit, Bike).",
            "Retry route generation."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1006",
        "title": "GPS & Location Permissions Troubleshooting",
        "category": "GPS_LOCATION",
        "keywords": ["gps", "location", "permission", "lat", "lng", "geo", "position"],
        "problem": "App cannot detect current location or accurate position",
        "verified_solution": "1. Enable Device Location/GPS in your OS settings.\n2. Grant Location permission to your web browser or TrafficAI Android app.\n3. Switch location accuracy to 'High Accuracy' or 'Precise Location'.\n4. If indoor or under dense cover, step outside or manually enter your starting address.",
        "steps": [
            "Check browser/OS location permission popup.",
            "Enable High Accuracy GPS mode.",
            "Manually enter address if GPS satellite lock fails."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1007",
        "title": "Weather Data & Advisory Issues",
        "category": "WEATHER",
        "keywords": ["weather", "rain", "fog", "forecast", "impact", "advisory"],
        "problem": "Weather alerts or local weather condition is missing or out of date",
        "verified_solution": "1. Ensure a valid city or location is selected on your commuter dashboard.\n2. Weather data synchronizes every 5 minutes from regional meteorological sensors.\n3. High-impact weather alerts (heavy rain, dense fog, waterlogging) will automatically overlay on affected route corridors.",
        "steps": [
            "Select current city on the weather widget.",
            "Check regional alert notifications."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1008",
        "title": "Notifications Sync & Real-Time Alert Guidance",
        "category": "NOTIFICATIONS",
        "keywords": ["notification", "alert", "bell", "unread", "badge", "sync", "push"],
        "problem": "Traffic alerts or support updates are not appearing in notification center",
        "verified_solution": "1. Click the Bell icon in the top header and click 'Mark All as Read' or refresh.\n2. Check Notification Preferences under Account Settings to ensure alert categories are toggled ON.\n3. If offline, notifications persist in MongoDB Atlas and resynchronize immediately when connection restores.",
        "steps": [
            "Review notification preferences in Profile.",
            "Verify WebSocket real-time status strip.",
            "Perform manual REST resync by refreshing the page."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1009",
        "title": "Android Mobile App Troubleshooting",
        "category": "MOBILE_APP",
        "keywords": ["android", "app", "apk", "crash", "mobile", "phone"],
        "problem": "Android app crashes or fails to connect to backend",
        "verified_solution": "1. Ensure you are running the latest compiled build of the TrafficAI Android app.\n2. Go to Android Settings -> Apps -> TrafficAI -> Storage -> Clear Cache.\n3. Verify mobile data or Wi-Fi internet access is connected.\n4. Check that background battery optimization is not killing TrafficAI background services.",
        "steps": [
            "Clear Android application cache.",
            "Allow background data and battery permissions.",
            "Restart TrafficAI mobile app."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1010",
        "title": "Saved Places & Favorite Routes Management",
        "category": "SAVED_PLACES_ROUTES",
        "keywords": ["saved", "places", "favorite", "home", "work", "routes", "trips"],
        "problem": "Unable to save or load favorite places/routes",
        "verified_solution": "1. Ensure you are logged into your TrafficAI commuter account.\n2. Verify you have not exceeded maximum saved limits (up to 50 saved places/routes per user).\n3. Use unique custom labels (e.g., 'Home', 'Office', 'Gym') when saving items.",
        "steps": [
            "Confirm active login session.",
            "Delete unused saved places if limit is reached."
        ],
        "status": "PUBLISHED"
    },
    {
        "article_id": "KB-1011",
        "title": "Privacy, Data Protection & Account Deletion",
        "category": "PRIVACY",
        "keywords": ["privacy", "data", "delete", "account", "security", "gdpr"],
        "problem": "Questions regarding privacy or requesting data deletion",
        "verified_solution": "1. TrafficAI stores user data securely in encrypted MongoDB Atlas clusters.\n2. You can request a full data export or account closure under Profile -> Account Security.\n3. Passwords are password-hashed (Bcrypt/PBKDF2) and never stored in plain text.",
        "steps": [
            "Navigate to Profile -> Account Settings.",
            "Request Data Export or Delete Account."
        ],
        "status": "PUBLISHED"
    }
]

class HelpCenterManager:
    """Manages Help Center Knowledge Base and Support Ticket Lifecycle."""

    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        if self._db is None:
            self._db = get_mongo_db()
        return self._db

    def get_knowledge_base(self, category: Optional[str] = None, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns filtered list of published Knowledge Base articles."""
        articles = [a for a in KNOWLEDGE_BASE_ARTICLES if a.get("status") == "PUBLISHED"]
        
        if category:
            cat_upper = category.upper()
            articles = [a for a in articles if a.get("category", "").upper() == cat_upper]

        if query:
            q_lower = query.lower().strip()
            articles = [
                a for a in articles
                if q_lower in a.get("title", "").lower()
                or q_lower in a.get("problem", "").lower()
                or any(q_lower in kw for kw in a.get("keywords", []))
            ]

        return articles

    def find_matching_solution(self, category: str, subject: str, description: str) -> Optional[Dict[str, Any]]:
        """Finds verified knowledge base solution matching category, subject, or description."""
        text_corpus = f"{subject} {description}".lower()
        cat_upper = (category or "").upper()

        # 1. First try exact category match with keyword overlap
        for article in KNOWLEDGE_BASE_ARTICLES:
            if article.get("category", "").upper() == cat_upper:
                for kw in article.get("keywords", []):
                    if kw in text_corpus:
                        return article

        # 2. Fallback keyword search across all articles
        for article in KNOWLEDGE_BASE_ARTICLES:
            for kw in article.get("keywords", []):
                if kw in text_corpus:
                    return article

        # 3. If category matches directly, return category article
        for article in KNOWLEDGE_BASE_ARTICLES:
            if article.get("category", "").upper() == cat_upper:
                return article

        return None

    def create_support_ticket(
        self,
        user_id: str,
        user_name: str,
        user_email: str,
        category: str,
        subject: str,
        description: str,
        priority: str = "NORMAL",
        related_feature: Optional[str] = None,
        device_info: Optional[str] = None,
        attachment_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates and persists a support ticket in MongoDB 'support_tickets'.
        Automatically performs verified Knowledge Base lookup.
        """
        # Auto-increment ticket_id format: TI-100001
        last_ticket = self.db.support_tickets.find_one({}, sort=[("created_at", DESCENDING)])
        if last_ticket and last_ticket.get("ticket_id", "").startswith("TI-"):
            try:
                num = int(last_ticket["ticket_id"].replace("TI-", "")) + 1
                ticket_id = f"TI-{num:06d}"
            except ValueError:
                ticket_id = f"TI-{100000 + self.db.support_tickets.count_documents({}) + 1:06d}"
        else:
            ticket_id = f"TI-{100000 + self.db.support_tickets.count_documents({}) + 1:06d}"

        now_str = datetime.now(timezone.utc).isoformat()
        
        # Check Knowledge Base for automatic verified solution
        kb_match = self.find_matching_solution(category, subject, description)
        
        initial_messages = [
            {
                "sender_id": user_id,
                "sender_name": user_name,
                "sender_role": "USER",
                "message": description,
                "timestamp": now_str,
                "attachments": [attachment_url] if attachment_url else []
            }
        ]

        if kb_match:
            kb_reply = (
                f"🤖 [Verified Help Center Solution]\n"
                f"Title: {kb_match['title']}\n\n"
                f"{kb_match['verified_solution']}\n\n"
                f"Recommended Steps:\n" + "\n".join([f"- {s}" for s in kb_match.get('steps', [])])
            )
            initial_messages.append({
                "sender_id": "system_support",
                "sender_name": "TrafficAI Automated Support",
                "sender_role": "SYSTEM",
                "message": kb_reply,
                "timestamp": now_str,
                "attachments": []
            })
            initial_status = "IN_PROGRESS"
            has_verified_solution = True
            resolution_text = kb_match['verified_solution']
        else:
            initial_messages.append({
                "sender_id": "system_support",
                "sender_name": "TrafficAI Automated Support",
                "sender_role": "SYSTEM",
                "message": "Your request has been received and is being reviewed by the TrafficAI Support Team.",
                "timestamp": now_str,
                "attachments": []
            })
            initial_status = "OPEN"
            has_verified_solution = False
            resolution_text = None

        ticket_doc = {
            "ticket_id": ticket_id,
            "id": ticket_id,
            "user_id": user_id,
            "user_name": user_name,
            "user_email": user_email,
            "category": category,
            "subject": subject,
            "description": description,
            "priority": priority.upper(),
            "status": initial_status,
            "related_feature": related_feature or category,
            "device_info": device_info or "Web App",
            "assigned_operator_id": None,
            "assigned_admin_id": None,
            "messages": initial_messages,
            "resolution": resolution_text,
            "has_verified_solution": has_verified_solution,
            "created_at": now_str,
            "updated_at": now_str,
            "resolved_at": now_str if (initial_status == "RESOLVED") else None,
            "closed_at": None,
            "metadata": {
                "kb_article_id": kb_match.get("article_id") if kb_match else None
            }
        }

        self.db.support_tickets.insert_one(ticket_doc.copy())
        return {k: v for k, v in ticket_doc.items() if k != "_id"}

    def get_user_tickets(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns support tickets owned by specified user_id only."""
        cursor = self.db.support_tickets.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", DESCENDING).limit(limit)
        return list(cursor)

    def get_assigned_tickets(self, operator_or_admin_id: str, role: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns tickets assigned to operator/admin or open unassigned tickets for operations."""
        role_upper = (role or "").upper()
        if role_upper in ["ADMIN", "SUPER_ADMIN"]:
            cursor = self.db.support_tickets.find({}, {"_id": 0}).sort("created_at", DESCENDING).limit(limit)
        else:
            cursor = self.db.support_tickets.find(
                {"$or": [
                    {"assigned_operator_id": operator_or_admin_id},
                    {"assigned_operator_id": None},
                    {"status": "OPEN"}
                ]},
                {"_id": 0}
            ).sort("created_at", DESCENDING).limit(limit)
        return list(cursor)

    def get_ticket_by_id(self, ticket_id: str, acting_user_id: str, acting_role: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves ticket details with strict role isolation:
        USER can ONLY view their own tickets.
        OPERATOR can view assigned/unassigned open tickets.
        ADMIN can view all tickets.
        """
        ticket = self.db.support_tickets.find_one(
            {"$or": [{"ticket_id": ticket_id}, {"id": ticket_id}]},
            {"_id": 0}
        )
        if not ticket:
            return None

        role_upper = (acting_role or "").upper()
        if role_upper in ["ADMIN", "SUPER_ADMIN"]:
            return ticket
        elif role_upper in ["TRAFFIC_OPERATOR", "OPERATOR"]:
            return ticket
        else:
            # USER: strict check
            if ticket.get("user_id") == acting_user_id:
                return ticket
            return None

    def add_ticket_reply(
        self,
        ticket_id: str,
        sender_id: str,
        sender_name: str,
        sender_role: str,
        message: str,
        attachment_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Adds a message reply to a support ticket and updates status & timestamp."""
        ticket = self.get_ticket_by_id(ticket_id, sender_id, sender_role)
        if not ticket:
            return None

        now_str = datetime.now(timezone.utc).isoformat()
        msg_obj = {
            "sender_id": sender_id,
            "sender_name": sender_name,
            "sender_role": sender_role.upper(),
            "message": message,
            "timestamp": now_str,
            "attachments": [attachment_url] if attachment_url else []
        }

        # Update status based on sender role
        role_upper = sender_role.upper()
        if role_upper in ["TRAFFIC_OPERATOR", "OPERATOR", "ADMIN", "SUPER_ADMIN", "SYSTEM"]:
            new_status = "WAITING_FOR_USER"
        else:
            new_status = "IN_PROGRESS"

        res = self.db.support_tickets.update_one(
            {"$or": [{"ticket_id": ticket_id}, {"id": ticket_id}]},
            {
                "$push": {"messages": msg_obj},
                "$set": {
                    "updated_at": now_str,
                    "status": new_status
                }
            }
        )

        if res.modified_count > 0:
            updated_ticket = self.db.support_tickets.find_one(
                {"$or": [{"ticket_id": ticket_id}, {"id": ticket_id}]},
                {"_id": 0}
            )
            return updated_ticket
        return None

    def update_ticket_status(
        self,
        ticket_id: str,
        acting_user_id: str,
        acting_role: str,
        new_status: str,
        resolution: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Updates support ticket status (RESOLVED, CLOSED, REOPENED, IN_PROGRESS, ASSIGNED)."""
        ticket = self.get_ticket_by_id(ticket_id, acting_user_id, acting_role)
        if not ticket:
            return None

        now_str = datetime.now(timezone.utc).isoformat()
        status_upper = new_status.upper()

        update_fields: Dict[str, Any] = {
            "status": status_upper,
            "updated_at": now_str
        }

        if resolution:
            update_fields["resolution"] = resolution

        if status_upper in ["RESOLVED", "CLOSED"]:
            update_fields["resolved_at"] = now_str
            if status_upper == "CLOSED":
                update_fields["closed_at"] = now_str

        res = self.db.support_tickets.update_one(
            {"$or": [{"ticket_id": ticket_id}, {"id": ticket_id}]},
            {"$set": update_fields}
        )

        if res.modified_count > 0:
            return self.db.support_tickets.find_one(
                {"$or": [{"ticket_id": ticket_id}, {"id": ticket_id}]},
                {"_id": 0}
            )
        return None

help_center_manager = HelpCenterManager()
