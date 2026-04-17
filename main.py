import time
import os
import json
from edge_node import EdgeNode
from mqtt_client import MQTTClient
from fog_node import FogNode


def is_valid_token(value):
    if not value:
        return False
    return not value.strip().startswith("PASTE_")


def load_tb_token_file(path="tb_tokens.json"):
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Failed to read {path}: {exc}")
        return {}


def load_engine_tokens(engine_ids, file_tokens):
    tokens = {}
    for eid in engine_ids:
        token = os.getenv(f"TB_TOKEN_{eid}")
        if is_valid_token(token):
            tokens[eid] = token

    for eid in engine_ids:
        if eid not in tokens and str(eid) in file_tokens and is_valid_token(file_tokens[str(eid)]):
            tokens[eid] = file_tokens[str(eid)]

    return tokens


def load_fog_token(file_tokens):
    env_token = os.getenv("TB_FOG_TOKEN")
    if is_valid_token(env_token):
        return env_token

    file_token = file_tokens.get("fog")
    if is_valid_token(file_token):
        return file_token

    return None


def initialize_runtime_baseline(source_path, target_path):
    with open(source_path, "r", encoding="utf-8") as f:
        baseline_data = json.load(f)

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, indent=2)

    return baseline_data


def persist_runtime_baseline(path, edge_nodes):
    data = {}
    for eid, node in edge_nodes.items():
        data[str(eid)] = node.get_baseline_state()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def is_enabled(value, default=True):
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def build_engine_telemetry(cycle, engine_id, edge_payload, fog_payload, profile):
    telemetry = {
        "cycle": cycle,
        "engine_id": engine_id,
        "raw_score": edge_payload["raw_score"],
        "severity": edge_payload["severity"],
        "severity_ema": edge_payload["severity_ema"],
        "status": edge_payload["status"],
        "dashboard_status": edge_payload["dashboard_status"],
        "warning_flag": edge_payload["warning_flag"],
        "critical_flag": edge_payload["critical_flag"],
        "alert_level": edge_payload["alert_level"],
        "risk_score": edge_payload["risk_score"],
        "current_baseline": edge_payload["current_baseline"],
    }

    if profile == "full":
        telemetry.update({
            "deviation": edge_payload["deviation"],
            "deviation_pct": edge_payload["deviation_pct"],
            "avg_severity": fog_payload["avg_severity"],
            "trend": fog_payload["trend"],
            "baseline_updated": edge_payload["baseline_updated"],
            "baseline_mean": edge_payload["baseline_mean"],
            "baseline_std": edge_payload["baseline_std"],
            "current_baseline_std": edge_payload["current_baseline_std"],
            "baseline_trend": edge_payload["baseline_trend"],
            "baseline_chunk_progress": edge_payload["baseline_chunk_progress"],
            "baseline_chunk_size": edge_payload["baseline_chunk_size"],
            "baseline_chunk_progress_pct": edge_payload["baseline_chunk_progress_pct"],
            "baseline_update_ready": edge_payload["baseline_update_ready"],
            "baseline_updates_count": edge_payload["baseline_updates_count"],
            "cycles_since_baseline_update": edge_payload["cycles_since_baseline_update"],
        })

    return telemetry


