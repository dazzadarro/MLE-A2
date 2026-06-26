# Assignment 2 Airflow Documentation

This document explains how the Assignment 2 Airflow pipeline is organised, how
to read the DAG graph, what each task does, and how the monthly backfill is
intended to work.

## 1. Why Airflow Is Used

Assignment 2 requires an end-to-end ML pipeline that can:

- train and select a model;
- store the selected model artefact;
- retrieve the selected model for inference;
- create prediction outputs across time;
- monitor model performance and stability across time;
- support backfilling, similar to Lab 5.

Airflow is used as the orchestration layer. It does not replace the modelling or
PySpark code. It coordinates the order in which the scripts run and makes the
pipeline visible through the DAG graph, Grid view and Calendar view.

## 2. Airflow Entry Points

The Airflow DAG file is:

```text
dags/mle_assignment_2_dag.py
```

It defines two DAGs.

| DAG | Purpose | Schedule | Main use |
|---|---|---|---|
| `mle_assignment_2_pipeline` | Marker-friendly full pipeline run | Manual only | Run the latest Assignment 2 month, default `2024-12-01` |
| `mle_assignment_2_monthly_backfill` | Historical monthly replay | `0 0 1 * *` | Backfill Jan-Dec 2024 one month at a time |

The manual DAG is the safer one for grading because the marker can click
Trigger DAG and see the pipeline run once.

The monthly backfill DAG is the one that demonstrates the Lab 5 backfill idea.
It has `catchup=True`, so Airflow can create one DAG run per historical monthly
execution date.

## 3. How To Open Airflow

From the project folder:

```bash
docker compose build
docker compose up
```

Then open:

```text
http://localhost:8080
```

Login:

```text
username: admin
password: admin
```

The monitoring dashboard is separate from Airflow:

```text
http://localhost:8050
```

## 4. Important Airflow Concepts Used

### DAG

A DAG is the pipeline definition. It specifies which tasks exist and what order
they must run in.

### Task

A task is one box in the Airflow graph.

In the current version, every graph box is a `BashOperator`, but there are two
different kinds of Bash task:

| Airflow task type | Meaning in this project |
|---|---|
| Heavy script Bash task | Runs one of the Python pipeline scripts |
| Lightweight check Bash task | Runs `test -f`, `test -d` or `echo` to verify a file/folder or mark a stage boundary |

This keeps the Lab 5 visual style but avoids a graph that looks like placeholder
tasks only. The output checkpoints are now real shell checks.

### Snapshot Date

The `snapshotdate` is the month being processed.

For the manual DAG:

```text
{{ dag_run.conf.get('snapshotdate', '2024-12-01') }}
```

This means:

- if no configuration is supplied, run `2024-12-01`;
- if a user supplies `{"snapshotdate": "2024-07-01"}`, run July 2024.

For the backfill DAG:

```text
{{ ds }}
```

This means Airflow passes the execution date as the snapshot month.

## 5. High-Level Pipeline Flow

The DAG follows this sequence:

```text
source checks
-> Bronze tables
-> Silver tables
-> Gold feature and label stores
-> Champion model selection or reuse
-> Monthly inference
-> Monthly monitoring
-> completed
```

The core idea is:

1. Build the data stores.
2. Ensure a governed champion model exists.
3. Score the selected snapshot month.
4. Monitor the model for that snapshot month.

## 6. Detailed DAG Walkthrough

### Stage 1: Source Readiness

Visible Airflow tasks:

| Task | Type | Meaning |
|---|---|---|
| `start` | BashOperator | Echo start marker |
| `dep_check_attr` | BashOperator | Checks `data/features_attributes.csv` exists |
| `dep_check_fin` | BashOperator | Checks `data/features_financials.csv` exists |
| `dep_check_click` | BashOperator | Checks `data/feature_clickstream.csv` exists |
| `dep_check_lms` | BashOperator | Checks `data/lms_loan_daily.csv` exists |
| `source_ready` | BashOperator | Echo source-ready marker |

These source-check tasks are real file-existence checks. Deeper schema and
business validation remains inside the Bronze/Silver PySpark processing code.

### Stage 2: Bronze Tables

Visible Airflow tasks:

| Task | Type | Script or output |
|---|---|---|
| `run_bronze_tables` | BashOperator | Runs `scripts/run_bronze.py` |
| `bronze_attr` | BashOperator | Checks `datamart/bronze/attributes` exists |
| `bronze_fin` | BashOperator | Checks `datamart/bronze/financials` exists |
| `bronze_click` | BashOperator | Checks `datamart/bronze/clickstream` exists |
| `bronze_lms` | BashOperator | Checks `datamart/bronze/lms` exists |
| `bronze_done` | BashOperator | Echo Bronze-complete marker |

Command run by Airflow:

```bash
cd /opt/airflow/project && PYTHONPATH=. python scripts/run_bronze.py --snapshotdate "{{ snapshotdate }}"
```

Bronze reads the raw CSVs and writes raw-like Parquet tables partitioned by
`snapshot_date`.

If the Bronze outputs already exist, the script skips rebuild to keep Airflow
backfills faster.

### Stage 3: Silver Tables

Visible Airflow tasks:

| Task | Type | Script or output |
|---|---|---|
| `run_silver_tables` | BashOperator | Runs `scripts/run_silver.py` |
| `silver_attr` | BashOperator | Checks `datamart/silver/attributes` exists |
| `silver_fin` | BashOperator | Checks `datamart/silver/financials` exists |
| `silver_click` | BashOperator | Checks `datamart/silver/clickstream` exists |
| `silver_lms` | BashOperator | Checks `datamart/silver/lms` exists |
| `silver_done` | BashOperator | Echo Silver-complete marker |

Silver cleans and conforms the source-domain tables. It handles things like:

- data type casting;
- invalid numeric values;
- invalid placeholders;
- category cleanup;
- date casting;
- basic source-domain validation.

Silver does not train models and does not create final ML outputs.

### Stage 4: Gold Feature And Label Stores

Visible Airflow tasks:

| Task | Type | Script or output |
|---|---|---|
| `run_gold_stores` | BashOperator | Runs `scripts/run_gold.py` |
| `gold_feature_store` | BashOperator | Checks `datamart/gold/feature_store` exists |
| `gold_label_store` | BashOperator | Checks `datamart/gold/label_store` exists |
| `gold_model_feature_store` | BashOperator | Checks `datamart/gold/model_feature_store` exists |
| `gold_preprocess_metadata` | BashOperator | Checks `datamart/gold/preprocessing_metadata` exists |
| `gold_done` | BashOperator | Echo Gold-complete marker |

Gold creates the ML-ready stores:

- `feature_store`: human-readable engineered features;
- `label_store`: future outcome label;
- `model_feature_store`: encoded/scaled model-ready features;
- `preprocessing_metadata`: train-only preprocessing values.

Gold also assigns the modelling split:

| Period | Split |
|---|---|
| Jan-Dec 2023 loans | Deterministic loan-level 80% train / 10% validation / 10% test, stratified by label |
| Jan-Dec 2024 loans | OOT monitoring and monthly backfill only |

The 2024 OOT months are not used to select the model.

## 7. Model Selection Stage

Visible Airflow tasks:

| Task | Type | Script or output |
|---|---|---|
| `model_automl_start` | BashOperator | Echo model-governance start marker |
| `train_or_load_champion` | BashOperator | Runs `scripts/ensure_champion.py` |
| `model_bank` | BashOperator | Checks `model_bank/champion_model.pkl` exists |
| `model_evaluation` | BashOperator | Checks `datamart/gold/model_evaluation` exists |
| `model_automl_completed` | BashOperator | Echo champion-complete marker |

The champion script checks whether a governed champion already exists:

```text
model_bank/champion_model.pkl
model_bank/model_registry.json
```

If both exist, Airflow reuses the champion.

If the champion is missing, or if a controlled refresh is explicitly requested,
the project evaluates challengers and selects a champion.

The governed selection logic is:

1. Candidate model must pass P0 recall >= 0.70 on validation.
2. Eligible models are ranked primarily by validation PR-AUC.
3. Small penalties are applied for model complexity and feature count.
4. The winning model is written as `champion_model.pkl`.
5. Metadata is written to `model_registry.json`.

Routine backfills do not retrain the model every month. They reuse the governed
champion. This is intentional: the backfill should answer what the approved
model would have predicted in each month.

## 8. Monthly Inference Stage

Visible Airflow tasks:

| Task | Type | Script or output |
|---|---|---|
| `model_inference_start` | BashOperator | Echo inference-start marker |
| `run_monthly_inference` | BashOperator | Runs `scripts/run_inference.py` |
| `gold_predictions` | BashOperator | Checks `datamart/gold/model_predictions` exists |
| `model_inference_completed` | BashOperator | Echo inference-complete marker |

Command run by Airflow:

```bash
cd /opt/airflow/project && PYTHONPATH=. python scripts/run_inference.py --snapshotdate "{{ snapshotdate }}"
```

The inference script:

1. loads the governed champion model;
2. reads `datamart/gold/model_feature_store`;
3. filters to the requested `snapshot_date`;
4. generates predicted probabilities and predicted labels;
5. writes predictions to `datamart/gold/model_predictions`.

The prediction output is partitioned by `snapshot_date`, so each monthly run is
kept separately.

## 9. Monthly Monitoring Stage

Visible Airflow tasks:

