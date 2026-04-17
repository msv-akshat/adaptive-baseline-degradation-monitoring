import numpy as np
import torch
import json
from model import FinalModel


def severity_to_status(severity):
    if severity < 60:
        return "NORMAL"
    if severity < 100:
        return "WARNING"
    return "CRITICAL"


def severity_to_dashboard_status(severity_value, warn_z, critical_z):
    if severity_value >= critical_z:
        return "CRITICAL"
    if severity_value >= warn_z:
        return "WARNING"
    return "NORMAL"


def status_rank(status):
    if status == "CRITICAL":
        return 2
    if status == "WARNING":
        return 1
    return 0

class EdgeNode:
    def __init__(
        self,
        engine_id,
        baseline_stats=None,
        adaptive_enabled=True,
        update_alpha=0.02,
        healthy_z_max=2.0,
        min_healthy_streak=8,
        update_chunk_size=30,
        max_shift_sigma=0.05,
        std_growth_cap=1.02,
        baseline_trend_window=8,
        baseline_trend_eps_sigma=0.25,
        max_pending_chunks=3,
        dashboard_warn_z=2.5,
        dashboard_critical_z=4.0,
        dashboard_warn_clear_z=2.0,
        dashboard_critical_clear_z=3.2,
        escalation_confirm_cycles=2,
        deescalation_confirm_cycles=3,
        min_status_hold_cycles=5,
        severity_ema_alpha=0.2,
        risk_ema_alpha=0.1,
        min_std=1e-6,
    ):
        self.engine_id = engine_id

        # load ONLY this engine data
        self.stream = np.load(f"engine_{engine_id}.npy")

        if baseline_stats is None:
            with open("baseline.json") as f:
                baseline_all = json.load(f)
            baseline_stats = baseline_all[str(self.engine_id)]

        self.mu = float(baseline_stats["mean"])
        self.sd = max(float(baseline_stats["std"]), min_std)

        self.adaptive_enabled = adaptive_enabled
        self.update_alpha = update_alpha
        self.healthy_z_max = healthy_z_max
        self.min_healthy_streak = min_healthy_streak
        self.update_chunk_size = max(update_chunk_size, 1)
        self.max_shift_sigma = max_shift_sigma
        self.std_growth_cap = std_growth_cap
        self.baseline_trend_window = max(baseline_trend_window, 2)
        self.baseline_trend_eps_sigma = baseline_trend_eps_sigma
        self.max_pending_chunks = max(max_pending_chunks, 1)
        self.dashboard_warn_z = dashboard_warn_z
        self.dashboard_critical_z = dashboard_critical_z
        self.dashboard_warn_clear_z = min(dashboard_warn_clear_z, self.dashboard_warn_z)
        self.dashboard_critical_clear_z = min(dashboard_critical_clear_z, self.dashboard_critical_z)
        self.escalation_confirm_cycles = max(escalation_confirm_cycles, 1)
        self.deescalation_confirm_cycles = max(deescalation_confirm_cycles, 1)
        self.min_status_hold_cycles = max(min_status_hold_cycles, 0)
        self.severity_ema_alpha = max(0.0, min(severity_ema_alpha, 1.0))
        self.risk_ema_alpha = max(0.0, min(risk_ema_alpha, 1.0))
        self.min_std = min_std
        self.healthy_streak = 0
        self.pending_raw = []
        self.baseline_mean_history = [self.mu]
        self.severity_ema = None
        self.risk_ema = None
        self.dashboard_status_state = "NORMAL"
        self.status_hold_cycles = 0
        self.escalation_counter = 0
        self.deescalation_counter = 0
        self.last_transition_target = None
        self.baseline_update_count = 0
        self.cycles_since_baseline_update = 0

        self.model = FinalModel()
        self.model.load_state_dict(torch.load("adaptive_model.pth"))
        self.model.eval()

        self.pointer = 0

    def _baseline_trend(self):
        window = self.baseline_mean_history[-self.baseline_trend_window:]
        if len(window) < 2:
            return "STABLE"

        delta = window[-1] - window[0]
        eps = self.baseline_trend_eps_sigma * max(self.sd, self.min_std)
        if delta > eps:
            return "RISING"
        if delta < -eps:
            return "FALLING"
        return "STABLE"

    def _hysteresis_target_status(self, risk_signal):
        current = self.dashboard_status_state

        if current == "NORMAL":
            if risk_signal >= self.dashboard_critical_z:
                return "CRITICAL"
            if risk_signal >= self.dashboard_warn_z:
                return "WARNING"
            return "NORMAL"

        if current == "WARNING":
            if risk_signal >= self.dashboard_critical_z:
                return "CRITICAL"
            if risk_signal < self.dashboard_warn_clear_z:
                return "NORMAL"
            return "WARNING"

        if risk_signal < self.dashboard_critical_clear_z:
            if risk_signal >= self.dashboard_warn_z:
                return "WARNING"
            return "NORMAL"
        return "CRITICAL"

    def _update_dashboard_status(self, risk_signal):
        target = self._hysteresis_target_status(risk_signal)
        current = self.dashboard_status_state

        if target == current:
            self.escalation_counter = 0
            self.deescalation_counter = 0
            self.last_transition_target = None
            self.status_hold_cycles += 1
            return current

        moving_up = status_rank(target) > status_rank(current)

        if moving_up:
            if self.last_transition_target != target:
                self.escalation_counter = 0
            self.escalation_counter += 1
            self.deescalation_counter = 0
            self.last_transition_target = target

            if self.escalation_counter >= self.escalation_confirm_cycles:
                self.dashboard_status_state = target
                self.status_hold_cycles = 0
                self.escalation_counter = 0
                self.last_transition_target = None
            return self.dashboard_status_state

        if self.status_hold_cycles < self.min_status_hold_cycles:
            self.escalation_counter = 0
            self.deescalation_counter = 0
            self.last_transition_target = None
            self.status_hold_cycles += 1
            return self.dashboard_status_state

        if self.last_transition_target != target:
            self.deescalation_counter = 0
        self.deescalation_counter += 1
        self.escalation_counter = 0
        self.last_transition_target = target

        if self.deescalation_counter >= self.deescalation_confirm_cycles:
            self.dashboard_status_state = target
            self.status_hold_cycles = 0
            self.deescalation_counter = 0
            self.last_transition_target = None

        return self.dashboard_status_state

    def step(self):
        x = self.stream[self.pointer]
        x = torch.tensor(x).unsqueeze(0).float()

        with torch.no_grad():
            recon, z = self.model(x)

        re = torch.mean((x - recon)**2).item()
        ld = torch.mean(torch.abs(z)).item()
        raw = re * (1 + ld)

        mu_for_scoring = self.mu
        sd_for_scoring = max(self.sd, self.min_std)
        severity = (raw - mu_for_scoring) / sd_for_scoring
        status = severity_to_status(severity)

        severity_pos = max(severity, 0.0)
        if self.severity_ema is None:
            self.severity_ema = severity_pos
        else:
            self.severity_ema = ((1.0 - self.severity_ema_alpha) * self.severity_ema) + (self.severity_ema_alpha * severity_pos)

        instant_risk = min(100.0, max(0.0, (severity_pos / max(self.dashboard_critical_z, self.min_std)) * 100.0))
        if self.risk_ema is None:
            self.risk_ema = instant_risk
        else:
            self.risk_ema = ((1.0 - self.risk_ema_alpha) * self.risk_ema) + (self.risk_ema_alpha * instant_risk)

        risk_score = self.risk_ema
        risk_signal = max(self.severity_ema, risk_score / 100.0 * self.dashboard_critical_z)
        dashboard_status = self._update_dashboard_status(risk_signal)
        warning_flag = 1 if dashboard_status == "WARNING" else 0
        critical_flag = 1 if dashboard_status == "CRITICAL" else 0
        alert_level = status_rank(dashboard_status)

        deviation = raw - mu_for_scoring
        deviation_pct = (deviation / max(abs(mu_for_scoring), self.min_std)) * 100.0

        healthy_for_update = (
            self.adaptive_enabled
            and abs(severity) <= self.healthy_z_max
        )

        if healthy_for_update:
            self.healthy_streak += 1
            self.pending_raw.append(raw)

            # Keep a bounded healthy buffer so progress survives brief anomalies.
            max_pending = self.update_chunk_size * self.max_pending_chunks
            if len(self.pending_raw) > max_pending:
                self.pending_raw = self.pending_raw[-max_pending:]
        else:
            self.healthy_streak = 0

        baseline_updated = False
        if (
            healthy_for_update
            and self.healthy_streak >= self.min_healthy_streak
            and len(self.pending_raw) >= self.update_chunk_size
        ):
            chunk = self.pending_raw[:self.update_chunk_size]
            self.pending_raw = self.pending_raw[self.update_chunk_size:]

            chunk_mean = float(np.mean(chunk))
            chunk_var = float(np.var(chunk))

            target_mu = self.mu + self.update_alpha * (chunk_mean - self.mu)
            raw_shift = target_mu - self.mu
            max_shift = self.max_shift_sigma * sd_for_scoring

            if raw_shift > max_shift:
                raw_shift = max_shift
            elif raw_shift < -max_shift:
                raw_shift = -max_shift

            new_mu = self.mu + raw_shift
            old_var = sd_for_scoring * sd_for_scoring
            target_var = chunk_var + (chunk_mean - new_mu) * (chunk_mean - new_mu)
            new_var = (1.0 - self.update_alpha) * old_var + self.update_alpha * target_var
            new_sd = max(new_var ** 0.5, self.min_std)

            max_allowed_sd = max(sd_for_scoring * self.std_growth_cap, self.min_std)
            if new_sd > max_allowed_sd:
                new_sd = max_allowed_sd

            self.mu = new_mu
            self.sd = new_sd
            self.baseline_mean_history.append(self.mu)
            if len(self.baseline_mean_history) > self.baseline_trend_window:
                self.baseline_mean_history.pop(0)
            baseline_updated = True
            self.baseline_update_count += 1
            self.cycles_since_baseline_update = 0
        else:
            self.cycles_since_baseline_update += 1

        baseline_trend = self._baseline_trend()

        self.pointer += 1
        if self.pointer >= len(self.stream):
            self.pointer = 0

        return {
            "engine_id": self.engine_id,
            "raw_score": raw,
            "severity": severity,
            "severity_ema": self.severity_ema,
            "status": status,
            "dashboard_status": dashboard_status,
            "warning_flag": warning_flag,
            "critical_flag": critical_flag,
            "alert_level": alert_level,
            "risk_score": risk_score,
            "deviation": deviation,
            "deviation_pct": deviation_pct,
            "baseline_updated": baseline_updated,
            "baseline_mean": self.mu,
            "baseline_std": self.sd,
            "current_baseline": self.mu,
            "current_baseline_std": self.sd,
            "baseline_trend": baseline_trend,
            "baseline_chunk_progress": len(self.pending_raw),
            "baseline_chunk_size": self.update_chunk_size,
            "baseline_chunk_progress_pct": (len(self.pending_raw) / self.update_chunk_size) * 100.0,
            "baseline_update_ready": len(self.pending_raw) >= self.update_chunk_size,
            "baseline_updates_count": self.baseline_update_count,
            "cycles_since_baseline_update": self.cycles_since_baseline_update,
        }

    def get_baseline_state(self):
        return {
            "mean": self.mu,
            "std": self.sd,
        }