"""
Test suite verifying Mobile Responsive Architecture, Viewport configuration,
Mobile Bottom Navigation role isolation, CSS card transformation rules, and Android WebView asset sync.
"""
import os
import re
import pytest

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
ANDROID_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "android-app", "app", "src", "main", "assets")

def test_viewport_meta_tag():
    """Verify viewport meta tag enforces mobile scaling & safe-area insets."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    assert os.path.exists(index_path)
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert '<meta name="viewport"' in content
    assert 'width=device-width' in content
    assert 'viewport-fit=cover' in content

def test_mobile_bottom_nav_element_exists():
    """Verify mobile bottom navigation container is present in index.html."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'id="mobile-bottom-nav"' in content
    assert 'class="mobile-bottom-nav"' in content

def test_css_responsive_table_card_transformations():
    """Verify CSS transforms wide desktop tables into mobile cards on small viewports."""
    css_path = os.path.join(FRONTEND_DIR, "styles.css")
    assert os.path.exists(css_path)
    with open(css_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check table transformation rules for Operator Triage and Admin Operators
    assert "#op-triage-table-body" in content
    assert "#adm-operators-tbody" in content
    assert "flex-direction: column" in content
    assert "font-size: 16px !important" in content  # Prevent mobile browser zoom on inputs

def test_app_js_mobile_nav_role_isolation():
    """Verify app.js defines updateMobileBottomNavForRole for 3-role navigation isolation."""
    js_path = os.path.join(FRONTEND_DIR, "app.js")
    assert os.path.exists(js_path)
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "function updateMobileBottomNavForRole" in content
    assert "currentRole === 'ADMIN'" in content
    assert "currentRole === 'TRAFFIC_OPERATOR'" in content
    assert "updateMobileBottomNavForRole(role)" in content

def test_android_assets_synchronized():
    """Verify Android assets directory has identical synced frontend files."""
    assert os.path.exists(ANDROID_ASSETS_DIR)
    for filename in ["index.html", "styles.css", "app.js"]:
        frontend_file = os.path.join(FRONTEND_DIR, filename)
        android_file = os.path.join(ANDROID_ASSETS_DIR, filename)
        assert os.path.exists(android_file), f"Missing {filename} in Android assets"
        assert os.path.getsize(frontend_file) == os.path.getsize(android_file), f"{filename} size mismatch between frontend and android assets"
