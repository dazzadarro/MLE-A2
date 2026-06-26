# Assignment 2 Slideument Content

This document is the source text for the management-facing slideument. It is
written as an executive explanation of the operating model, not as a direct
reply to the assignment brief.

## Current Verified Project Values

Use these values unless the pipeline is rerun and the model bank changes.

| Area | Current value |
|---|---|
| Business problem | Loan default prediction at application / monthly scoring time |
| Learning setup | Supervised binary classification |
| Label | `30dpd_6mob`: label = 1 if DPD >= 30 at MOB 6, else 0 |
| Source domains | Attributes, financials, clickstream, LMS loan daily |
| Overall label rate | 28.9% default, 71.1% non-default |
| Model development window | Jan-Dec 2023 |
| Split method | Deterministic loan-level stratified 80/10/10 split inside Jan-Dec 2023 |
| Development split counts | Train 4,978, validation 491, test 489 |
| Forward monitoring window | Jan-Dec 2024 |
| Forward monitoring rows | 6,016 prediction rows |
| Candidate search | 36 candidates = 4 model families x 3 hyperparameter variants x 3 feature budgets |
| Model families | Logistic Regression, Random Forest, Histogram Gradient Boosting, XGBoost |
| Feature budgets | Top 40, top 60 and all model features |
| Current governed champion pointer | `hist_gradient_boosting_deeper__top_40_features` |
| Champion version | `20260626T110604Z` |
| Champion feature count | 40 |
| Decision threshold in registry | 0.43 |
| Random seed | 42 |
| Latest Dec 2024 OOT recall | 0.800 |
| Latest Dec 2024 OOT PR-AUC | 0.677 |
| Latest Dec 2024 OOT precision | 0.571 |
| Latest Dec 2024 PSI | 0.335, significant drift |
| Dec 2024 scored loans | 515 |
| Dec 2024 predicted default rate | 38.1% |
| Dec 2024 observed default rate | 27.2% |
| Gold prediction output | `datamart/gold/model_predictions` |
| Gold monitoring output | `datamart/gold/model_monitoring` |
| Gold feature drift output | `datamart/gold/feature_drift_monitoring` |

The latest model evaluation artefacts show close competition between Histogram
Gradient Boosting variants. The deployed model should be described using the
governed registry pointer, because inference and monitoring load
`model_bank/champion_model.pkl` and `model_bank/model_registry.json`.

## Executive Narrative

The project converts the Assignment 1 medallion data pipeline into an
operational machine-learning lifecycle. The system prepares trusted loan-level
features, trains governed challenger models, promotes a champion model into a
model bank, replays monthly inference through Airflow backfill, writes
predictions and monitoring results into Gold tables, and visualises performance
and drift in a dashboard.

The most important design decision is separation of responsibilities:

| Layer or component | Responsibility |
|---|---|
| Bronze | Preserve raw source-domain records as partitioned Parquet |
| Silver | Clean, type-cast and conform source-domain data |
| Gold feature and label stores | Produce one row per loan, with application-time predictors separated from future repayment labels |
| Model bank | Store versioned model artefacts and the active champion pointer |
| Monthly inference | Score each selected snapshot month using the frozen champion |
| Monitoring | Track model performance, score population stability and feature-level drift |
| Dashboard | Provide a management view of model health, not an automatic root-cause engine |

## Slide 1: Executive Summary

**Title:** Loan Default Model Lifecycle

**Main message:** The project delivers a batch ML operating model for loan
default prediction, covering data preparation, champion selection, monthly
inference, monitoring and governance.

**Slide content:**

- We predict whether a loan will become 30+ days past due by MOB 6.
- The model is used as a risk-ranking tool for loan default monitoring.
- The solution is a supervised binary classification pipeline.
- The operating model is monthly batch scoring, because the source data is
  snapshot-based and the label matures only after repayment behaviour is
  observed.
- The deployed champion is loaded from the governed model bank, not from an
  ad hoc notebook.
- Gold outputs include predictions, monthly monitoring, feature drift and model
  selection evidence.

**Suggested visual:** Compact architecture flow:
Raw data -> Bronze -> Silver -> Gold -> Model bank -> Monthly inference ->
Monitoring dashboard.

**Management takeaway:** The project is not only a model. It is a controlled
model lifecycle with data controls, reproducible promotion and monitoring.

## Slide 2: Data, Label and Leakage Control

**Title:** Data Foundation and Target Definition

**Main message:** The label is engineered from future repayment behaviour, so
the feature store must strictly contain application-time predictors only.

**Slide content:**

| Source | Business role |
|---|---|
| `features_attributes.csv` | Customer demographics and profile attributes |
| `features_financials.csv` | Credit, income, loan and repayment capacity signals |
| `feature_clickstream.csv` | Digital behaviour features `fe_1` to `fe_20` |
| `lms_loan_daily.csv` | Loan application records and future repayment performance |

