# Airflow DAG Comparison Against Lab 5

## What Lab 5 Shows

Lab 5 uses Airflow task boxes to make each pipeline component visible:

| Lab 5 area | Visible tasks |
|---|---|
| Label store | source check -> bronze label -> silver label -> gold label -> completed |
| Feature store | source checks -> bronze tables -> silver tables -> gold feature store -> completed |
| AutoML | feature/label stores -> model candidates -> completed |
| Inference | feature store -> model inference candidates -> completed |
| Monitoring | inference outputs -> model monitor candidates -> completed |

Not every Lab 5 box is a standalone Python script. Most are `DummyOperator`
checkpoint nodes. The teaching objective is to make the pipeline structure,
dependencies and backfill sequence visible in the Airflow graph.

## What The Earlier Assignment 2 DAG Did

The earlier DAG was operational but compressed:

| Earlier task | Hidden work inside the task |
|---|---|
| `prepare_bronze_silver_gold` | Bronze, Silver, Gold feature store, label store and model feature store |
| `train_or_load_champion` | Governed challenger evaluation or champion reuse |
| `monthly_batch_inference` | Monthly prediction generation |
| `monitor_p0_p1_psi_csi` | P0/P1, PSI and CSI monitoring |

This was runnable, but it under-represented the medallion and model lifecycle
when viewed in Airflow.

## Refactored Assignment 2 DAG

The refactored DAG keeps the same tested execution scripts, but adds
Lab-5-style validation nodes:

| Refactored area | Visible tasks |
|---|---|
| Source checks | attributes, financials, clickstream, LMS |
| Bronze | four Bronze source-domain outputs |
| Silver | four Silver source-domain outputs |
| Gold | feature store, label store, model feature store, preprocessing metadata |
| Model selection | governed champion selection, model bank, model evaluation |
| Inference | monthly batch prediction and Gold prediction table |
| Monitoring | P0/P1/PSI/CSI metrics, feature drift table, chart outputs |

The validation nodes are lightweight `BashOperator` tasks. Source nodes check
that CSV files exist, output nodes check that expected folders/files exist, and
stage-boundary nodes write short echo messages. The heavy work remains in the
tested scripts:

- `scripts/run_bronze.py`
- `scripts/run_silver.py`
- `scripts/run_gold.py`
- `scripts/ensure_champion.py`
- `scripts/run_inference.py`
- `scripts/run_monitoring.py`

This gives the marker a graph that is closer to Lab 5 while preserving the
working Assignment 2 outputs.
