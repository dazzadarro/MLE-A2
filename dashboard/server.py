from __future__ import annotations

import json
import math
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", ROOT.parent))
STATIC_ROOT = ROOT / "static"
GOLD_ROOT = PROJECT_ROOT / "datamart" / "gold"
MODEL_BANK = PROJECT_ROOT / "model_bank"


def _clean_number(value):
    if value is None or pd.isna(value) or math.isinf(float(value)):
        return None
    return round(float(value), 4)


def _read_parquet(name):
    path = GOLD_ROOT / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _read_registry():
    path = MODEL_BANK / "model_registry.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _records(df):
    if df.empty:
        return []
    output = df.copy()
    for column in output.columns:
        if "date" in column:
            output[column] = pd.to_datetime(output[column], errors="coerce").dt.strftime("%Y-%m-%d")
    output = output.where(pd.notnull(output), None)
    return output.to_dict(orient="records")


def dashboard_payload(params):
    monitoring = _read_parquet("model_monitoring")
    drift = _read_parquet("feature_drift_monitoring")
    evaluation = _read_parquet("model_evaluation")
    predictions = _read_parquet("model_predictions")
    registry = _read_registry()

    if monitoring.empty:
        return {
            "ready": False,
            "message": "Run python main.py to create the Gold monitoring tables.",
            "registry": registry,
            "months": [],
            "summary": {},
            "performance": [],
            "drift": [],
            "evaluation": [],
        }

    monitoring["snapshot_date"] = pd.to_datetime(monitoring["snapshot_date"])
    monitoring = monitoring.sort_values("snapshot_date")
    drift["snapshot_date"] = pd.to_datetime(drift["snapshot_date"])
    months = monitoring["snapshot_date"].dt.strftime("%Y-%m-%d").drop_duplicates().tolist()
    selected_month = params.get("month", [months[-1]])[0]
    selected = monitoring[
        monitoring["snapshot_date"].dt.strftime("%Y-%m-%d") == selected_month
    ]
    if selected.empty:
        selected = monitoring.tail(1)
        selected_month = selected.iloc[0]["snapshot_date"].strftime("%Y-%m-%d")
    latest = selected.iloc[0]

    selected_drift = drift[
        drift["snapshot_date"].dt.strftime("%Y-%m-%d") == selected_month
    ].sort_values("csi", ascending=False)
    selected_drift = selected_drift.head(15)

    prediction_count = 0
    if not predictions.empty:
        predictions["snapshot_date"] = pd.to_datetime(predictions["snapshot_date"])
        prediction_count = int(
            (
                predictions["snapshot_date"].dt.strftime("%Y-%m-%d")
                == selected_month
            ).sum()
        )

    summary = {
        "snapshot_date": selected_month,
        "model_name": latest.get("model_name") or registry.get("champion_model"),
        "model_version": latest.get("model_version") or registry.get("model_version"),
        "monitoring_status": latest.get("monitoring_status", "unknown"),
        "data_drift_status": latest.get("data_drift_status", "unknown"),
        "performance_drift_status": latest.get("performance_drift_status", "unknown"),
        "observation_status": latest.get("observation_status", "unknown"),
        "prediction_count": prediction_count or int(latest.get("record_count", 0)),
        "p0_name": latest.get("p0_metric_name", "recall"),
        "p0_value": _clean_number(latest.get("p0_metric_value")),
        "p1_name": latest.get("p1_metric_name", "roc_auc"),
        "p1_value": _clean_number(latest.get("p1_metric_value")),
        "psi": _clean_number(latest.get("psi")),
        "predicted_default_rate": _clean_number(latest.get("predicted_default_rate")),
        "observed_default_rate": _clean_number(latest.get("observed_default_rate")),
        "significant_feature_count": int((selected_drift["csi"] > 0.25).sum()),
        "watch_feature_count": int(
            ((selected_drift["csi"] >= 0.10) & (selected_drift["csi"] <= 0.25)).sum()
        ),
    }

    performance_columns = [
        "snapshot_date",
        "p0_metric_value",
        "p1_metric_value",
        "precision",
        "recall",
        "f1_score",
        "pr_auc",
        "psi",
        "predicted_default_rate",
        "observed_default_rate",
        "monitoring_status",
        "observation_status",
    ]
    performance = monitoring[[c for c in performance_columns if c in monitoring.columns]]
    drift_columns = [
        "feature_name",
        "csi",
        "drift_status",
        "baseline_mean",
        "current_mean",
    ]

    return {
        "ready": True,
        "message": "",
        "registry": registry,
        "months": months,
        "selected_month": selected_month,
        "summary": summary,
        "performance": _records(performance),
        "drift": _records(selected_drift[drift_columns]),
        "evaluation": _records(evaluation),
        "thresholds": {
            "stable_upper": 0.10,
            "watch_upper": 0.25,
        },
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json({"status": "ok"})
            return
        if parsed.path == "/api/monitoring":
            self._write_json(dashboard_payload(parse_qs(parsed.query)))
            return
        return super().do_GET()

    def _write_json(self, payload):
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", "8050"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Loan monitoring dashboard listening on http://0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