Label definition:

```text
label = 1 if dpd >= 30 at MOB 6
label = 0 otherwise
label_def = 30dpd_6mob
```

Leakage boundary:

- Future repayment fields such as `due_amt`, `paid_amt`, `overdue_amt`,
  `balance`, `installments_missed`, `first_missed_date` and `dpd` are used only
  to create the label and monitoring outputs.
- These future outcome fields are excluded from the feature store and model
  feature store.
- Train-only preprocessing prevents validation, test and 2024 monitoring months
  from influencing imputation, capping, scaling, one-hot encoding or feature
  ranking.

**Management takeaway:** The model is designed to simulate information that
would have been available at decision time, not after repayment outcomes were
known.

## Slide 3: Architecture

**Title:** End-to-End ML Architecture

**Main message:** The architecture extends the medallion data stack into a
model lifecycle with orchestration, model artefacts, predictions and monitoring.

**Slide content:**

```text
Raw CSVs
  -> Bronze raw-like Parquet tables
  -> Silver cleaned source-domain tables
  -> Gold feature_store, label_store and model_feature_store
  -> Governed model selection
  -> Model bank
  -> Monthly inference
  -> Gold model_predictions
  -> Gold model_monitoring and feature_drift_monitoring
  -> Dashboard
```

Gold store responsibilities:

| Gold store | Purpose |
|---|---|
| `feature_store` | Human-readable engineered predictors |
| `label_store` | Future outcome label for supervised learning and monitoring |
| `model_feature_store` | Encoded, standardised and ML-ready features |
| `model_predictions` | Monthly scored loans with model version and threshold |
| `model_monitoring` | P0/P1/P2/P3, PSI, default-rate and status metrics |
| `feature_drift_monitoring` | CSI by feature and snapshot month |

**Management takeaway:** Model outputs are treated as governed data products in
the Gold layer, so they can be audited and reused.

## Slide 4: Development Split and Feature Preparation

**Title:** Modelling Window and Feature Controls

**Main message:** Model development uses a fixed 2023 cohort, while 2024 is
reserved for forward monitoring and backfill simulation.

**Slide content:**

| Period | Role |
|---|---|
| Jan-Dec 2023 | Development cohort |
| Within Jan-Dec 2023 | Deterministic loan-level stratified 80/10/10 train, validation and test split |
| Jan-Dec 2024 | Forward prediction and monitoring replay |

Current split profile:

| Split | Rows | Default rate |
|---|---:|---:|
| Train | 4,978 | 28.0% |
| Validation | 491 | 29.1% |
| Test | 489 | 30.9% |
| Forward prediction / OOT monitoring | 6,016 | 29.5% |

The split is not random row splitting and not chronological month chunks. It is
loan-level, deterministic and label-stratified, so all rows for a loan stay in
one split and the default/non-default balance is preserved.

Feature engineering:

- Credit history months from credit history age.
- Number of loan types from cleaned loan-type text.
- Debt-to-income, EMI-to-income and loan-to-income ratios.
- Additional ratios for investment, balance-to-debt, inquiries per loan and
  repayment ability.
- Aggregated clickstream features `fe_1` to `fe_20`.

Train-only preprocessing:

- Median imputation for missing numeric features.
- Percentile capping to reduce extreme-value impact.
- Standardisation for numeric model inputs.
- One-hot encoding using train-fitted category vocabularies.
- Train-only feature ranking for top-40 and top-60 feature budgets.

**Management takeaway:** The split and preprocessing design protect against
leakage while keeping the model reproducible.

## Slide 5: Candidate Models and Metric Hierarchy

**Title:** Governed Candidate Search

**Main message:** The project evaluates several model families but promotes a
champion using a business-first hierarchy, not a single blended score.

Candidate design:

```text
4 model families
x 3 hyperparameter variants per family
x 3 feature budgets
= 36 governed candidates
```

Model families:

| Family | Why it is included |
|---|---|
| Logistic Regression | Transparent baseline; tests whether engineered ratios and linear effects are sufficient |
| Random Forest | Nonlinear benchmark with bagging and moderate interpretability |
| Histogram Gradient Boosting | Efficient tabular challenger with strong nonlinear performance |
| XGBoost | Advanced boosted-tree benchmark with imbalance handling |

Metric hierarchy:

| Priority | Metric | Role |
|---|---|---|
| P0 | Recall >= 0.70 | Mandatory eligibility gate because missed defaulters are the main business risk |
| P1 | PR-AUC | Primary ranking metric among eligible models under class imbalance |
| P2 | Precision | Operational efficiency and false-positive cost |
| P3 | ROC-AUC | Supporting threshold-independent ranking measure |

**P0/P1 justification for management:**

