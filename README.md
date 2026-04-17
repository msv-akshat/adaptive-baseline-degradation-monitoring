# Adaptive Baseline Degradation Monitoring (Edge-Fog IoT)

A real-time, edge-fog condition monitoring project for multi-engine anomaly detection using a deep reconstruction model, adaptive baseline recalibration, and ThingsBoard MQTT telemetry.

## Suggested GitHub Repository Name

adaptive-baseline-degradation-monitoring

Alternative names:
- edge-fog-adaptive-degradation-monitoring
- engine-health-adaptive-baseline-iot
- adaptive-edge-fog-anomaly-monitor

## Project Highlights

- Edge-side anomaly scoring using a Conv1D + GRU reconstruction model.
- Adaptive baseline updates (mean/std) during healthy operating windows.
- Hysteresis + EMA smoothing for stable alert transitions.
- Fog-level fleet aggregation (trend, fleet risk, warning/critical counts).
- MQTT publishing to ThingsBoard for per-engine and fleet dashboards.

## System Architecture

```text
engine_i.npy -> EdgeNode(i)
             -> model inference (reconstruction + latent)
             -> raw_score -> severity(z-score) -> risk_score + dashboard_status
             -> MQTT telemetry (engine device)

All EdgeNode payloads -> FogNode
                      -> fleet_avg_severity, fleet_trend, warning/critical counts
                      -> MQTT telemetry (fog device)
```

## Repository Structure

```text
adaptive_model.pth          # Trained PyTorch model weights
baseline.json               # Initial baseline mean/std per engine
edge_node.py                # Edge inference, adaptive baseline, status logic
engine_1.npy                # Engine stream 1
engine_2.npy                # Engine stream 2
engine_3.npy                # Engine stream 3
fog_node.py                 # Fleet-level aggregation logic
main.py                     # End-to-end orchestration loop
model.py                    # Conv1D + GRU model definition
mqtt_client.py              # ThingsBoard MQTT client wrapper
requirements.txt            # Python dependencies
tb_tokens.example.json      # Token template (safe to commit)
tb_tokens.json              # Local tokens (ignored)
```

## Prerequisites

- Python 3.10+
- pip
- Internet access (only if publishing to ThingsBoard Cloud)

## Setup

### 1) Create and activate virtual environment

Windows PowerShell:

```powershell
py -3.10 -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```powershell
pip install -r requirements.txt
```

## Configuration

You can provide ThingsBoard tokens using environment variables or `tb_tokens.json`.

### Option A: Environment variables (recommended in CI/CD)

```powershell
$env:TB_TOKEN_1 = "YOUR_ENGINE_1_TOKEN"
$env:TB_TOKEN_2 = "YOUR_ENGINE_2_TOKEN"
$env:TB_TOKEN_3 = "YOUR_ENGINE_3_TOKEN"
$env:TB_FOG_TOKEN = "YOUR_FOG_DEVICE_TOKEN"
```

### Option B: Local JSON file

1. Copy `tb_tokens.example.json` to `tb_tokens.json`
2. Replace placeholders with real tokens

`tb_tokens.json` is ignored by Git to prevent secret leakage.

## Runtime Environment Variables

| Variable | Default | Description |
|---|---|---|
| BASELINE_SOURCE_PATH | baseline.json | Source baseline stats loaded at startup |
| BASELINE_RUNTIME_PATH | baseline_runtime.json | Runtime baseline persistence file |
| BASELINE_SAVE_EVERY | 5 | Persist runtime baseline every N cycles |
| ADAPTIVE_BASELINE_ENABLED | true | Enable/disable adaptive baseline update |
| ADAPTIVE_ALPHA | 0.02 | Baseline update smoothing factor |
| ADAPTIVE_HEALTHY_Z_MAX | 2.0 | Max absolute z-score considered healthy |
| ADAPTIVE_MIN_HEALTHY_STREAK | 8 | Required healthy streak before updates |
| ADAPTIVE_UPDATE_CHUNK_SIZE | 30 | Samples needed for each baseline update chunk |
| ADAPTIVE_MAX_SHIFT_SIGMA | 0.05 | Max baseline-mean shift per update (in sigma units) |
| ADAPTIVE_STD_GROWTH_CAP | 1.02 | Caps std growth rate per update |
| ADAPTIVE_BASELINE_TREND_WINDOW | 8 | Window length for baseline trend detection |
| ADAPTIVE_BASELINE_TREND_EPS_SIGMA | 0.25 | Trend sensitivity factor |
| ADAPTIVE_DASHBOARD_WARN_Z | 2.5 | Warn threshold for dashboard status |
| ADAPTIVE_DASHBOARD_CRITICAL_Z | 4.0 | Critical threshold for dashboard status |
| ADAPTIVE_DASHBOARD_WARN_CLEAR_Z | 2.0 | Clear threshold from WARNING to NORMAL |
| ADAPTIVE_DASHBOARD_CRITICAL_CLEAR_Z | 3.2 | Clear threshold from CRITICAL state |
| ADAPTIVE_ESCALATION_CONFIRM_CYCLES | 2 | Consecutive cycles needed to escalate |
| ADAPTIVE_DEESCALATION_CONFIRM_CYCLES | 3 | Consecutive cycles needed to de-escalate |
| ADAPTIVE_MIN_STATUS_HOLD_CYCLES | 5 | Minimum hold cycles before downshift |
| ADAPTIVE_SEVERITY_EMA_ALPHA | 0.2 | EMA smoothing for severity |
| ADAPTIVE_RISK_EMA_ALPHA | 0.1 | EMA smoothing for risk score |
| ADAPTIVE_MIN_STD | 1e-6 | Lower floor for baseline std |
| TELEMETRY_PROFILE | lite | `lite` or `full` telemetry payload |
| ENGINE_PUBLISH_EVERY | 2 | Engine telemetry periodic publish interval |
| FOG_PUBLISH_EVERY | 2 | Fog telemetry periodic publish interval |
| LOG_EVERY | 2 | Console log interval |
| TB_HOST | mqtt.thingsboard.cloud | MQTT host |
| TB_PORT | 1883 | MQTT port |
| TB_TOPIC | v1/devices/me/telemetry | Telemetry topic |

## Run

```powershell
python main.py
```

Expected behavior:
- Baseline runtime resets from `baseline.json` to `baseline_runtime.json`
- Per-engine severity/status logs appear every cycle interval
- Fog fleet summary logs appear
- MQTT publish occurs if valid tokens are configured

Stop with `Ctrl+C`.

## Telemetry Overview

Engine telemetry includes:
- raw_score, severity, severity_ema
- status, dashboard_status, warning_flag, critical_flag
- risk_score, current_baseline
- plus baseline evolution fields when `TELEMETRY_PROFILE=full`

Fog telemetry includes:
- fleet_avg_severity, fleet_trend, active_engines
- fleet_warning_count, fleet_critical_count, fleet_avg_risk
- per-engine dashboard status and risk snapshots

## Troubleshooting

- "Missing baseline for engine X": ensure `baseline.json` has entries for all configured engine IDs.
- "MQTT client init failed": verify token validity, host, port, and network access.
- No ThingsBoard updates: ensure tokens are set and not placeholder values.
- Unstable status transitions: tune hysteresis and confirm-cycle parameters.

## Security Notes

- Never commit `tb_tokens.json`.
- Prefer environment variables for production tokens.
- Rotate tokens if they are accidentally exposed.

## Reproducibility Notes

- This repo includes model weights and sample engine streams to run out of the box.
- Runtime baseline changes are stored in `baseline_runtime.json` and intentionally ignored in Git.

## Future Enhancements

- Add labeled fault datasets for formal benchmark metrics.
- Add unit tests for edge/fog logic.
- Add containerized deployment profile.
- Add CI pipeline for linting and smoke tests.