| Task | Type | Script or output |
|---|---|---|
| `model_monitor_start` | BashOperator | Echo monitoring-start marker |
| `run_model_monitor` | BashOperator | Runs `scripts/run_monitoring.py` |
| `gold_model_monitoring` | BashOperator | Checks `datamart/gold/model_monitoring` exists |
| `gold_feature_drift` | BashOperator | Checks `datamart/gold/feature_drift_monitoring` exists |
| `monitoring_charts` | BashOperator | Checks `monitoring_charts/` exists |
| `model_monitoring_completed` | BashOperator | Echo monitoring-complete marker |
| `completed` | BashOperator | Echo final-complete marker |

Command run by Airflow:

```bash
cd /opt/airflow/project && PYTHONPATH=. python scripts/run_monitoring.py --snapshotdate "{{ snapshotdate }}"
```

The monitoring script writes:

| Output | Meaning |
|---|---|
| `datamart/gold/model_monitoring` | Monthly P0/P1 performance, PSI, predicted default rate, observed default rate |
| `datamart/gold/feature_drift_monitoring` | Feature-level CSI drift results |
| `monitoring_charts/performance_trend.png` | P0/P1 trend |
| `monitoring_charts/psi_trend.png` | PSI trend |
| `monitoring_charts/csi_top_features.png` | Highest CSI features |
| `monitoring_charts/default_rate_trend.png` | Predicted versus observed default rate |

Monitoring has two parts:

| Monitoring type | Metric | Can run immediately? | Why |
|---|---|---|---|
| Data drift | PSI and CSI | Yes | Uses feature and score distributions |
| Performance drift | Recall, PR-AUC, precision | Only after labels mature | Requires future repayment outcome |

## 10. Backfill Design

The backfill DAG is:

```text
mle_assignment_2_monthly_backfill
```

Its schedule is:

```text
0 0 1 * *
```

This means first day of every month at midnight.

The DAG is configured with:

```text
start_date = 2024-01-01
end_date = 2024-12-01
catchup = True
```

This creates one historical Airflow run per month from Jan 2024 to Dec 2024.

Each backfill run passes its execution date as the `snapshotdate`. For example:

| Airflow execution date | Snapshot scored |
|---|---|
| `2024-01-01` | Jan 2024 |
| `2024-02-01` | Feb 2024 |
| `2024-07-01` | Jul 2024 |
| `2024-12-01` | Dec 2024 |

This lets the project simulate monthly production scoring.

## 11. Backfill Without Data Leakage

Backfill must not let future data influence earlier model decisions.

This project controls leakage as follows:

| Leakage risk | Control |
|---|---|
| Future months affect model selection | Model development is fixed to 2023 |
| Future rows affect preprocessing | Preprocessing is fitted on train rows only |
| Repayment outcome leaks into features | LMS repayment fields are excluded from model features |
| Backfill retrains using later months | Monthly backfill reuses the frozen champion |
| Monitoring reads labels too early | Performance metrics are reported only when labels exist |
| Later runs overwrite earlier months | Outputs are partitioned by `snapshot_date` |

The key interpretation is:

```text
Each 2024 backfill run asks:
"What would the approved 2023-developed model have predicted for this month?"
```

It does not ask:

```text
"What model would we build after already seeing all 2024 outcomes?"
```

## 12. How To Read The Airflow UI

### Graph View

Use Graph View to explain the pipeline structure. It shows the dependency flow:

```text
source checks -> Bronze -> Silver -> Gold -> model -> inference -> monitoring
```

In the graph:

- green boxes mean successful tasks;
- arrows show task dependencies;
- script boxes run Python pipeline scripts;
- check boxes run real shell checks against files or folders;
- echo boxes mark stage boundaries.

### Grid View

Use Grid View to confirm whether each monthly DAG run succeeded. This is the
best view for checking backfill completion.

### Calendar View

Use Calendar View to show that the DAG runs occur on monthly dates. This is the
best screenshot for proving backfill across time.

### Task Duration

Use Task Duration to see which task took longest. Longer months can happen due
to retries, Docker resource contention, Spark startup cost, or reruns.

### Logs

Click a task, then click Logs to see the exact script output. This is how to
debug failed tasks.

## 13. Why Some BashOperator Boxes Are Lightweight Checks

The graph has many boxes because the assignment and Lab 5 expect a visible ML
pipeline, not just one large Python script.

However, creating one separate Python script for every single output checkpoint
would add unnecessary complexity and make the backfill much slower. Therefore,
the DAG uses:

- heavy `BashOperator` tasks for real processing scripts;
- lightweight `BashOperator` tasks for source/output checks and stage markers.

This is aligned with Lab 5's visible pipeline style, but stronger: the
checkpoint-style boxes now execute real shell commands instead of being pure
placeholders.

The important point is that the major transformations are still concentrated in
the tested Python scripts, while the surrounding Airflow nodes verify that the
expected files and folders exist.