The primary objective is to minimise false negatives, because approving a
borrower who subsequently defaults creates direct credit loss. Recall is
therefore the mandatory gate. Among models that meet the recall floor, PR-AUC is
used because loan default is an imbalanced classification problem. PR-AUC
assesses whether the model ranks likely defaulters above non-defaulters across
thresholds and discourages a naive "predict everyone as default" strategy.

**Management takeaway:** P0 decides eligibility. P1 decides the winner. P2 and
P3 explain the consequences.

## Slide 6: Champion Selection and Results

**Title:** Champion Model Decision

**Main message:** A Histogram Gradient Boosting model is the governed deployed
champion because it provides the strongest risk-ranking performance under the
promotion rules.

Current governed champion:

| Field | Value |
|---|---|
| Model | Histogram Gradient Boosting |
| Registry name | `hist_gradient_boosting_deeper__top_40_features` |
| Version | `20260626T110604Z` |
| Feature count | 40 |
| Registry threshold | 0.43 |
| Candidate count | 36 |

Governance score:

```text
governance_score
= validation PR-AUC
  - 0.005 * (simplicity_tier - 1)
  - 0.00005 * feature_count
```

The penalty is intentionally small. It does not override P0 or P1, but it
prevents unnecessary complexity when candidates are close.

Best validation candidates by family:

| Family | Best candidate | Validation recall | Validation PR-AUC | Governance score |
|---|---|---:|---:|---:|
| Histogram Gradient Boosting | compact, all features | 0.769 | 0.654 | 0.640 |
| Random Forest | depth 12, leaf 5, top 40 | 0.769 | 0.636 | 0.629 |
| XGBoost | depth 4, lr 0.03, top 60 | 0.727 | 0.644 | 0.626 |
| Logistic Regression | C=3.0, all features | 0.706 | 0.549 | 0.545 |

The active deployment pointer remains the model recorded in the registry and
loaded by inference. This keeps deployment auditable: scoring jobs do not pick a
model directly from a leaderboard; they load the governed champion artefact.

**Management takeaway:** The model bank separates experimentation from
deployment. Only the governed champion pointer is used for production scoring.

## Slide 7: Airflow Orchestration and Lab 5 Alignment

**Title:** Monthly Orchestration and Backfill

**Main message:** Airflow operationalises the lifecycle using the same monthly
backfill pattern taught in Lab 5, while making the Assignment 2 model stages
visible.

Airflow entry points:

| DAG | Purpose |
|---|---|
| `mle_assignment_2_pipeline` | Manual end-to-end run for immediate execution |
| `mle_assignment_2_monthly_backfill` | Monthly Jan-Dec 2024 replay using `catchup=True` |

How the Lab 5 pattern is applied:

| Lab 5 idea | Assignment 2 implementation |
|---|---|
| Monthly schedule | `0 0 1 * *` |
| Backfill with execution date | `{{ ds }}` is passed as the monthly `snapshotdate` |
| Visible DAG stages | Source checks, Bronze, Silver, Gold, model bank, inference and monitoring are separate nodes |
| One run per month | Each 2024 DAG run scores and monitors one snapshot month |
| Production replay | The champion is reused; routine backfill does not retrain models |

The graph intentionally contains many visible tasks. Some are heavy execution
scripts and some are lightweight checks. This mirrors Lab 5's teaching pattern:
the graph communicates pipeline structure, while the actual reusable logic
lives in versioned scripts.

Key scripts:

| Stage | Script |
|---|---|
| Bronze | `scripts/run_bronze.py` |
| Silver | `scripts/run_silver.py` |
| Gold | `scripts/run_gold.py` |
| Champion governance | `scripts/ensure_champion.py` |
| Monthly inference | `scripts/run_inference.py` |
| Monitoring | `scripts/run_monitoring.py` |

**Management takeaway:** Airflow provides a repeatable monthly operating rhythm:
prepare data, confirm artefacts, score a snapshot month and publish monitoring.

## Slide 8: Deployment and Inference

**Title:** Batch Deployment Design

**Main message:** Batch deployment is the appropriate operating mode because
the data is monthly snapshot-based and labels mature over time.

Deployment flow:

1. Load the active champion from `model_bank/champion_model.pkl`.
2. Use the registry to identify the model version and threshold.
3. Read the selected snapshot month from `model_feature_store`.
4. Score loans and write predictions to `gold/model_predictions`.
5. Write model version, default probability, decision threshold and predicted
   label with every prediction.

Why not real-time deployment:

- Source files are batch extracts rather than online request streams.
- The target is a MOB 6 repayment outcome, so immediate label feedback is not
  available.
- Monthly portfolio monitoring is better aligned with the assignment data and
  governance objective.

Controlled retraining:

- Routine monthly backfills reuse the champion.
- Retraining is triggered only through an explicit refresh command or
  governance process.
