# TrafficAI V5 — Operations Guide

## 1. Daily Operator Workflow
1. **Shift Login**: Authenticate using unified Email + Password or Phone + Password.
2. **Start Shift**: Select Duty Zone (e.g., `ZONE-CENTRAL`) and start shift logging.
3. **Attention Required Hub**: Review active verified incidents, critical speed drops, and unacknowledged anomalies.
4. **Road Segment & Corridor Inspection**: Monitor real-time speed, queue length, and freshness indicators.
5. **AI Recommendation Review**: Inspect explainable recommendations with structured `WHAT` and `WHY` evidence. Approve recommendations for in silico simulation or reject with justification.
6. **Outcome Measurement**: Inspect measured delta changes in the Outcome Measurement Center to verify empirical improvements.
7. **Shift Handover**: Record handover notes and smoothly transfer active operational context to the incoming operator.

---

## 2. Telemetry Ingestion Monitoring
- Verify edge NVR and camera gateways are posting valid payload schemas to `POST /api/v1/operator/vehicle-telemetry`.
- Stale streams (> 300s) trigger automated `ROAD_DATA_STALE` anomalies.
