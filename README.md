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
- `model_selection_charts`: feature-count elbow chart for model-selection governance
- `monitoring_charts`: P0/P1, PSI, CSI and default-rate charts

## Airflow

```bash
docker compose build
docker compose up
```

Open `http://localhost:8080` and sign in with `admin` / `admin`.

Airflow exposes two clear entry points:

- `mle_assignment_2_pipeline`: marker-friendly manual DAG. Clicking
  **Trigger DAG** executes the full pipeline for the latest Assignment 2
  modelling snapshot month (`2024-12-01`). An alternative month can be supplied as
  `{"snapshotdate": "YYYY-MM-DD"}`.
- `mle_assignment_2_monthly_backfill`: paused historical DAG scheduled monthly
  from January 2024 through December 2024 with `catchup=True`. Unpause it to
  replay monthly scoring/monitoring with Airflow's `{{ ds }}` date.

The DAG graph is intentionally expanded in the same style as Lab 5. It shows
source checks, Bronze/Silver/Gold output validation, champion selection,
monthly inference and monitoring outputs as separate Airflow nodes. The
lightweight validation nodes run real shell checks such as `test -f` and
`test -d`; the heavy execution work is handled by:

- `scripts/run_bronze.py`
- `scripts/run_silver.py`
- `scripts/run_gold.py`
- `scripts/ensure_champion.py`
- `scripts/run_inference.py`
- `scripts/run_monitoring.py`

See `docs/airflow_lab5_comparison.md` for the comparison against Lab 5. The
earlier compact DAG is retained for reference at
`docs/airflow_compact_dag_reference.py.txt`.

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
outcome label. Train-window rows remain available as PSI/CSI references, but
their in-sample P0/P1 values are deliberately suppressed; reported performance
starts from validation, continues through test, and can be monitored on OOT
loans when labels are available.

The default Assignment 2 split uses the Jan-Dec 2023 development cohort for
train/validation/test and holds Jan-Dec 2024 out as OOT monitoring data. Within
2023, the split is deterministic and stratified at loan level rather than by
monthly chunks: default and non-default loans are separately ordered by a stable
loan_id hash, then assigned 80% train, 10% validation and 10% test. This keeps
train, validation and test drawn from the same development timeframe, preserves
class distribution, and ensures a single loan cannot appear in more than one
split. Validation is used for hyperparameter and champion selection; test is
kept for post-selection evaluation.

Training automatically evaluates 36 governed candidates: three hyperparameter
variants across each of four model families, crossed with top-40, top-60 and
all-feature budgets. Feature ranking is fitted on train rows only. A challenger
must pass P0 recall and outrank the incumbent on a validation PR-AUC governance
score after small model-complexity and feature-count penalties before
`champion_model.pkl` is replaced. Routine Airflow backfills reuse the current
governed champion so historical monthly scoring remains fast and reproducible.
Controlled challenger evaluation is run through `python main.py`,
`python scripts/train_model.py`, or
`python scripts/ensure_champion.py --force-refresh` when the governance SOP
calls for a model refresh. Inference never selects an
arbitrary file: it loads the governed champion pointer and records its model
version with every prediction.

The feature-budget sweep also writes
`model_selection_charts/feature_elbow.png`, which visualises whether the
validation lift from more features is large enough to justify the added
complexity and monitoring burden.

## Current monitoring finding after the latest rerun

The refreshed Assignment 2 data still contains a deliberate feature-availability
shift. The clickstream file remains populated monthly through December 2024, but
it covers only the original 8,974-customer panel. From July 2024 onward, LMS
loan applications come from a new cohort with reduced clickstream overlap. Gold
therefore median-imputes missing clickstream features for affected application
rows, and PSI/CSI can flag the later-period feature-availability shift,
especially in the 2024 OOT population. Governance treats this as a feature-source
coverage incident before any retraining decision.
