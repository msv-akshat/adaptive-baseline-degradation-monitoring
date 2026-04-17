class FogNode:
    def __init__(self, window_size=10, trend_epsilon=0.5):
        self.history = {}
        self.window_size = window_size
        self.trend_epsilon = trend_epsilon
        self.fleet_history = []

    def _trend(self, series):
        if len(series) < 2:
            return "STABLE"

        delta = series[-1] - series[0]
        if delta > self.trend_epsilon:
            return "RISING"
        return "STABLE"

    def update(self, edge_data):
        eid = edge_data["engine_id"]
        sev = edge_data["severity"]

        if eid not in self.history:
            self.history[eid] = []

        self.history[eid].append(sev)

        # keep last N values per engine
        if len(self.history[eid]) > self.window_size:
            self.history[eid].pop(0)

        engine_avg = sum(self.history[eid]) / len(self.history[eid])
        engine_trend = self._trend(self.history[eid])

        return {
            "engine_id": eid,
            "avg_severity": engine_avg,
            "trend": engine_trend
        }

    def update_batch(self, edge_payloads):
        per_engine = {}

        for edge_data in edge_payloads:
            engine_view = self.update(edge_data)
            per_engine[engine_view["engine_id"]] = engine_view

        latest_values = [vals[-1] for vals in self.history.values() if vals]
        fleet_avg_now = sum(latest_values) / len(latest_values)

        self.fleet_history.append(fleet_avg_now)
        if len(self.fleet_history) > self.window_size:
            self.fleet_history.pop(0)

        fleet_trend = self._trend(self.fleet_history)

        result = {}
        for eid, engine_view in per_engine.items():
            result[eid] = {
                "engine_id": eid,
                "avg_severity": engine_view["avg_severity"],
                "trend": engine_view["trend"],
                "fleet_avg_severity": fleet_avg_now,
                "fleet_trend": fleet_trend,
                "active_engines": len(latest_values)
            }

        return result