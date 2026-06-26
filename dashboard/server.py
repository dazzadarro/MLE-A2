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
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _records(df):
    if df.empty:
        return []
    output = df.copy()
    for column in output.columns:
        if "date" in column:
            output[column] = pd.to_datetime(output[column], errors="coerce").dt.strftime("%Y-%m-%d")
    output = output.astype(object).where(pd.notnull(output), None)
    return output.to_dict(orient="records")


def _format_month_range(dates):
    if len(dates) == 0:
        return "-"
    ordered = sorted(pd.to_datetime(dates))
    start = ordered[0].strftime("%b %Y")
    end = ordered[-1].strftime("%b %Y")
    return start if start == end else f"{start}-{end}"


def dashboard_payload(params):
    monitoring = _read_parquet("model_monitoring")
    drift = _read_parquet("feature_drift_monitoring")
    evaluation = _read_parquet("model_evaluation")
    predictions = _read_parquet("model_predictions")
    feature_store = _read_parquet("feature_store")
    labels = _read_parquet("label_store")
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

    split_summary = {}
    split_source = feature_store if not feature_store.empty else monitoring
    if "data_split" in split_source.columns and "snapshot_date" in split_source.columns:
        split_source = split_source.copy()
        split_source["snapshot_date"] = pd.to_datetime(split_source["snapshot_date"].astype(str))
        for split_name, split_df in split_source.groupby("data_split"):
            split_summary[str(split_name)] = {
                "start": split_df["snapshot_date"].min().strftime("%Y-%m-%d"),
                "end": split_df["snapshot_date"].max().strftime("%Y-%m-%d"),
                "label": _format_month_range(split_df["snapshot_date"]),
                "month_count": int(split_df["snapshot_date"].nunique()),
            }

    development_parts = []
    for split_name in ["train", "validation", "test"]:
        if split_name in split_summary:
            development_parts.append(f"{split_name.title()} {split_summary[split_name]['label']}")
    period_summary = {
        "development_period": ", ".join(development_parts) if development_parts else "-",
        "oot_window": split_summary.get("oot", {}).get("label", "-"),
        "selected_month_label": pd.to_datetime(selected_month).strftime("%b %Y"),
    }

    p0_minimum = None
    if not evaluation.empty and "p0_minimum" in evaluation.columns:
        p0_values = evaluation["p0_minimum"].dropna()
        if not p0_values.empty:
            p0_minimum = _clean_number(p0_values.iloc[0])

    selected_drift_all = drift[
        drift["snapshot_date"].dt.strftime("%Y-%m-%d") == selected_month
    ].sort_values("csi", ascending=False)
    selected_drift = selected_drift_all.head(15)

    prediction_count = 0
    confusion_matrix = {
        "available": False,
        "tn": None,
        "fp": None,
        "fn": None,
        "tp": None,
        "threshold": _clean_number(registry.get("decision_threshold")),
        "precision": None,
        "recall": None,
        "f1_score": None,
        "predicted_default_rate": None,
        "observed_default_rate": None,
    }
    if not predictions.empty:
        predictions["snapshot_date"] = pd.to_datetime(predictions["snapshot_date"])
        prediction_count = int(
            (
                predictions["snapshot_date"].dt.strftime("%Y-%m-%d")
                == selected_month
            ).sum()
        )
        selected_predictions = predictions[
            predictions["snapshot_date"].dt.strftime("%Y-%m-%d") == selected_month
        ]

        if not labels.empty and not selected_predictions.empty:
            labels["snapshot_date"] = pd.to_datetime(labels["snapshot_date"])
            labelled_predictions = selected_predictions.merge(
                labels[["loan_id", "snapshot_date", "label"]],
                on=["loan_id", "snapshot_date"],
                how="inner",
            )
            if not labelled_predictions.empty:
                actual = labelled_predictions["label"].astype(int)
                predicted = labelled_predictions["predicted_label"].astype(int)
                tn = int(((actual == 0) & (predicted == 0)).sum())
                fp = int(((actual == 0) & (predicted == 1)).sum())
                fn = int(((actual == 1) & (predicted == 0)).sum())
                tp = int(((actual == 1) & (predicted == 1)).sum())
                precision = tp / (tp + fp) if (tp + fp) else None
                recall = tp / (tp + fn) if (tp + fn) else None
                f1_score = (
                    2 * precision * recall / (precision + recall)
                    if precision is not None and recall is not None and (precision + recall)
                    else None
                )
                confusion_matrix = {
                    "available": True,
                    "tn": tn,
                    "fp": fp,
                    "fn": fn,
                    "tp": tp,
                    "threshold": _clean_number(selected_predictions["decision_threshold"].iloc[0]),
                    "precision": _clean_number(precision),
                    "recall": _clean_number(recall),
                    "f1_score": _clean_number(f1_score),
                    "predicted_default_rate": _clean_number(predicted.mean()),
                    "observed_default_rate": _clean_number(actual.mean()),
                }

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
        "p1_name": latest.get("p1_metric_name", "pr_auc"),
        "p1_value": _clean_number(latest.get("p1_metric_value")),
        "psi": _clean_number(latest.get("psi")),
        "predicted_default_rate": _clean_number(latest.get("predicted_default_rate")),
        "observed_default_rate": _clean_number(latest.get("observed_default_rate")),
        "significant_feature_count": int((selected_drift_all["drift_status"] == "significant_drift").sum()),
        "watch_feature_count": int((selected_drift_all["drift_status"] == "watch").sum()),
    }

    performance_columns = [
        "snapshot_date",
        "data_split",
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
        "baseline_stddev",
        "current_stddev",
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
        "confusion_matrix": confusion_matrix,
        "split_summary": split_summary,
        "period_summary": period_summary,
        "p0_minimum": p0_minimum,
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