def build_fog_telemetry(cycle, shared_fog, edge_payloads, engine_states, warning_count, critical_count, fleet_avg_risk, max_engine_payload, profile):
    fog_telemetry = {
        "cycle": cycle,
        "fleet_avg_severity": shared_fog["fleet_avg_severity"],
        "fleet_trend": shared_fog["fleet_trend"],
        "active_engines": shared_fog["active_engines"],
        "fleet_warning_count": warning_count,
        "fleet_critical_count": critical_count,
        "fleet_avg_risk": fleet_avg_risk,
        "fleet_max_severity_ema": max_engine_payload["severity_ema"],
        "fleet_max_engine_id": max_engine_payload["engine_id"],
    }

    for eid, edge_payload in edge_payloads.items():
        fog_telemetry[f"engine_{eid}_dashboard_status"] = edge_payload["dashboard_status"]
        fog_telemetry[f"engine_{eid}_risk_score"] = edge_payload["risk_score"]
        fog_telemetry[f"engine_{eid}_current_baseline"] = edge_payload["current_baseline"]
        fog_telemetry[f"engine_{eid}_baseline_chunk_progress_pct"] = edge_payload["baseline_chunk_progress_pct"]

        if profile == "full":
            fog_telemetry[f"engine_{eid}_severity"] = edge_payload["severity"]
            fog_telemetry[f"engine_{eid}_severity_ema"] = edge_payload["severity_ema"]
            fog_telemetry[f"engine_{eid}_status"] = edge_payload["status"]
            fog_telemetry[f"engine_{eid}_baseline_mean"] = edge_payload["baseline_mean"]
            fog_telemetry[f"engine_{eid}_baseline_std"] = edge_payload["baseline_std"]
            fog_telemetry[f"engine_{eid}_current_baseline_std"] = edge_payload["current_baseline_std"]
            fog_telemetry[f"engine_{eid}_baseline_trend"] = edge_payload["baseline_trend"]
            fog_telemetry[f"engine_{eid}_baseline_updated"] = edge_payload["baseline_updated"]
            fog_telemetry[f"engine_{eid}_baseline_chunk_progress"] = edge_payload["baseline_chunk_progress"]
            fog_telemetry[f"engine_{eid}_baseline_chunk_size"] = edge_payload["baseline_chunk_size"]

    return fog_telemetry


engine_ids = [1, 2, 3]

baseline_source_path = os.getenv("BASELINE_SOURCE_PATH", "baseline.json")
baseline_runtime_path = os.getenv("BASELINE_RUNTIME_PATH", "baseline_runtime.json")
baseline_save_every = max(int(os.getenv("BASELINE_SAVE_EVERY", "5")), 1)

adaptive_enabled = is_enabled(os.getenv("ADAPTIVE_BASELINE_ENABLED"), default=True)
adaptive_alpha = float(os.getenv("ADAPTIVE_ALPHA", "0.02"))
adaptive_healthy_z_max = float(os.getenv("ADAPTIVE_HEALTHY_Z_MAX", "2.0"))
adaptive_min_healthy_streak = int(os.getenv("ADAPTIVE_MIN_HEALTHY_STREAK", "8"))
adaptive_update_chunk_size = int(os.getenv("ADAPTIVE_UPDATE_CHUNK_SIZE", "30"))
adaptive_max_shift_sigma = float(os.getenv("ADAPTIVE_MAX_SHIFT_SIGMA", "0.05"))
adaptive_std_growth_cap = float(os.getenv("ADAPTIVE_STD_GROWTH_CAP", "1.02"))
adaptive_baseline_trend_window = int(os.getenv("ADAPTIVE_BASELINE_TREND_WINDOW", "8"))
adaptive_baseline_trend_eps_sigma = float(os.getenv("ADAPTIVE_BASELINE_TREND_EPS_SIGMA", "0.25"))
adaptive_dashboard_warn_z = float(os.getenv("ADAPTIVE_DASHBOARD_WARN_Z", "2.5"))
adaptive_dashboard_critical_z = float(os.getenv("ADAPTIVE_DASHBOARD_CRITICAL_Z", "4.0"))
adaptive_dashboard_warn_clear_z = float(os.getenv("ADAPTIVE_DASHBOARD_WARN_CLEAR_Z", "2.0"))
adaptive_dashboard_critical_clear_z = float(os.getenv("ADAPTIVE_DASHBOARD_CRITICAL_CLEAR_Z", "3.2"))
adaptive_escalation_confirm_cycles = int(os.getenv("ADAPTIVE_ESCALATION_CONFIRM_CYCLES", "2"))
adaptive_deescalation_confirm_cycles = int(os.getenv("ADAPTIVE_DEESCALATION_CONFIRM_CYCLES", "3"))
adaptive_min_status_hold_cycles = int(os.getenv("ADAPTIVE_MIN_STATUS_HOLD_CYCLES", "5"))
adaptive_severity_ema_alpha = float(os.getenv("ADAPTIVE_SEVERITY_EMA_ALPHA", "0.2"))
adaptive_risk_ema_alpha = float(os.getenv("ADAPTIVE_RISK_EMA_ALPHA", "0.1"))
adaptive_min_std = float(os.getenv("ADAPTIVE_MIN_STD", "1e-6"))

telemetry_profile = os.getenv("TELEMETRY_PROFILE", "lite").strip().lower()
if telemetry_profile not in {"lite", "full"}:
    telemetry_profile = "lite"

