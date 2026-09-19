# TrafficAI V5 — REST API Specification

## Authentication & Authorization
All V5 Operator endpoints require a valid Bearer JWT token with `OPERATOR`, `TRAFFIC_OPERATOR`, `ADMIN`, or `SUPER_ADMIN` role.
Standard `USER` accounts receive `HTTP 403 Forbidden`.
`ADMIN` role accounts attempting access from mobile/Android User-Agents receive `HTTP 403 Forbidden` (`ADMIN_WEB_ONLY`).

---

## Endpoints

### 1. Road Segments
- **`GET /api/v1/operator/road-segments`**
  - Query Params: `zone_id` (optional), `corridor_id` (optional)
  - Returns canonical segments with live traffic states, speed, free-flow baseline, queue, and freshness status.
- **`GET /api/v1/operator/road-segments/{segment_id}`**
  - Returns detailed segment intelligence including mapped cameras, anomalies, and active forecasts.
- **`POST /api/v1/operator/road-segments/{segment_id}/state`**
  - Records real-time traffic snapshot (`speed`, `free_flow_speed`, `queue_length_m`, `delay_seconds`, `source`).

### 2. Corridors & Camera Graph
- **`GET /api/v1/operator/corridors/{corridor_id}/intelligence`**
  - Aggregated corridor speed, delay, active incidents, anomalies, and CCTV availability.
- **`GET /api/v1/operator/cameras/{camera_id}/intelligence`**
  - Resolves camera mapping to road segment, corridor, and latest vehicle telemetry.

### 3. Vehicle Intelligence & Flow
- **`POST /api/v1/operator/vehicle-telemetry`**
  - Ingests vehicle classification telemetry (`cars_count`, `bikes_count`, `buses_count`, `trucks_count`, `vehicles_per_minute`, `average_speed_kmh`, `queue_length`).
- **`GET /api/v1/operator/vehicle-flow`**
  - Returns recent timestamped vehicle classification snapshots.

### 4. Anomaly Detection V5
- **`GET /api/v1/operator/anomalies`**
  - Lists active anomalies with structured evidence.
- **`POST /api/v1/operator/anomalies/{anomaly_id}/ack`**
  - Acknowledges anomaly and logs operator audit record.
- **`POST /api/v1/operator/anomalies/{anomaly_id}/status`**
  - Transitions anomaly through lifecycle (`INVESTIGATING`, `RESOLVED`, `DISMISSED`).

### 5. Traffic Forecasting
- **`GET /api/v1/operator/forecasts`**
  - Query Params: `target_type` (`SEGMENT` | `CORRIDOR`), `target_id`
  - Returns +15, +30, and +60 min predictive horizons or `FORECAST_UNAVAILABLE`.

### 6. Explainable AI Recommendations
- **`GET /api/v1/operator/recommendations`**
  - Returns structured proposals with `WHAT`, `WHY`, `EVIDENCE`, and `SIMULATION ONLY` status.
- **`POST /api/v1/operator/recommendations`**
  - Creates a new explainable recommendation.
- **`POST /api/v1/operator/recommendations/{rec_id}/approve`**
  - Approves proposal for in silico simulation and captures `BEFORE` state outcome baseline.
- **`POST /api/v1/operator/recommendations/{rec_id}/reject`**
  - Rejects proposal with audited operator justification.

### 7. Outcome Measurement Engine
- **`GET /api/v1/operator/outcomes`**
  - Lists operational action outcome measurements.
- **`POST /api/v1/operator/outcomes/measure`**
  - Evaluates pre vs post state deltas (`speed_delta_kmh`, `queue_delta_m`) and sets outcome status.

### 8. Historical Incident Replay
- **`GET /api/v1/operator/incident-replay/{incident_id}`**
  - Synchronized chronological timeline of incidents, anomalies, alerts, and outcomes without fake video (`VIDEO_NOT_AVAILABLE`).
