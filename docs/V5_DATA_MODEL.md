# TrafficAI V5 — Database Schema & Data Models

## MongoDB Collections & Indexes

### 1. `road_segments`
Canonical segments with coordinates and baseline attributes.
- `segment_id` (String, unique index)
- `external_id` (String, sparse index)
- `name` (String)
- `geometry` (List of [lat, lng])
- `start_point`, `end_point` ({lat, lng, name})
- `corridor_id` (String, index)
- `zone_id` (String, index)
- `free_flow_speed` (Float)
- `length_m` (Integer)
- `status` (String)

### 2. `v5_corridors`
Multi-segment arterial corridors.
- `corridor_id` (String, unique index)
- `name` (String)
- `zone_id` (String, index)
- `segment_ids` (List of String)
- `geometry` (List of [lat, lng])
- `status` (String)

### 3. `camera_road_mappings`
Spatial binding between CCTV cameras and road segments.
- `camera_id` (String, unique index)
- `segment_id` (String, index)
- `corridor_id` (String, index)
- `direction` (String)
- `distance_m` (Float)
- `mapping_status` (String)

### 4. `vehicle_flow_snapshots`
Time-series vehicle classification counts and flow rates.
- `snapshot_id` (String)
- `camera_id` (String, compound index with timestamp)
- `segment_id` (String, compound index with timestamp)
- `corridor_id` (String, compound index with timestamp)
- `timestamp` (ISO String), `timestamp_ts` (Float)
- `cars`, `bikes`, `buses`, `trucks`, `other`, `total` (Integer)
- `vehicles_per_minute` (Float)
- `direction`, `avg_speed`, `queue_length_m`, `occupancy`
- `source`, `data_status`, `freshness_seconds`

### 5. `traffic_state_snapshots`
Real-time traffic measurements.
- `segment_id`, `corridor_id` (compound indexes with timestamp)
- `timestamp`, `timestamp_ts`
- `speed`, `free_flow_speed`, `congestion_index`, `delay_seconds`, `queue_length_m`
- `source`, `status`, `freshness_seconds`

### 6. `traffic_forecasts`
Predictive horizon projections.
- `target_type` (`SEGMENT` | `CORRIDOR`), `target_id`
- `target_timestamp` (ISO String, compound index)
- `horizon_minutes` (15, 30, 60)
- `predicted_speed`, `predicted_congestion`, `predicted_queue_m`
- `model_version`, `status`

### 7. `anomalies`
Sensor anomalies with structured evidence.
- `anomaly_id` (String, unique index)
- `type` (`SUDDEN_SPEED_DROP`, `QUEUE_GROWTH`, `TRAFFIC_SURGE`, `ROAD_DATA_STALE`)
- `segment_id`, `corridor_id` (indexes)
- `severity` (`CRITICAL`, `WARNING`)
- `observed_value`, `baseline_value`, `threshold`
- `evidence` (List of {source, description, timestamp})
- `status` (`DETECTED`, `ACKNOWLEDGED`, `INVESTIGATING`, `RESOLVED`, `DISMISSED`)
- `acknowledged_by`, `acknowledged_at`, `resolved_by`, `resolved_at`

### 8. `recommendations`
Explainable AI optimization proposals.
- `recommendation_id` (String, unique index)
- `category` (`SIGNALS`, `CORRIDORS`, `DISPATCH`, `INCIDENTS`)
- `target_type`, `target_id`
- `what`, `why`, `evidence`, `data_sources`, `expected_effect`, `risks_limitations`
- `is_simulation_only` (Boolean: True)
- `status` (`PENDING_REVIEW`, `APPROVED_FOR_SIMULATION`, `REJECTED`)
- `reviewed_by`, `reviewed_at`, `simulation_result`

### 9. `outcome_events`
Empirical operational outcome tracking.
- `action_id` (String, unique index)
- `recommendation_id`, `incident_id` (sparse indexes)
- `target_id`, `action_type`, `operator_id`
- `before_state` (Snapshot), `after_state` (Snapshot)
- `action_time`, `measured_at`
- `outcome_status` (`PENDING_MEASUREMENT`, `MEASURED_IMPROVEMENT`, `NO MEASURABLE IMPROVEMENT`, `INSUFFICIENT_DATA`)
- `measured_delta` ({speed_delta_kmh, queue_delta_m})

### 10. `data_quality_snapshots`
Data quality, latency, and uptime observability.
- `source`, `measured_at` (compound index)
- `status`, `latency_ms`, `freshness_seconds`, `uptime_pct`, `error_count`
