# TrafficAI V5 — Rollout & Deployment Guide

## 1. Prerequisites
- Python 3.10+
- MongoDB 6.0+ instance running and accessible via `MONGODB_URI`
- SQLite database initialized (`traffic.db`)

## 2. Deployment Steps
1. **Pull Repository Code**: Ensure all V5 modules (`src/traffic_intelligence_v5.py`, `src/operator_service.py`, `src/mongo_db.py`, `app/main.py`) are present.
2. **Initialize Database Indexes**: Run `init_mongo_indexes()` on startup to ensure all indexes are created idempotently.
3. **Execute Test Suite Verification**:
   ```bash
   python -m pytest tests/test_unified_auth.py tests/test_operator_v4_intelligence.py tests/test_final_platform_verification.py tests/test_v5_intelligence.py
   ```
4. **Deploy Web Application**: Start FastAPI server with Uvicorn.
5. **Synchronize Android Assets**: Copy updated `frontend/` files into `android-app/app/src/main/assets/`.