engine_publish_every = max(int(os.getenv("ENGINE_PUBLISH_EVERY", "2")), 1)
fog_publish_every = max(int(os.getenv("FOG_PUBLISH_EVERY", "2")), 1)
log_every = max(int(os.getenv("LOG_EVERY", "2")), 1)

runtime_baseline = initialize_runtime_baseline(baseline_source_path, baseline_runtime_path)
print(f"Baseline runtime reset: {baseline_source_path} -> {baseline_runtime_path}")
print(f"Adaptive baseline enabled: {adaptive_enabled}")
print(f"Adaptive chunk size: {adaptive_update_chunk_size}")
print(
    "Status stability config: "
    f"warn={adaptive_dashboard_warn_z}/{adaptive_dashboard_warn_clear_z}, "
    f"critical={adaptive_dashboard_critical_z}/{adaptive_dashboard_critical_clear_z}, "
    f"up_confirm={adaptive_escalation_confirm_cycles}, "
    f"down_confirm={adaptive_deescalation_confirm_cycles}, "
    f"min_hold={adaptive_min_status_hold_cycles}"
)
print(f"Telemetry profile: {telemetry_profile}")
print(f"Publish intervals (engine/fog): {engine_publish_every}s/{fog_publish_every}s")

edge_nodes = {}
for eid in engine_ids:
    key = str(eid)
    if key not in runtime_baseline:
        raise KeyError(f"Missing baseline for engine {eid} in {baseline_source_path}")

    edge_nodes[eid] = EdgeNode(
        eid,
        baseline_stats=runtime_baseline[key],
        adaptive_enabled=adaptive_enabled,
        update_alpha=adaptive_alpha,
        healthy_z_max=adaptive_healthy_z_max,
        min_healthy_streak=adaptive_min_healthy_streak,
        update_chunk_size=adaptive_update_chunk_size,
        max_shift_sigma=adaptive_max_shift_sigma,
        std_growth_cap=adaptive_std_growth_cap,
        baseline_trend_window=adaptive_baseline_trend_window,
        baseline_trend_eps_sigma=adaptive_baseline_trend_eps_sigma,
        dashboard_warn_z=adaptive_dashboard_warn_z,
        dashboard_critical_z=adaptive_dashboard_critical_z,
        dashboard_warn_clear_z=adaptive_dashboard_warn_clear_z,
        dashboard_critical_clear_z=adaptive_dashboard_critical_clear_z,
        escalation_confirm_cycles=adaptive_escalation_confirm_cycles,
        deescalation_confirm_cycles=adaptive_deescalation_confirm_cycles,
        min_status_hold_cycles=adaptive_min_status_hold_cycles,
        severity_ema_alpha=adaptive_severity_ema_alpha,
        risk_ema_alpha=adaptive_risk_ema_alpha,
        min_std=adaptive_min_std,
    )

for eid, node in edge_nodes.items():
    stream_len = len(node.stream)
    print(f"Engine {eid}: stream length = {stream_len}")
    if stream_len < 30:
        print(f"Engine {eid}: short stream may rarely produce WARNING/CRITICAL transitions")

tb_host = os.getenv("TB_HOST", "mqtt.thingsboard.cloud")
tb_port = int(os.getenv("TB_PORT", "1883"))
tb_topic = os.getenv("TB_TOPIC", "v1/devices/me/telemetry")

file_tokens = load_tb_token_file()
engine_tokens = load_engine_tokens(edge_nodes.keys(), file_tokens)
fog_token = load_fog_token(file_tokens)

mqtt_clients = {}
fog_client = None

for eid in edge_nodes.keys():
    token = engine_tokens.get(eid)
    if not token:
        print(f"Engine {eid}: no ThingsBoard token configured (skip publish)")
        mqtt_clients[eid] = None
        continue

    try:
        mqtt_clients[eid] = MQTTClient(token, host=tb_host, port=tb_port, topic=tb_topic)
        print(f"Engine {eid}: MQTT client initialized ({tb_host}:{tb_port})")
    except Exception as exc:
        print(f"Engine {eid}: MQTT client init failed: {exc}")
        mqtt_clients[eid] = None