## 14. Scripts Used By Airflow

| Script | Used by task | Responsibility |
|---|---|---|
| `scripts/run_bronze.py` | `run_bronze_tables` | Create Bronze Parquet source-domain tables |
| `scripts/run_silver.py` | `run_silver_tables` | Create cleaned Silver tables |
| `scripts/run_gold.py` | `run_gold_stores` | Create Gold feature, label and model feature stores |
| `scripts/ensure_champion.py` | `train_or_load_champion` | Reuse or train/select champion model |
| `scripts/run_inference.py` | `run_monthly_inference` | Score one snapshot month |
| `scripts/run_monitoring.py` | `run_model_monitor` | Create monthly performance and stability monitoring |

## 15. Outputs Created For Assignment Marking

The Airflow DAG creates or refreshes these important outputs:

```text
datamart/bronze/attributes
datamart/bronze/financials
datamart/bronze/clickstream
datamart/bronze/lms

datamart/silver/attributes
datamart/silver/financials
datamart/silver/clickstream
datamart/silver/lms

datamart/gold/feature_store
datamart/gold/label_store
datamart/gold/model_feature_store
datamart/gold/model_evaluation
datamart/gold/model_predictions
datamart/gold/model_monitoring
datamart/gold/feature_drift_monitoring

model_bank/champion_model.pkl
model_bank/model_registry.json

monitoring_charts/
model_selection_charts/
```

These outputs map directly to the Assignment 2 requirements:

| Assignment requirement | Output evidence |
|---|---|
| Store model artefacts | `model_bank/` |
| Retrieve best model for inference | `champion_model.pkl` loaded by inference |
| Store predictions as Gold table | `datamart/gold/model_predictions` |
| Store monitoring as Gold table | `datamart/gold/model_monitoring`, `feature_drift_monitoring` |
| Visualise monitoring | `monitoring_charts/` and dashboard |
| Backfill across time | `mle_assignment_2_monthly_backfill` |

## 16. How To Trigger The Manual DAG

1. Open Airflow.
2. Click `mle_assignment_2_pipeline`.
3. Click Trigger DAG.
4. Leave configuration blank to run the default month:

```text
2024-12-01
```

Optional configuration:

```json
{"snapshotdate": "2024-07-01"}
```

This manually runs July 2024.

## 17. How To Run The Backfill DAG

1. Open Airflow.
2. Find `mle_assignment_2_monthly_backfill`.
3. Unpause the DAG.
4. Airflow will create scheduled runs for the historical monthly dates.
5. Use Grid View or Calendar View to confirm the months succeeded.

The backfill can take materially longer than a single manual run because it
replays twelve monthly runs.

## 18. Why The Backfill Can Take A Long Time

The dataset is not huge, but the Docker/Airflow/Spark stack adds overhead:

- Airflow starts each task separately;
- PySpark has startup overhead;
- each monthly run may launch several scripts;
- Docker Desktop shares limited CPU and memory;
- the backfill DAG repeats the monthly inference and monitoring workflow for
  every month.

This is normal for a teaching Airflow setup. For marking, the manual DAG is the
fastest proof that the pipeline works. The monthly DAG is the proof that
backfill is supported.

## 19. Common Troubleshooting

| Symptom | Likely cause | What to check |
|---|---|---|
| Airflow page does not open | Containers still starting or port conflict | `docker compose ps` |
| DAG does not appear | Scheduler has not parsed DAG yet | Refresh after 30-60 seconds |
| Task failed | Python script error or missing output | Open task logs in Airflow |
| Dashboard says no data | Gold monitoring tables not created yet | Run DAG or `python main.py` |
| Backfill takes long | Twelve monthly runs plus Spark overhead | Use Grid View to monitor progress |
| Month shows manual run | It was triggered manually for that execution date | Valid if execution date and task state are correct |

## 20. How To Explain This In The PPT

Use this short explanation:

```text
Airflow orchestrates the ML lifecycle. The DAG first builds the Bronze, Silver
and Gold stores, then ensures a governed champion model exists, scores the
selected snapshot month, and writes performance and drift monitoring results
back to Gold. A separate monthly catchup DAG replays Jan-Dec 2024 using the
Airflow execution date as the snapshot month. The 2024 months are scored with
the frozen champion model, so backfilling demonstrates production replay
without leaking future outcomes into model selection.
```

Use this one-line distinction:

```text
The manual DAG proves the pipeline runs end-to-end; the monthly backfill DAG
proves the same model can be replayed across historical production months.
```

## 21. One-Sentence Summary

The Airflow design is a Lab-5-style orchestration graph for a loan-default ML
pipeline: it prepares data stores, governs the champion model, scores monthly
snapshots, stores Gold predictions, stores Gold monitoring results, and supports
historical monthly backfill without temporal leakage.

