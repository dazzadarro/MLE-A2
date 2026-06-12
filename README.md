# CS611 Assignment 2: Loan Default MLE Pipeline

This project extends the Assignment 1 Bronze-Silver-Gold loan-default pipeline
with model training, champion selection, monthly inference and model monitoring.

## Run the complete pipeline

```bash
python main.py
```

The command creates:

- `datamart/bronze`: four raw-like Parquet source tables
- `datamart/silver`: four cleaned Parquet source tables and cleaning audit CSV
- `datamart/gold/feature_store`
- `datamart/gold/label_store`
- `datamart/gold/model_feature_store`
- `datamart/gold/model_evaluation`
- `datamart/gold/model_predictions`
- `datamart/gold/model_monitoring`
- `datamart/gold/feature_drift_monitoring`
- `model_bank`: versioned and champion model artefacts
- `monitoring_charts`: P0/P1, PSI, CSI and default-rate charts

## Airflow

```bash
docker compose build
docker compose up
```

Open `http://localhost:8082` and sign in with `admin` / `admin`.

The DAG is scheduled monthly and uses `catchup=True` so historical snapshot
months can be backfilled. Each task receives Airflow's `{{ ds }}` date.

## Monitoring dashboard

The project includes a small monitoring-only web dashboard which reads the
actual Gold model-monitoring and feature-drift Parquet tables.

When Docker Compose is running, open:

```text
http://localhost:8050
```

The dashboard displays:

- P0 recall and P1 PR-AUC over time
- PSI with the 0.10 and 0.25 governance thresholds
- feature-level CSI and drift status
- predicted versus observed default rates
- champion model version and label-maturity status

`render.yaml` is included for a later Render deployment. The dashboard is part
of this Assignment 2 repository and uses `dashboard/Dockerfile`.

The monitoring-focused layout was informed by the earlier group-project
dashboard at
`https://smu-cs611-mle-groupproject-frauddetection.onrender.com/`, while this
implementation is a separate, simpler dashboard backed by Assignment 2 output.

## Monitoring definitions

- **P0: Recall**, with a validation floor of 0.70, because failing to identify
  a genuine defaulter is the main business risk.
- **P1: PR-AUC** because the default class is the minority class and PR-AUC
  evaluates positive-class ranking without being inflated by true negatives.
- **P2: Precision** to monitor how efficiently predicted defaults are targeted.
- **P3: ROC-AUC** as a threshold-independent overall ranking measure.
- Accuracy is reported only as supplementary context because predicting the
  majority class can make accuracy appear acceptable while missing defaulters.
- PSI monitors movement in the overall prediction-score population.
- CSI monitors drift for individual model features.
- PSI/CSI below 0.10 is stable, 0.10-0.25 is watch, and above 0.25 is
  significant drift requiring investigation.

Performance monitoring is reported only when the future MOB 6 label has
matured. Drift monitoring can run immediately because it does not require the
outcome label.
