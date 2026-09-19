# TrafficAI V5 — System Architecture Document

## 1. Executive Summary
TrafficAI V5 is a production-grade Real Traffic Intelligence Platform transforming operational CCTV feeds, municipal sensor telemetry, and third-party traffic data into actionable, predictive, and explainable intelligence for city traffic control centers.

```
REAL DATA SOURCES (TomTom, CCTV Gateway, Edge AI NVR, Weather)
       ↓
DATA QUALITY & NORMALIZATION ENGINE (Freshness & SLA Verification)
       ↓
VEHICLE INTELLIGENCE (Classification: Cars, Bikes, Buses, Trucks, Flow/vpm)
       ↓
ROAD SEGMENT STATE (Speeds, Delays, Free-Flow Baselines, Queues)
       ↓
CORRIDOR STATE (Multi-Segment Aggregation & CCTV Proximity)
       ↓
ANOMALY DETECTION ENGINE V5 (Speed Drop, Queue Growth, Traffic Surge)
       ↓
INCIDENT CORRELATION V5 (Spatial-Temporal Multi-Entity Evidence)
       ↓
TRAFFIC FORECASTING ENGINE (+15m, +30m, +60m Horizons)
       ↓
EXPLAINABLE AI RECOMMENDATION CENTER (WHAT, WHY, EVIDENCE, SIMULATION ONLY)
       ↓
OPERATOR DECISION WORKFLOW (Approve for Simulation / Reject)
       ↓
ACTION / IN SILICO SIMULATION
       ↓
OPERATIONAL OUTCOME MEASUREMENT (Pre vs Post Delta Evaluation)
       ↓
HISTORICAL INTELLIGENCE & TIMELINE REPLAY
```

---

## 2. Truthful-Data Contract
TrafficAI V5 adheres to a strict Zero-Fake-Data policy:
- **No Fabricated Telemetry**: If sensor data is missing or not configured, state is explicitly marked `N/A`, `UNAVAILABLE`, or `NOT_CONFIGURED`.
- **Freshness Enforced**: Any telemetry older than 300 seconds transitions automatically to `STALE`.
- **Truthful Video Handling**: If historical CCTV footage is not archived, it is explicitly marked `VIDEO_NOT_AVAILABLE`.
- **Simulation Transparency**: All signal queue adjustments are labeled `SIMULATION ONLY (In Silico)` unless verified physical controller hardware is linked.
- **Forecasting Guardrails**: If fewer than 2 historical state snapshots exist for a segment, forecasting endpoints return `FORECAST_UNAVAILABLE`.

---

## 3. Core Subsystems

### 3.1 Road Segment & Corridor Engine
- Canonical spatial models mapping individual road segments (e.g., `SEG-MALL-01`, `SEG-VIP-01`) to multi-segment Corridors (`CORR-MALL-RD`, `CORR-VIP-RD`) and municipal Duty Zones (`ZONE-CENTRAL`, `ZONE-CIVIL-LINES`, `ZONE-SOUTH`).
- Real-time aggregation of average speed, free-flow velocity, congestion index, delay seconds, and queue lengths.

### 3.2 Camera-to-Road-to-Corridor Graph
- Haversine geodesic distance calculation accurately mapping physical CCTV camera coordinates to road segments and corridors.

### 3.3 Anomaly Detection Engine V5
- Detects sudden velocity drops ($\ge 30\%$), queue expansion ($\ge 300m$), traffic flow surges ($\ge 120$ vpm), and stale data streams ($> 300s$).
- Supports complete lifecycle states: `DETECTED` $\rightarrow$ `ACKNOWLEDGED` $\rightarrow$ `INVESTIGATING` $\rightarrow$ `RESOLVED` $\rightarrow$ `DISMISSED`.

### 3.4 Multi-Entity Incident Correlation V5
- Evaluates spatial proximity ($\le 800m$) between commuter incident reports, CCTV streams, active anomaly triggers, and weather conditions.
- Preserves correlation vs causality distinction.

### 3.5 Traffic Forecasting Engine (+15, +30, +60 min)
- Multi-horizon predictive extrapolation with model versioning (`traffic_forecast_v1`).

### 3.6 Explainable AI Recommendation Center
- Structured decision support schema containing `WHAT`, `WHY`, `EVIDENCE`, `DATA SOURCES`, `EXPECTED EFFECT`, and `RISKS/LIMITATIONS`.

### 3.7 Outcome Measurement Engine
- Captures empirical `BEFORE` state when an action or simulation is initiated.
- Measures `AFTER` state delta (Speed $\Delta$ km/h, Queue $\Delta$ m) and categorizes empirical outcome as `MEASURED IMPROVEMENT`, `NO MEASURABLE IMPROVEMENT`, or `INSUFFICIENT DATA`.
