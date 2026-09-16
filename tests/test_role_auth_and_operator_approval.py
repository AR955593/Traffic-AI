"""
Test Suite for 3-Role Authentication, Operator Approval Workflow,
Strong Password Policy (8-16 chars), Disposable Email Blocking,
Country Code & Phone OTP Verification in TrafficAI.
"""
import sys
import os
import pytest
from fastapi.testclient import TestClient

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(project_dir, "src"))
sys.path.append(os.path.join(project_dir, "app"))

from mongo_db import get_mongo_db, init_mongo_indexes
from auth import AuthManager
from main import app

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    init_mongo_indexes()
    yield

def test_password_strength_policy():
    auth = AuthManager()
    
    # 1. Less than 8 characters -> Fail
    with pytest.raises(ValueError) as exc:
        auth.register_user("pwd_short@example.com", "Pass1!", "Short Pwd")
    assert "between 8 and 16" in str(exc.value)

    # 2. Greater than 16 characters -> Fail
    with pytest.raises(ValueError) as exc:
        auth.register_user("pwd_long@example.com", "PasswordSuperLong123!Extra", "Long Pwd")
    assert "between 8 and 16" in str(exc.value)

    # 3. Missing uppercase letter -> Fail
    with pytest.raises(ValueError) as exc:
        auth.register_user("pwd_noupper@example.com", "password123!", "No Upper Pwd")
    assert "uppercase letter" in str(exc.value)

    # 4. Missing lowercase letter -> Fail
    with pytest.raises(ValueError) as exc:
        auth.register_user("pwd_nolower@example.com", "PASSWORD123!", "No Lower Pwd")
    assert "lowercase letter" in str(exc.value)

    # 5. Missing digit -> Fail
    with pytest.raises(ValueError) as exc:
        auth.register_user("pwd_nodigit@example.com", "PasswordSecret!", "No Digit Pwd")
    assert "number" in str(exc.value)

    # 6. Missing special char -> Fail
    with pytest.raises(ValueError) as exc:
        auth.register_user("pwd_nospecial@example.com", "Password123456", "No Special Pwd")
    assert "special character" in str(exc.value)

def test_disposable_email_blocking():
    auth = AuthManager()
    
    disposable_emails = [
        "user123@tempmail.com",
        "hacker@guerrillamail.com",
        "test@10minutemail.com",
        "spam@mailinator.com",
        "fake@yopmail.com"
    ]
    for email in disposable_emails:
        with pytest.raises(ValueError) as exc:
            auth.register_user(email, "StrongPass123!", "Temp Mail User")
        assert "disposable or temporary email" in str(exc.value).lower()

def test_operator_registration_approval_and_login_flow():
    auth = AuthManager()
    op_email = "kanpur_operator_test@traffic.gov"
    op_pass = "OperatorPass1!"
    op_name = "Kanpur Traffic Operator"
    db = get_mongo_db()
    db.users.delete_many({"email_normalized": op_email.lower()})

    # 1. Register as TRAFFIC_OPERATOR
    reg_res = auth.register_user(
        email=op_email,
        password=op_pass,
        name=op_name,
        city="Kanpur, UP",
        role="TRAFFIC_OPERATOR",
        phone="9876543210",
        country_code="+91"
    )
    assert reg_res["status"] == "PENDING_APPROVAL"
    op_user = reg_res["user"]
    assert op_user["role"] == "TRAFFIC_OPERATOR"
    assert op_user["is_active"] is False
    assert op_user["status"] == "PENDING_APPROVAL"
    assert op_user["country_code"] == "+91"
    assert op_user["phone"] == "9876543210"

    # 2. Attempt Login BEFORE Admin Approval -> Must fail
    with pytest.raises(ValueError) as exc:
        auth.login_user(op_email, op_pass)
    assert "pending admin approval" in str(exc.value).lower()

    # 3. HTTP login attempt via FastAPI client -> 403 Forbidden
    login_http = client.post("/api/v1/auth/login", json={"email": op_email, "password": op_pass})
    assert login_http.status_code == 403
    assert "pending Admin approval" in login_http.json()["detail"]

    # 4. List Pending Operators
    pending_list = auth.list_pending_operators()
    assert any(p["id"] == op_user["id"] for p in pending_list)

    # 5. Admin Approves Operator
    appr_res = auth.approve_operator(op_user["id"], admin_user_id="usr_admin")
    assert appr_res["status"] == "success"
    approved_user = appr_res["user"]
    assert approved_user["status"] == "APPROVED"
    assert approved_user["is_active"] is True

    # 6. Login AFTER Admin Approval -> Must succeed
    login_success = auth.login_user(op_email, op_pass)
    assert login_success["user"]["id"] == op_user["id"]
    assert "token" in login_success

    # Cleanup
    auth.delete_account(op_user["id"])

def test_phone_otp_verification():
    auth = AuthManager()
    email = "phone_user_test@example.com"
    pwd = "UserPass123!"
    db = get_mongo_db()
    db.users.delete_many({"email_normalized": email.lower()})

    reg = auth.register_user(email, pwd, "Phone Test User", phone="9988776655", country_code="+91")
    user_id = reg["user"]["id"]

    # 1. Send OTP
    otp_res = auth.send_phone_otp("9988776655", country_code="+91")
    assert otp_res["status"] == "success"
    demo_otp = otp_res["demo_otp"]

    # 2. Verify OTP
    ver_res = auth.verify_phone_otp(user_id, "9988776655", demo_otp)
    assert ver_res["status"] == "success"
    assert ver_res["user"]["phone_verified"] is True

    # Cleanup
    auth.delete_account(user_id)