- A refreshed challenger must pass P0 and outrank the incumbent on the
  validation governance rule before the champion pointer changes.

**Management takeaway:** The deployment is conservative: stable monthly scoring
first, governed retraining only when evidence supports it.

## Slide 9: Monitoring Dashboard and Drift Finding

**Title:** Model Monitoring and Stability

**Main message:** The dashboard shows that Dec 2024 performance remains stable,
but data drift requires investigation.

Dashboard headline values for Dec 2024:

| Metric | Value | Interpretation |
|---|---:|---|
| P0 recall | 0.800 | Above the 0.70 floor |
| P1 PR-AUC | 0.677 | Ranking quality remains usable |
| Precision | 0.571 | False-positive trade-off is visible |
| PSI | 0.335 | Significant population shift |
| Loans scored | 515 | Selected snapshot month |
| Predicted default rate | 38.1% | Champion model decisions |
| Observed default rate | 27.2% | Matured MOB 6 outcome |

Drift interpretation:

- The PSI and CSI monitors flag a change in the score and feature
  distributions.
- The strongest CSI signals are clickstream features.
- Investigation found that clickstream data continues to exist through Dec
  2024, but the later LMS applicant cohort has reduced or missing overlap with
  the earlier clickstream customer panel.
- This creates a feature-source coverage issue: clickstream values are missing
  for the new application population and are imputed by the train-fitted
  preprocessing rules.
- The model can still score the month, but the data contract has changed enough
  to require business and data-owner review.

Dashboard wording should remain detection-only:

```text
Performance stable, but data drift requires investigation.
Investigate data drift; retraining trigger not met.
```

**Management takeaway:** The monitor does exactly what it should do: it flags a
material input-distribution change before automatically replacing the model.

## Slide 10: Governance SOP and Next Steps

**Title:** Model Governance and Operating SOP

**Main message:** Monitoring alerts lead to investigation and controlled
refresh, not automatic replacement.

Governance thresholds:

| Condition | Response |
|---|---|
| P0 recall below 0.70 | Escalate immediately; review threshold, data and challenger models |
| PR-AUC drops materially versus baseline | Review ranking quality and candidate refresh |
| PSI below 0.10 | Continue normal monitoring |
| PSI or CSI from 0.10 to 0.25 | Watch; investigate affected population or feature group |
| PSI or CSI above 0.25 | Significant drift; escalate data-quality and model-risk review |
| Clickstream coverage drops materially | Treat as feature-source incident before retraining |
| Sustained drift plus P0/P1 degradation | Trigger controlled challenger refresh |

Retraining policy:

- Do not retrain on every monthly backfill.
- Do not promote a model from OOT performance alone.
- Refresh challengers only after sustained drift, performance degradation or a
  confirmed feature-source change.
- Promote only through the P0 gate, P1 ranking and simplicity-adjusted
  governance score.

Known limitations:

- The dataset is an assignment dataset, not a production banking portfolio.
- Clickstream features are anonymised, so business explainability is limited.
- Fairness, calibration and cost-sensitive expected-loss optimisation are not
  implemented.
- The dashboard is a read-only monitoring surface, not a full incident workflow.

**Management takeaway:** The final design is production-oriented: evidence
first, controlled refresh second, automated replacement only after governance is
met.

## Diagram Guidance for Claude or Manual PPT Rendering

Use a clean left-to-right architecture diagram with the same visual language as
the dashboard: navy headers, white cards, gold highlights and green/red status
accents.

Required diagram components:

1. Four raw source CSVs on the far left.
2. Bronze, Silver and Gold medallion layers as three grouped storage zones.
3. Gold sub-stores: `feature_store`, `label_store`, `model_feature_store`.
4. Model development branch from Gold to:
   - 36 candidates;
   - P0 recall gate;
   - P1 PR-AUC ranking;
   - simplicity penalty;
   - model bank.
5. Model bank containing:
   - versioned artefacts;
   - `champion_model.pkl`;
   - `model_registry.json`.
6. Monthly inference branch:
   - Airflow `snapshotdate`;
   - load champion;
   - score monthly data;
   - write `model_predictions`.
7. Monitoring branch:
   - P0/P1/P2/P3 after labels mature;
   - PSI score drift;
   - CSI feature drift;
   - dashboard.
8. Governance feedback loop:
   - monitoring alert;
   - data investigation;
   - controlled challenger refresh;
   - champion promotion only if P0/P1 governance is passed.

Add a small note near Airflow:

```text
Lab 5 pattern: one monthly DAG run per snapshot date; Jan-Dec 2024 backfilled
with catchup=True; champion is reused during routine replay.
```

Use business terms such as "operating model", "governance", "portfolio
monitoring", "feature-source incident" and "controlled refresh".
