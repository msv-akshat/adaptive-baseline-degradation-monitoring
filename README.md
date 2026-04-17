# Adaptive Baseline Degradation Monitoring

Edge-Fog-Cloud monitoring system for real-time engine degradation detection with adaptive thresholds, fleet-level aggregation, and ThingsBoard dashboards.

## What This Project Delivers

- Real-time edge inference per engine using a Conv1D + GRU reconstruction model.
- Adaptive baseline tracking (mean and std) so thresholds stay useful as operating conditions drift.
- Stable alerting with smoothing, hysteresis, confirmation cycles, and hold-time logic.
- Fog-level aggregation for fleet KPIs, top-risk engine tracking, and warning/critical counts.
- ThingsBoard integration for live telemetry, dashboard widgets, and alarm workflows.

## Core Functionalities

### 1) Edge Intelligence

- Each engine stream is processed by an independent edge node.
- Anomaly severity is computed from reconstruction behavior and latent representation.
- Dashboard status is generated as NORMAL, WARNING, or CRITICAL.

### 2) Adaptive Baseline Management

- Baseline is not static; it updates during healthy operating windows.
- Update chunking, bounded shift, and std-growth caps prevent runaway drift.
- Runtime baseline is persisted to support continuity during long-running sessions.

### 3) Fog-Level Fleet Monitoring

- Collects all engine outputs and computes fleet-wide summary metrics.
- Tracks fleet trend, active engines, warning count, and critical count.
- Publishes fleet telemetry as a dedicated upstream signal.

### 4) Alert and Dashboard Pipeline

- Telemetry is pushed to ThingsBoard through MQTT.
- Dashboard shows both fleet KPIs and engine-level status panels.
- Alarm list reflects critical degradations for operator response.

## Architecture Diagram

Place your finalized architecture image at:

- docs/images/architecture-diagram.png



## Dashboard Screenshots

<img width="824" height="1377" alt="image" src="https://github.com/user-attachments/assets/95abd79f-ee52-4a85-8a42-5d5cdf7eafe4" />

### Dashboard Overview

<img width="940" height="529" alt="image" src="https://github.com/user-attachments/assets/1a716bc1-7da1-4efe-912a-e5edbdbc2d5b" />

### Trends and Active Alerts

<img width="940" height="529" alt="image" src="https://github.com/user-attachments/assets/f560d8ec-dc1e-4c8f-9777-91c6a86b7a43" />

### Alarm List

<img width="940" height="219" alt="image" src="https://github.com/user-attachments/assets/e4179d7b-d290-49ca-8997-14d0684eff8f" />

## End-to-End Data Flow

1. Edge nodes load engine streams from NumPy files.
2. Model inference produces reconstruction-driven anomaly signals.
3. Severity and risk are stabilized into dashboard-friendly status transitions.
4. Fog node aggregates fleet metrics and trend signals.
5. MQTT publisher sends engine and fog telemetry to ThingsBoard.
6. Rule chain stores timeseries and triggers warning or critical alarms.
7. Operators monitor KPIs and alarms from the dashboard.

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Setup

```powershell
py -3.10 -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Token Configuration

Use either environment variables or a local token file.

Environment variable option:

```powershell
$env:TB_TOKEN_1 = "YOUR_ENGINE_1_TOKEN"
$env:TB_TOKEN_2 = "YOUR_ENGINE_2_TOKEN"
$env:TB_TOKEN_3 = "YOUR_ENGINE_3_TOKEN"
$env:TB_FOG_TOKEN = "YOUR_FOG_TOKEN"
```

Local file option:

1. Copy tb_tokens.example.json as tb_tokens.json
2. Replace placeholders with real tokens

### Run

```powershell
python main.py
```

## Project Structure

```text
adaptive_model.pth
baseline.json
edge_node.py
engine_1.npy
engine_2.npy
engine_3.npy
fog_node.py
main.py
model.py
mqtt_client.py
requirements.txt
tb_tokens.example.json
```

## Important Runtime Controls

Most projects only need these controls:

- TELEMETRY_PROFILE: lite or full payload mode
- TB_HOST, TB_PORT, TB_TOPIC: ThingsBoard broker settings
- ADAPTIVE_BASELINE_ENABLED: enable or disable adaptive baseline behavior

Advanced tuning parameters are available in the source for threshold and adaptation behavior, but default values are already production-friendly for demonstration.

## Security and Git Hygiene

- tb_tokens.json is ignored and must never be committed.
- baseline_runtime.json is runtime-generated and ignored.
- venv and cache folders are ignored.

## Known Limitations

- Current streams are demonstration data with a fixed engine count.
- Formal benchmark evaluation with externally labeled faults is not included in this repo.

## Roadmap

- Add automated tests for edge and fog modules.
- Add replay mode and batch evaluation scripts.
- Add containerized deployment profile.