if fog_token:
    try:
        fog_client = MQTTClient(fog_token, host=tb_host, port=tb_port, topic=tb_topic)
        print(f"Fog: MQTT client initialized ({tb_host}:{tb_port})")
    except Exception as exc:
        print(f"Fog: MQTT client init failed: {exc}")
        fog_client = None
else:
    print("Fog: no ThingsBoard token configured (skip publish)")

fog = FogNode()
cycle = 0
engine_schema_printed = False
fog_schema_printed = False
last_engine_status = {eid: None for eid in edge_nodes.keys()}
last_fog_signature = None

try:
    while True:
        cycle += 1
        edge_payloads = {}
        for eid, node in edge_nodes.items():
            edge_payloads[eid] = node.step()

        fog_views = fog.update_batch(list(edge_payloads.values()))

        for eid in edge_nodes.keys():
            edge_payload = edge_payloads[eid]
            fog_payload = fog_views[eid]

            telemetry = build_engine_telemetry(cycle, eid, edge_payload, fog_payload, telemetry_profile)

            status_changed = edge_payload["dashboard_status"] != last_engine_status[eid]
            should_publish = status_changed or (cycle % engine_publish_every == 0)

            if status_changed or (cycle % log_every == 0):
                print(
                    f"Engine {eid} | sev={edge_payload['severity']:.2f} ema={edge_payload['severity_ema']:.2f} "
                    f"dash={edge_payload['dashboard_status']} risk={edge_payload['risk_score']:.1f}% "
                    f"raw={edge_payload['raw_score']:.6f} base={edge_payload['current_baseline']:.6f} "
                    f"bchunk={edge_payload['baseline_chunk_progress']}/{edge_payload['baseline_chunk_size']} "
                    f"({edge_payload['baseline_chunk_progress_pct']:.0f}%)"
                )

            if not engine_schema_printed:
                print("Engine telemetry keys:", ", ".join(sorted(telemetry.keys())))
                engine_schema_printed = True

            if should_publish and mqtt_clients[eid] is not None:
                ok = mqtt_clients[eid].send(telemetry)
                if not ok:
                    print(f"Engine {eid}: publish failed")

            if should_publish:
                last_engine_status[eid] = edge_payload["dashboard_status"]

        if fog_views:
            shared_fog = next(iter(fog_views.values()))
            engine_states = [edge_payloads[eid] for eid in edge_nodes.keys()]

            max_engine_payload = max(engine_states, key=lambda item: item["severity_ema"])
            warning_count = sum(1 for item in engine_states if item["dashboard_status"] == "WARNING")
            critical_count = sum(1 for item in engine_states if item["dashboard_status"] == "CRITICAL")
            fleet_avg_risk = sum(item["risk_score"] for item in engine_states) / len(engine_states)

            fog_telemetry = build_fog_telemetry(
                cycle,
                shared_fog,
                edge_payloads,
                engine_states,
                warning_count,
                critical_count,
                fleet_avg_risk,
                max_engine_payload,
                telemetry_profile,
            )

            fog_signature = (
                warning_count,
                critical_count,
                max_engine_payload["engine_id"],
                round(fleet_avg_risk, 1),
            )
            fog_changed = fog_signature != last_fog_signature
            should_publish_fog = fog_changed or (cycle % fog_publish_every == 0)

            if fog_changed or (cycle % log_every == 0):
                print(
                    f"Fog | fleet_avg={fog_telemetry['fleet_avg_severity']:.2f} "
                    f"fleet_trend={fog_telemetry['fleet_trend']} active={fog_telemetry['active_engines']} "
                    f"warn={warning_count} crit={critical_count} max_engine={fog_telemetry['fleet_max_engine_id']}"
                )

            if not fog_schema_printed:
                print("Fog telemetry keys:", ", ".join(sorted(fog_telemetry.keys())))
                fog_schema_printed = True

            if should_publish_fog and fog_client is not None:
                ok = fog_client.send(fog_telemetry)
                if not ok:
                    print("Fog: publish failed")

            if should_publish_fog:
                last_fog_signature = fog_signature

        if cycle % baseline_save_every == 0:
            persist_runtime_baseline(baseline_runtime_path, edge_nodes)

        print("=" * 70)
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping edge-fog simulation...")
finally:
    persist_runtime_baseline(baseline_runtime_path, edge_nodes)
    for client in mqtt_clients.values():
        if client is not None:
            client.close()
    if fog_client is not None:
        fog_client.close()