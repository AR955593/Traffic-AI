import os
import sys

# Ensure root directory and app/src are in sys.path for Vercel Serverless Function
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
app_dir = os.path.join(root_dir, "app")
src_dir = os.path.join(root_dir, "src")

for path in [root_dir, app_dir, src_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Set VERCEL flag before importing app
os.environ["VERCEL"] = "1"

from app.main import app

# Export app instance for Vercel
app = app
