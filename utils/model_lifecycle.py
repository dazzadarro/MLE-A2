import hashlib
import json
import math
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier


ID_COLUMNS = {
    "loan_id",
    "Customer_ID",
    "snapshot_date",
    "loan_start_date",
    "data_split",
    "label",
}

RAW_NUMERIC_COLUMNS = {
    "tenure",
    "loan_amt",
    "Age",
    "Annual_Income",
    "Monthly_Inhand_Salary",
    "Num_Bank_Accounts",
    "Num_Credit_Card",
    "Interest_Rate",
    "Num_of_Loan",
    "Delay_from_due_date",
    "Num_of_Delayed_Payment",
    "Changed_Credit_Limit",
    "Num_Credit_Inquiries",
    "Outstanding_Debt",
    "Credit_Utilization_Ratio",
    "Total_EMI_per_month",
    "Amount_invested_monthly",
    "Monthly_Balance",
    "Credit_History_Months",
    "Num_Loan_Types",
    "Debt_to_Income_Ratio",
    "EMI_to_Monthly_Income_Ratio",
    "Loan_to_Income_Ratio",
    *{f"fe_{i}" for i in range(1, 21)},
}


def training_signature(project_dir):
    """Fingerprint model code and training inputs for controlled refresh detection."""
    project_dir = Path(project_dir)
    digest = hashlib.sha256()
    digest.update(Path(__file__).resolve().read_bytes())
    for root in [
        project_dir / "datamart" / "gold" / "model_feature_store",
        project_dir / "datamart" / "gold" / "label_store",
    ]:
        files = (
            item
            for item in root.rglob("*")
            if item.is_file() and not item.name.endswith(".crc")
        )
        for path in sorted(files):
            digest.update(str(path.relative_to(project_dir)).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _read_parquet(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Required parquet dataset does not exist: {path}")
    return pd.read_parquet(path)


def _write_parquet(df, path, partition_cols=None):
    path = Path(path)
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if partition_cols:
        df.to_parquet(path, index=False, partition_cols=partition_cols)
    else:
        df.to_parquet(path, index=False)


def _model_columns(model_feature_store):
    columns = []
    for column in model_feature_store.columns:
        if column in ID_COLUMNS or column in RAW_NUMERIC_COLUMNS:
            continue
        if column.endswith("_std") or pd.api.types.is_integer_dtype(model_feature_store[column]):
            columns.append(column)
    return sorted(columns)


def _metric_value(function, y_true, values):
    if len(np.unique(y_true)) < 2 and function in {roc_auc_score, average_precision_score}:
        return float("nan")
    return float(function(y_true, values))


def calculate_metrics(y_true, probabilities, threshold):
    predictions = (np.asarray(probabilities) >= threshold).astype(int)
    return {
        "roc_auc": _metric_value(roc_auc_score, y_true, probabilities),
        "pr_auc": _metric_value(average_precision_score, y_true, probabilities),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1_score": float(f1_score(y_true, predictions, zero_division=0)),
    }


def choose_threshold(y_true, probabilities, minimum_recall=0.70):
    candidates = np.linspace(0.10, 0.90, 81)
    scored = []
    for threshold in candidates:
        metrics = calculate_metrics(y_true, probabilities, float(threshold))
        scored.append((float(threshold), metrics))

    feasible = [item for item in scored if item[1]["recall"] >= minimum_recall]
    pool = feasible or scored
    threshold, _ = max(
        pool,
        key=lambda item: (
            item[1]["f1_score"],
            item[1]["precision"],
            item[1]["recall"],
        ),
    )
    return threshold


def _safe_edges(values, bins=10):
    values = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return [-np.inf, np.inf]
    if values.nunique() <= 2:
        return [-np.inf, 0.5, np.inf]
    quantiles = np.unique(values.quantile(np.linspace(0, 1, bins + 1)).to_numpy(dtype=float))
    if len(quantiles) < 3:
        return [-np.inf, float(values.median()), np.inf]
    quantiles[0] = -np.inf
    quantiles[-1] = np.inf
    return quantiles.tolist()


def _distribution(values, edges):
    bucket = pd.cut(pd.Series(values), bins=edges, include_lowest=True, duplicates="drop")
    counts = bucket.value_counts(sort=False, normalize=True)
    return counts.to_numpy(dtype=float).tolist()


def _stability_index(expected, actual, epsilon=1e-6):
    expected = np.clip(np.asarray(expected, dtype=float), epsilon, None)
    actual = np.clip(np.asarray(actual, dtype=float), epsilon, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def _drift_status(value):
    if value < 0.10:
        return "stable"
    if value <= 0.25:
        return "watch"
    return "significant_drift"


def _worst_status(*statuses):
    rank = {"stable": 0, "watch": 1, "significant_drift": 2}
    valid = [status for status in statuses if status in rank]
    return max(valid, key=lambda status: rank[status]) if valid else "stable"


def _json_ready(value):
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def train_and_select_model(project_dir):
    project_dir = Path(project_dir)
    gold_root = project_dir / "datamart" / "gold"
    model_df = _read_parquet(gold_root / "model_feature_store")
    labels = _read_parquet(gold_root / "label_store")[["loan_id", "label"]]
    modelling = model_df.merge(labels, on="loan_id", how="inner")
    feature_columns = _model_columns(modelling)

    train = modelling[modelling["data_split"] == "train"].copy()
    validation = modelling[modelling["data_split"] == "validation"].copy()
    test = modelling[modelling["data_split"] == "test"].copy()
    oot = modelling[modelling["data_split"] == "oot"].copy()
    if train.empty or validation.empty or test.empty or oot.empty:
        raise ValueError("Train, validation, test and OOT rows are required before model training.")

    negative_count = int((train["label"] == 0).sum())
    positive_count = int((train["label"] == 1).sum())
    imbalance_ratio = negative_count / max(positive_count, 1)
    candidates = {
        "logistic_regression": LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=42,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            learning_rate=0.08,
            max_iter=180,
            max_leaf_nodes=24,
            l2_regularization=0.1,
            random_state=42,
        ),
        "xgboost": XGBClassifier(
            n_estimators=250,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            scale_pos_weight=imbalance_ratio,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
            use_label_encoder=False,
        ),
    }

    rows = []
    fitted = {}
    for model_name, model in candidates.items():
        if model_name == "hist_gradient_boosting":
            sample_weight = np.where(train["label"].to_numpy() == 1, imbalance_ratio, 1.0)
            model.fit(train[feature_columns], train["label"], sample_weight=sample_weight)
        else:
            model.fit(train[feature_columns], train["label"])
        validation_probability = model.predict_proba(validation[feature_columns])[:, 1]
        threshold = choose_threshold(validation["label"].to_numpy(), validation_probability)
        validation_metrics = calculate_metrics(validation["label"], validation_probability, threshold)
        test_probability = model.predict_proba(test[feature_columns])[:, 1]
        test_metrics = calculate_metrics(test["label"], test_probability, threshold)
        fitted[model_name] = (model, threshold)

        oot_probability = model.predict_proba(oot[feature_columns])[:, 1]
        oot_metrics = calculate_metrics(oot["label"], oot_probability, threshold)
        for dataset_name, metrics in [
            ("validation", validation_metrics),
            ("test", test_metrics),
            ("oot", oot_metrics),
        ]:
            rows.append(
                {
                    "model_name": model_name,
                    "dataset": dataset_name,
                    "decision_threshold": threshold,
                    "p0_metric_name": "recall",
                    "p0_metric_value": metrics["recall"],
                    "p0_minimum": 0.70,
                    "p0_pass": metrics["recall"] >= 0.70,
                    "p1_metric_name": "pr_auc",
                    "p1_metric_value": metrics["pr_auc"],
                    "p2_metric_name": "precision",
                    "p2_metric_value": metrics["precision"],
                    "p3_metric_name": "roc_auc",
                    "p3_metric_value": metrics["roc_auc"],
                    "used_for_champion_selection": dataset_name == "validation",
                    **metrics,
                }
            )

    evaluation = pd.DataFrame(rows)
    eligible_validation = evaluation[
        (evaluation["dataset"] == "validation") & evaluation["p0_pass"]
    ]
    if eligible_validation.empty:
        raise ValueError("No candidate model passed the mandatory P0 validation recall floor.")

    validation_results = eligible_validation.sort_values(
        ["p0_pass", "p1_metric_value", "p0_metric_value", "p2_metric_value"],
        ascending=False,
    )
    champion_name = validation_results.iloc[0]["model_name"]
    champion_model, champion_threshold = fitted[champion_name]
    champion_validation = validation_results.iloc[0]
    model_version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    training_probabilities = champion_model.predict_proba(train[feature_columns])[:, 1]
    score_edges = _safe_edges(training_probabilities)
    score_distribution = _distribution(training_probabilities, score_edges)
    feature_baselines = {}
    for feature_name in feature_columns:
        edges = _safe_edges(train[feature_name])
        feature_baselines[feature_name] = {
            "edges": edges,
            "distribution": _distribution(train[feature_name], edges),
            "mean": float(pd.to_numeric(train[feature_name], errors="coerce").mean()),
            "stddev": float(pd.to_numeric(train[feature_name], errors="coerce").std(ddof=0)),
        }

    artefact = {
        "model_name": champion_name,
        "model_version": model_version,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": champion_model,
        "decision_threshold": float(champion_threshold),
        "feature_columns": feature_columns,
        "p0_metric_name": "recall",
        "p1_metric_name": "pr_auc",
        "p2_metric_name": "precision",
        "p3_metric_name": "roc_auc",
        "performance_baseline": {
            "recall": float(champion_validation["recall"]),
            "pr_auc": float(champion_validation["pr_auc"]),
            "precision": float(champion_validation["precision"]),
            "roc_auc": float(champion_validation["roc_auc"]),
        },
        "train_default_rate": float(train["label"].mean()),
        "score_baseline": {
            "edges": score_edges,
            "distribution": score_distribution,
        },
        "feature_baselines": feature_baselines,
    }

    model_bank = project_dir / "model_bank"
    model_bank.mkdir(parents=True, exist_ok=True)
    versioned_path = model_bank / f"{champion_name}_{model_version}.pkl"
    with versioned_path.open("wb") as file:
        pickle.dump(artefact, file)

    champion_path = model_bank / "champion_model.pkl"
    incumbent = None
    if champion_path.exists():
        with champion_path.open("rb") as file:
            incumbent = pickle.load(file)

    challenger_rank = (
        float(champion_validation["recall"]) >= 0.70,
        float(champion_validation["pr_auc"]),
        float(champion_validation["recall"]),
        float(champion_validation["precision"]),
    )
    incumbent_rank = None
    incumbent_current_metrics = None
    if incumbent:
        incumbent_columns = incumbent.get("feature_columns", [])
        if incumbent_columns == feature_columns:
            incumbent_probability = incumbent["model"].predict_proba(
                validation[incumbent_columns]
            )[:, 1]
            incumbent_current_metrics = calculate_metrics(
                validation["label"],
                incumbent_probability,
                incumbent["decision_threshold"],
            )
            incumbent_rank = (
                float(incumbent_current_metrics["recall"]) >= 0.70,
                float(incumbent_current_metrics["pr_auc"]),
                float(incumbent_current_metrics["recall"]),
                float(incumbent_current_metrics["precision"]),
            )
        else:
            # A changed feature contract requires explicit review rather than
            # comparing metrics produced from incompatible feature sets.
            incumbent_rank = (True, float("inf"), float("inf"), float("inf"))

    promoted = incumbent is None or challenger_rank > incumbent_rank
    if promoted:
        with champion_path.open("wb") as file:
            pickle.dump(artefact, file)
        deployed = artefact
        promotion_reason = (
            "Initial champion created."
            if incumbent is None
            else "Challenger passed P0 and ranked above the incumbent on validation metrics."
        )
    else:
        deployed = incumbent
        promotion_reason = (
            "Challenger retained as a versioned artefact; incumbent remained superior "
            "under the P0 then P1 promotion rule."
        )

    registry = {
        "champion_model": deployed["model_name"],
        "model_version": deployed["model_version"],
        "artefact_path": (
            versioned_path.name
            if promoted
            else f"{deployed['model_name']}_{deployed['model_version']}.pkl"
        ),
        "decision_threshold": float(deployed["decision_threshold"]),
        "latest_challenger_model": champion_name,
        "latest_challenger_version": model_version,
        "latest_challenger_promoted": promoted,
        "promotion_reason": promotion_reason,
        "incumbent_current_validation": incumbent_current_metrics,
        "training_signature": training_signature(project_dir),
        "p0_metric": "recall",
        "p1_metric": "pr_auc",
        "p2_metric": "precision",
        "p3_metric": "roc_auc",
        "selection_rule": (
            "Pass the validation recall floor of 0.70, then maximise PR-AUC; "
            "use recall and precision as tie-breakers. OOT is reporting-only."
        ),
    }
    (model_bank / "model_registry.json").write_text(
        json.dumps(_json_ready(registry), indent=2),
        encoding="utf-8",
    )
    _write_parquet(evaluation, gold_root / "model_evaluation")
    print(
        f"Champion model: {deployed['model_name']} ({deployed['model_version']}); "
        f"challenger promoted={promoted}"
    )
    return deployed


def load_champion(project_dir):
    path = Path(project_dir) / "model_bank" / "champion_model.pkl"
    if not path.exists():
        raise FileNotFoundError("Champion model not found. Run model training first.")
    with path.open("rb") as file:
        return pickle.load(file)


def run_monthly_inference(project_dir, snapshot_date=None):
    project_dir = Path(project_dir)
    gold_root = project_dir / "datamart" / "gold"
    model_df = _read_parquet(gold_root / "model_feature_store")
    artefact = load_champion(project_dir)
    model_df["snapshot_date"] = pd.to_datetime(model_df["snapshot_date"]).dt.date

    if snapshot_date:
        target_date = pd.to_datetime(snapshot_date).date()
        model_df = model_df[model_df["snapshot_date"] == target_date]
    if model_df.empty:
        raise ValueError(f"No feature rows available for snapshot_date={snapshot_date}")

    probabilities = artefact["model"].predict_proba(model_df[artefact["feature_columns"]])[:, 1]
    predictions = model_df[["loan_id", "Customer_ID", "snapshot_date", "data_split"]].copy()
    predictions["model_name"] = artefact["model_name"]
    predictions["model_version"] = artefact["model_version"]
    predictions["default_probability"] = probabilities
    predictions["decision_threshold"] = artefact["decision_threshold"]
    predictions["predicted_label"] = (
        predictions["default_probability"] >= artefact["decision_threshold"]
    ).astype(int)
    predictions["prediction_created_at_utc"] = datetime.now(timezone.utc).isoformat()

    output = gold_root / "model_predictions"
    if snapshot_date and output.exists():
        existing = _read_parquet(output)
        existing["snapshot_date"] = pd.to_datetime(existing["snapshot_date"]).dt.date
        predictions = pd.concat(
            [existing[existing["snapshot_date"] != pd.to_datetime(snapshot_date).date()], predictions],
            ignore_index=True,
        )
    _write_parquet(predictions, output, ["snapshot_date"])
    print(f"Gold predictions written: {output}")
    return predictions


def calculate_monthly_monitoring(project_dir, snapshot_date=None):
    project_dir = Path(project_dir)
    gold_root = project_dir / "datamart" / "gold"
    predictions = _read_parquet(gold_root / "model_predictions")
    labels = _read_parquet(gold_root / "label_store")[["loan_id", "label", "label_observation_date"]]
    model_df = _read_parquet(gold_root / "model_feature_store")
    artefact = load_champion(project_dir)

    predictions["snapshot_date"] = pd.to_datetime(predictions["snapshot_date"]).dt.date
    model_df["snapshot_date"] = pd.to_datetime(model_df["snapshot_date"]).dt.date
    if snapshot_date:
        target_date = pd.to_datetime(snapshot_date).date()
        predictions = predictions[predictions["snapshot_date"] == target_date]
        model_df = model_df[model_df["snapshot_date"] == target_date]

    labelled = predictions.merge(labels, on="loan_id", how="left")
    monitoring_rows = []
    feature_drift_rows = []
    for month, month_predictions in predictions.groupby("snapshot_date"):
        month_labelled = labelled[labelled["snapshot_date"] == month].dropna(subset=["label"])
        data_split = str(month_predictions["data_split"].iloc[0])
        probability = month_predictions["default_probability"].to_numpy()
        score_actual = _distribution(probability, artefact["score_baseline"]["edges"])
        psi = _stability_index(artefact["score_baseline"]["distribution"], score_actual)

        metrics = {
            "roc_auc": float("nan"),
            "pr_auc": float("nan"),
            "precision": float("nan"),
            "recall": float("nan"),
            "f1_score": float("nan"),
        }
        observation_status = "in_sample_reference" if data_split == "train" else "labels_pending"
        performance_drift_status = observation_status
        # Training months are useful PSI/CSI baselines, but their in-sample
        # performance is not presented as evidence of generalisation.
        if (
            data_split != "train"
            and not month_labelled.empty
            and month_labelled["label"].nunique() >= 2
        ):
            metrics = calculate_metrics(
                month_labelled["label"].astype(int),
                month_labelled["default_probability"],
                artefact["decision_threshold"],
            )
            observation_status = "observed"
            baseline = artefact["performance_baseline"]
            if metrics["recall"] < 0.70 or metrics["pr_auc"] < baseline["pr_auc"] - 0.10:
                performance_drift_status = "significant_drift"
            elif (
                metrics["recall"] < baseline["recall"] - 0.05
                or metrics["pr_auc"] < baseline["pr_auc"] - 0.05
            ):
                performance_drift_status = "watch"
            else:
                performance_drift_status = "stable"

        data_drift_status = _drift_status(psi)
        combined_status = (
            data_drift_status
            if performance_drift_status in {"labels_pending", "in_sample_reference"}
            else _worst_status(data_drift_status, performance_drift_status)
        )

        monitoring_rows.append(
            {
                "snapshot_date": month,
                "model_name": artefact["model_name"],
                "model_version": artefact["model_version"],
                "data_split": data_split,
                "observation_status": observation_status,
                "record_count": len(month_predictions),
                "labelled_record_count": len(month_labelled),
                "p0_metric_name": "recall",
                "p0_metric_value": metrics["recall"],
                "p1_metric_name": "pr_auc",
                "p1_metric_value": metrics["pr_auc"],
                "p2_metric_name": "precision",
                "p2_metric_value": metrics["precision"],
                "p3_metric_name": "roc_auc",
                "p3_metric_value": metrics["roc_auc"],
                **metrics,
                "predicted_default_rate": float(month_predictions["predicted_label"].mean()),
                "observed_default_rate": (
                    float(month_labelled["label"].mean()) if not month_labelled.empty else float("nan")
                ),
                "training_default_rate": artefact["train_default_rate"],
                "default_rate_shift": (
                    float(month_labelled["label"].mean() - artefact["train_default_rate"])
                    if not month_labelled.empty
                    else float("nan")
                ),
                "psi": psi,
                "data_drift_status": data_drift_status,
                "performance_drift_status": performance_drift_status,
                "monitoring_status": combined_status,
            }
        )

        month_features = model_df[model_df["snapshot_date"] == month]
        for feature_name, baseline in artefact["feature_baselines"].items():
            current_distribution = _distribution(month_features[feature_name], baseline["edges"])
            csi = _stability_index(baseline["distribution"], current_distribution)
            current_values = pd.to_numeric(month_features[feature_name], errors="coerce")
            feature_drift_rows.append(
                {
                    "snapshot_date": month,
                    "model_name": artefact["model_name"],
                    "model_version": artefact["model_version"],
                    "feature_name": feature_name,
                    "csi": csi,
                    "drift_status": _drift_status(csi),
                    "baseline_mean": baseline["mean"],
                    "current_mean": float(current_values.mean()),
                    "baseline_stddev": baseline["stddev"],
                    "current_stddev": float(current_values.std(ddof=0)),
                }
            )

    monitoring = pd.DataFrame(monitoring_rows)
    feature_drift = pd.DataFrame(feature_drift_rows)
    if snapshot_date:
        monitoring_path = gold_root / "model_monitoring"
        drift_path = gold_root / "feature_drift_monitoring"
        target_date = pd.to_datetime(snapshot_date).date()
        if monitoring_path.exists():
            existing = _read_parquet(monitoring_path)
            existing["snapshot_date"] = pd.to_datetime(existing["snapshot_date"]).dt.date
            monitoring = pd.concat(
                [existing[existing["snapshot_date"] != target_date], monitoring],
                ignore_index=True,
            )
        if drift_path.exists():
            existing = _read_parquet(drift_path)
            existing["snapshot_date"] = pd.to_datetime(existing["snapshot_date"]).dt.date
            feature_drift = pd.concat(
                [existing[existing["snapshot_date"] != target_date], feature_drift],
                ignore_index=True,
            )
    _write_parquet(monitoring, gold_root / "model_monitoring")
    _write_parquet(feature_drift, gold_root / "feature_drift_monitoring")
    create_monitoring_charts(project_dir, monitoring, feature_drift)
    print(f"Gold monitoring written: {gold_root / 'model_monitoring'}")
    return monitoring, feature_drift


def create_monitoring_charts(project_dir, monitoring, feature_drift):
    chart_root = Path(project_dir) / "monitoring_charts"
    chart_root.mkdir(parents=True, exist_ok=True)
    monitoring = monitoring.sort_values("snapshot_date").copy()
    x = pd.to_datetime(monitoring["snapshot_date"])

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(x, monitoring["recall"], marker="o", label="P0 Recall")
    ax.plot(x, monitoring["pr_auc"], marker="o", label="P1 PR-AUC")
    ax.plot(x, monitoring["precision"], marker="o", label="Precision", alpha=0.8)
    ax.set_ylim(0, 1.05)
    ax.set_title("Monthly model performance")
    ax.set_ylabel("Metric")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(chart_root / "performance_trend.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(x, monitoring["psi"], marker="o", color="#D89000", label="PSI")
    ax.axhline(0.10, color="#D9A400", linestyle="--", label="Watch threshold")
    ax.axhline(0.25, color="#C33C30", linestyle="--", label="Significant drift")
    ax.set_title("Prediction population stability")
    ax.set_ylabel("PSI")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(chart_root / "psi_trend.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(x, monitoring["predicted_default_rate"], marker="o", label="Predicted")
    ax.plot(x, monitoring["observed_default_rate"], marker="o", label="Observed")
    ax.set_title("Predicted versus observed default rate")
    ax.set_ylabel("Default rate")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(chart_root / "default_rate_trend.png", dpi=160)
    plt.close(fig)

    if not feature_drift.empty:
        ranked = (
            feature_drift.groupby("feature_name", as_index=False)["csi"]
            .max()
            .sort_values("csi", ascending=False)
            .head(15)
            .sort_values("csi")
        )
        fig, ax = plt.subplots(figsize=(10, 6))
        colors = ["#C33C30" if value > 0.25 else "#D9A400" if value >= 0.10 else "#4F8A5B" for value in ranked["csi"]]
        ax.barh(ranked["feature_name"], ranked["csi"], color=colors)
        ax.axvline(0.10, color="#D9A400", linestyle="--")
        ax.axvline(0.25, color="#C33C30", linestyle="--")
        ax.set_title("Top feature drift indicators")
        ax.set_xlabel("Maximum monthly CSI")
        fig.tight_layout()
        fig.savefig(chart_root / "csi_top_features.png", dpi=160)
        plt.close(fig)
