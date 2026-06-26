# Assignment 2 Presentation Content

## Problem and label

| Question | Decision | Slide justification |
|---|---|---|
| Learning type | Supervised learning | Historical loans have a known future repayment outcome |
| Prediction task | Binary classification | Each loan has one outcome: default or non-default |
| Label | `30dpd_6mob` | Label is 1 when DPD is at least 30 at MOB 6; otherwise 0 |
| Class balance | 28.8% default, 71.2% non-default | Moderate imbalance makes accuracy unsuitable as the main metric |

This is not unsupervised learning because a target label exists. It is not
multiclass or multilabel because there are two mutually exclusive outcomes and
one label per loan.

## Candidate models and actual results

The shortlist intentionally moves from simple and explainable to stronger
nonlinear tabular learners. The pipeline now evaluates 36 governed candidates:
three hyperparameter variants for each of four model families, crossed with
three train-only feature budgets: top 40, top 60 and all features. All
candidates use the same development policy: Jan-Dec 2023 is the modelling cohort, split at loan level into 80% train, 10% validation and 10% test. The split is deterministic and label-stratified using loan_id hash ordering, not month chunks and not random rows. Jan-Dec 2024 is held out as OOT monitoring. All candidates use the same random seed. This makes the comparison fair:
differences come from the learning algorithm, hyperparameters and feature
budget, not from different data samples.

| Best candidate per family | Shortlist justification | Validation recall | Validation PR-AUC | Governance score | Test recall | Test PR-AUC |
|---|---|---:|---:|---:|---:|---:|
| Logistic Regression `C=3.0`, all features | Governance baseline. It is fast, stable, coefficient-based and easy to explain to business users. It also tests whether linear decision boundaries are sufficient after engineered ratios, standardised numerics and one-hot categories. | 0.706 | 0.549 | 0.545 | 0.748 | 0.551 |
| Random Forest depth 12, leaf 5, top 40 features | Robust nonlinear benchmark. It handles interactions and non-monotonic relationships without heavy preprocessing, and bagging reduces variance. It is less transparent than logistic regression, but still easier to explain than boosted ensembles through feature importance. | **0.769** | 0.636 | 0.629 | 0.735 | 0.638 |
| Histogram Gradient Boosting compact, all features | Efficient advanced tabular model. It captures nonlinear patterns and interactions with lower runtime and governance complexity than XGBoost. It is a strong fit for the dataset size and provides the best validation performance/complexity balance. | **0.769** | **0.654** | **0.640** | 0.742 | **0.663** |
| XGBoost depth 4, lr 0.03, top 60 features | High-performing boosted-tree challenger. It is included because it is a proven tabular ML benchmark and handles class imbalance through `scale_pos_weight`. It has more tuning and governance complexity, so it must clearly outperform simpler options before deployment. | 0.727 | 0.644 | 0.626 | **0.748** | 0.654 |

Histogram Gradient Boosting compact with all features is the champion because it
passed the P0 recall floor and achieved the highest validation governance score
after both model-complexity and feature-count penalties. XGBoost and Random
Forest performed strongly on the test months, but the test and OOT monitoring windows are deliberately not used for champion selection.

The earlier dashboard view showing recall close to 1.00 came from months inside
the training window. Those values were in-sample and therefore not valid
evidence of generalisation. The monitoring output now suppresses train-period
P0/P1 and reports performance only for validation, test and OOT monitoring months. Validation recall is 0.769 and validation PR-AUC is 0.654. Test recall
is 0.742 and test PR-AUC is 0.663. The latest OOT monitoring month, Dec
2024, has recall 0.800 and PR-AUC 0.677 after its labels mature.

Full candidate search:

| Family | Hyperparameter variants | Feature budgets | Best validation candidate |
|---|---:|---|---|
| Logistic Regression | 3 | top 40 / top 60 / all | `logistic_regression_c3_0__all_features` |
| Random Forest | 3 | top 40 / top 60 / all | `random_forest_depth12_leaf5__top_40_features` |
| Histogram Gradient Boosting | 3 | top 40 / top 60 / all | `hist_gradient_boosting_compact__all_features` |
| XGBoost | 3 | top 40 / top 60 / all | `xgboost_depth4_lr0_03__top_60_features` |

## Performance versus simplicity decision

The model selection rule is not a weighted average. It is a governed hierarchy:

1. **P0 gate:** validation recall must be at least 0.70.
2. **P1 ranking:** among models that pass P0, use validation PR-AUC as the main
   ranking signal.
3. **Simplicity adjustment:** subtract small model-complexity and feature-count
   penalties from PR-AUC so a more complex model or larger feature set must
   clearly outperform a simpler option.
4. **Tie-breakers:** raw PR-AUC, recall and precision are used if scores are
   close.
5. **Holdout discipline:** test and OOT monitoring months are used for
   reporting and monitoring, not for choosing the champion.

This avoids the common mistake of averaging business-critical recall with a
secondary metric. P0 is the non-negotiable risk-control requirement. P1 is the
main ranking metric among acceptable candidates, while simplicity prevents
unnecessary model complexity when performance is close.

## Airflow orchestration and backfill design

The Airflow DAG follows the same visual logic as Lab 5: each box is an Airflow
task node, not necessarily one independent Python file. Lab 5 uses a mixture of
real execution tasks and checkpoint-style nodes to show source checks,
Bronze/Silver/Gold stores, model inference and monitoring. Assignment 2 keeps
that visible structure, but implements the checkpoint-style boxes as lightweight
`BashOperator` checks or echo markers rather than pure placeholders.

The earlier Assignment 2 DAG was operational but too compressed: one task built
the whole medallion layer, one task selected or loaded the champion, one task
ran inference, and one task ran monitoring. That was runnable, but it hid the
pipeline structure in the graph. The refactored DAG keeps the tested scripts but
adds explicit real Bash validation nodes for the four source checks, four Bronze
outputs, four Silver outputs, Gold feature/label/model stores, model
bank/evaluation, Gold predictions and Gold monitoring outputs.

| DAG area | Visible Airflow nodes | Real execution script |
|---|---|---|
| Bronze | source checks and four Bronze output checkpoints | `scripts/run_bronze.py` |
| Silver | four Silver output checkpoints | `scripts/run_silver.py` |
| Gold | feature store, label store, model feature store and preprocessing metadata | `scripts/run_gold.py` |
| Champion governance | model training start, champion selection, model bank, model evaluation | `scripts/ensure_champion.py` |
| Monthly scoring | inference start, monthly batch inference, Gold predictions | `scripts/run_inference.py` |
| Monitoring | monitoring start, P0/P1/PSI/CSI, feature drift, monitoring charts | `scripts/run_monitoring.py` |

Backfilling is handled by the separate
`mle_assignment_2_monthly_backfill` DAG. It is scheduled monthly from January
2024 to December 2024 with `catchup=True`, so Airflow can simulate each monthly
production run using the run date `{{ ds }}`. The model is selected using only
the 2023 development window: Jan-Dec 2023 loan-level train/validation/test split. Each 2024 backfill run then reuses the governed champion and scores
only that snapshot month. This prevents future 2024 observations from leaking
into model selection or preprocessing fit.

| Comparison | Decision |
|---|---|
| Logistic Regression versus HGB | Logistic is simpler, but HGB improves validation PR-AUC by about 0.105 absolute while still passing P0. The gain is large enough to justify the added complexity. |
| Random Forest versus HGB | Random Forest is less complex and has the same validation recall, but HGB has higher validation PR-AUC and the stronger governance score. |
| XGBoost versus HGB | XGBoost is a strong challenger, but HGB has higher validation recall, higher validation PR-AUC and the best governance score. |

If two models have near-identical validation PR-AUC, for example within 0.01 to
0.02, prefer the simpler model unless there is a business reason to do
otherwise.

Feature simplicity is acceptable but not perfect. The final champion uses 76
inputs after train-only preprocessing. These are engineered financial ratios,
standardised numeric features, one-hot categorical features and aggregated
clickstream features. The feature search also tested top-40 and top-60 subsets
ranked using a train-only embedded selector, so feature count was treated as a
governed design choice. No PCA or broad polynomial expansion is used, so the
model remains auditable. The weakest explainability area is the anonymised
`fe_1` to `fe_20` clickstream features, which should be monitored closely using
CSI and explained as source-system behavioural signals rather than
business-readable drivers.

The feature-count decision is framed as a bias-variance and governance trade-off.
Too few features can underfit because useful borrower, credit and behavioural
signals are removed. Too many features can overfit, increase monitoring scope and
make the model harder to explain. The pipeline therefore plots an elbow chart:
`model_selection_charts/feature_elbow.png`. If validation PR-AUC flattens after
40 or 60 features, the smaller set should be preferred. In this run the full
76-feature set still produced a visible validation lift after the small
feature-count penalty, so all features remained justified.

## Automated but governed champion promotion

1. `python main.py` or `scripts/train_model.py` builds the governed model bank
   by training and evaluating all 36 model and feature-budget candidates.
2. Routine Airflow backfills reuse the existing `champion_model.pkl`, avoiding
   needless retraining while replaying historical monthly scoring.
3. A controlled refresh can be triggered explicitly with
   `scripts/ensure_champion.py --force-refresh` when governance evidence calls
   for challenger evaluation.
4. A challenger is promoted only if it passes P0 recall and outranks the
   incumbent on the simplicity-adjusted validation governance score, with raw
   PR-AUC, recall and precision as tie-breakers.
5. The registry records the selected champion, latest challenger, model version,
   decision threshold, candidate count, random seed, selection rule and training
   signature for audit.
6. Inference always retrieves the governed `champion_model.pkl` pointer and
   records its model version with every prediction.

Simply adding a model file does not deploy it. Promotion occurs only through
the evaluation gate, and test/OOT results remain reporting-only.

## Metric hierarchy

| Priority | Metric | Decision role |
|---|---|---|
| P0 | Recall >= 0.70 | Mandatory gate because missing a true defaulter is the main risk |
| P1 | PR-AUC | Champion ranking metric for the minority default class |
| P2 | Precision | Measures the efficiency and false-positive cost of default flags |
| P3 | ROC-AUC | Supporting threshold-independent ranking measure |

Use one P0, not several. P0 is the single non-negotiable production objective;
P1-P3 explain trade-offs and support diagnosis. Accuracy is supplementary only.

## Hyperparameter tuning approach

This assignment uses a compact, production-style manual grid rather than a
large automated grid search. That is appropriate because the dataset is small,
the runtime must remain manageable in Docker/Airflow, and the goal is to
demonstrate an end-to-end MLOps pipeline rather than exhaust every modelling
option.

| Model | Main settings | Rationale |
|---|---|---|
| Logistic Regression | `C=0.3, 1.0, 3.0`, `class_weight="balanced"` | Tests regularisation strength while retaining explainability. |
| Random Forest | depth 8/10/12, leaf 5/10, 160-220 trees | Tests model capacity while limiting overfitting. |
| Histogram Gradient Boosting | compact, balanced and deeper variants | Tests boosting capacity, learning rate and leaf complexity. |
| XGBoost | depth 3/4, learning rate 0.03/0.05, 220-320 trees | Tests stronger boosted-tree variants with imbalance weighting. |
| Feature budgets | top 40, top 60 and all features | Tests whether a smaller ranked feature set can match the full feature set. |

The decision threshold is tuned per model on the validation set. The threshold
search chooses a threshold that satisfies the P0 recall objective where
possible, then maximises F1 and precision as secondary trade-offs. The final
champion is selected using a governance score:

`governance_score = validation PR-AUC - 0.005 * (simplicity_tier - 1) - 0.00005 * feature_count`

The feature-count penalty is intentionally small, so larger feature sets must
offer a real validation PR-AUC improvement but are not rejected mechanically.

This keeps PR-AUC dominant while requiring more complex models to provide a
clear improvement before deployment.

## Monitoring both drift families

| Drift family | Meaning | Detection | Timing |
|---|---|---|---|
| Data/covariate drift | Input or score distribution changes, `P(X)` | Prediction-score PSI and feature CSI | Available immediately |
| Concept/performance drift | Predictor-outcome relationship changes, `P(Y\|X)` | Recall, PR-AUC, precision, ROC-AUC and predicted vs observed default rate | After MOB 6 labels mature |

PSI/CSI thresholds are `<0.10` stable, `0.10-0.25` watch, and `>0.25`
significant. A single alert triggers investigation; sustained drift together
with P0/P1 deterioration supports recalibration or retraining.

## Backfilling without data leakage

Backfilling is treated as a production replay, not as a chance to retrain with
future information. The source files are historical CSV extracts, so the
pipeline may physically load all available months into partitioned Bronze,
Silver and Gold stores for assignment runtime convenience. Leakage control is
enforced by the modelling and orchestration boundaries:

| Leakage risk | Control in this project |
|---|---|
| Future months influence model training | The development window is fixed before the OOT monitoring/backfill months. OOT months are excluded from model selection and threshold decisions. |
| Preprocessing learns from future rows | Median imputation, caps, standardisation, one-hot vocabularies and feature selection are fitted on train rows only, then reused unchanged. |
| Repayment outcomes leak into features | LMS repayment fields such as `due_amt`, `paid_amt`, `overdue_amt`, `balance`, `installments_missed`, `first_missed_date` and `dpd` are used only for `label_store` and monitoring, never as model features. |
| Backfill accidentally refits using later months | Airflow passes a single `snapshot_date` to the inference/monitoring task. Each backfill run scores that month using the frozen `champion_model.pkl`. |
| Monitoring uses labels too early | PSI/CSI can run immediately because they use input and score distributions. P0/P1 performance metrics are reported only when MOB 6 labels have matured. |
| Earlier backfill months are overwritten by later months | Predictions and monitoring outputs are partitioned by `snapshot_date`, so each replay month is recorded separately. |

This means the backfill answers: "What would the already-approved model have
predicted in this month?" It does not answer: "What model could we have built if
we had already seen all later months?"

## Backfill implementation versus Lab 5

The Assignment 2 DAG follows the Lab 5 backfill pattern but applies it to
model scoring and monitoring rather than only a teaching label-store task.

| Design point | Lab 5 pattern | Assignment 2 implementation |
|---|---|---|
| Schedule | Monthly: `0 0 1 * *` | Monthly: `0 0 1 * *` |
| Backfill control | `catchup=True` | `mle_assignment_2_monthly_backfill` uses `catchup=True` |
| Snapshot parameter | Script receives `--snapshotdate "{{ ds }}"` | Inference and monitoring scripts receive `--snapshotdate "{{ ds }}"` |
| Run grain | One Airflow run per month | One scoring/monitoring replay per OOT month |
| Development/OOT boundary | Teaching example spans 2023-2024 | Model development uses a 2023 loan-level split; Jan-Dec 2024 is replayed as OOT monitoring |
| Data preparation | Lab includes many placeholder tasks | Bronze/Silver/Gold stores are complete partitioned inputs; monthly runs reuse them unless forced |
| Leakage control | Snapshot date demonstrates monthly processing | Frozen champion and train-only preprocessing prevent future months from influencing the model |

Because the source files are historical bulk extracts, the medallion stores are
loaded once as partitioned Parquet for runtime practicality. The monthly
backfill then replays the operational part of the pipeline: load governed
champion, score the selected snapshot month, write `gold/model_predictions`, then
write `gold/model_monitoring` and `gold/feature_drift_monitoring`.

## Three action-plan iterations

### Iteration 1: Rubric coverage

| Requirement | Current status | Action |
|---|---|---|
| Docker Compose exposes Airflow | Implemented | Keep `docker-compose.yaml` simple and marker-friendly |
| Airflow DAG creates model artefacts, predictions and monitoring | Implemented | Verify both manual DAG and monthly backfill DAG from Docker |
| Gold predictions and monitoring tables | Implemented | Show `model_predictions`, `model_monitoring` and `feature_drift_monitoring` in the deck |
| Max 10-slide slideument | Content prepared | Convert this content into a polished PDF deck |

### Iteration 2: Backfill and leakage hardening

| Risk | Improvement |
|---|---|
| Backfill accidentally retrains with future months | Use frozen champion during monthly replay; refresh challengers only through explicit governance command |
| Parallel DAG runs corrupt Gold outputs | Add same-path Parquet write lock and locked snapshot upsert |
| Training metrics shown as production performance | Suppress train-period P0/P1 and report validation/test/OOT months only |
| Future repayment data leaks into features | Keep LMS repayment fields in label/monitoring logic only |

### Iteration 3: Submission polish

| Remaining task | Why it matters |
|---|---|
| Final PDF slideument | Worth 5 marks across technical content and corporate quality |
| Clean Git status before final ZIP | Spark regenerates Parquet filenames, so code/doc changes and generated datamart churn must be reviewed separately |
| Fresh clone or clean-folder run | Confirms the marker can build Docker and run Airflow without local hidden state |
| Remove stale wording | The deck and README must describe governed explicit refresh, not automatic retraining on every backfill |
| Keep dashboard detection-only | Monitoring can flag drift; root-cause and retraining decisions need evidence and governance approval |

## How to show lessons from class

Do not spend a full slide listing generic lessons. Demonstrate them alongside
the implementation:

- loan-level stratified 80/10/10 splitting inside the 2023 development cohort avoids row leakage while preserving class balance;
- preprocessing is fitted on train only;
- champion/challenger selection uses validation, with test and OOT months kept untouched for reporting;
- Airflow receives `snapshot_date` and supports leakage-safe historical
  backfills;
- the backfill DAG simulates Jan-Dec 2024 monthly batch scoring after the 2023
  development window;
- model versions, thresholds and metrics are stored in the model bank;
- delayed labels are separated from immediate stability monitoring;
- retraining is governed by evidence, not triggered by one noisy month.

## Recommended 10-slide slideument

### Slide 1: Executive summary

- Predict loan default at application time using a supervised binary classifier.
- Label: `30dpd_6mob`, engineered from future LMS repayment performance.
- Champion: compact Histogram Gradient Boosting using all 76 selected model
  features.
- Validation result: recall 0.769 and PR-AUC 0.654.
- Test result: recall 0.742 and PR-AUC 0.663.
- Latest OOT monitoring month, Dec 2024: recall 0.800 and PR-AUC 0.677.
- Airflow automates feature readiness, champion governance, inference and
  monitoring.

### Slide 2: Data, label and leakage boundary

- Four source domains: attributes, financials, clickstream and LMS.
- Application-time data enters the feature store.
- Future repayment fields enter the label store only.
- Show the 2023 development cohort and 2024 OOT monitoring window.
- Explain that the label is generated, not supplied:
  `label = 1` when DPD is at least 30 at MOB 6.

### Slide 3: End-to-end architecture

Show:

`Raw CSV -> Bronze -> Silver -> Gold feature/label stores -> model training ->
model bank -> monthly inference -> Gold predictions -> monitoring Gold tables
-> dashboard`

Include the two Airflow entry points:

- manual marker DAG for an immediate full run;
- paused monthly catchup DAG for Jan-Dec 2024 OOT backfilling.

### Slide 4: Feature and model dataset preparation

- One row per loan.
- Financial ratios, including debt/income, EMI/income, investment/income,
  balance/debt, inquiries/loan and repayment ability, plus aggregated
  clickstream features.
- 2023 is the development cohort: deterministic loan-level 80/10/10 train/validation/test split.
- Jan-Dec 2024 is the OOT monitoring/backfill window.
- Train-only median imputation, p1/p99 capping, standardisation and one-hot
  encoding.
- No future repayment fields in model features.
- Train-only feature ranking supports top-40, top-60 and all-feature candidate
  evaluation.

### Slide 5: Candidate models and metric hierarchy

Use the candidate-model table above. Emphasise:

- P0 recall >= 0.70 is a mandatory business-risk gate.
- P1 PR-AUC ranks eligible models under class imbalance.
- Precision and ROC-AUC provide supporting trade-off information.
- Accuracy is not used for champion selection.

### Slide 6: Champion result and governed promotion

- Show the four-family validation and test comparison.
- Histogram Gradient Boosting compact with all features wins on the governance
  score after passing P0.
- Show `model_selection_charts/feature_elbow.png` to justify why the full
  76-feature set is retained despite the larger monitoring burden.
- Test and OOT monitoring months are not used during model selection.
- Show the controlled promotion sequence:
  train challengers -> P0 gate -> P1 PR-AUC ranking -> simplicity penalty ->
  governed champion pointer -> versioned predictions.

### Slide 7: Batch deployment and Airflow execution

- Selected deployment: monthly batch inference because source features arrive
  by snapshot month and the target matures after MOB 6.
- `champion_model.pkl` is the governed deployment pointer.
- Predictions are stored as Gold Parquet partitioned by `snapshot_date`.
- Backfill uses the Airflow execution date as the snapshot month and replays one
  month at a time with the frozen champion artefacts.
- Execution evidence: the monthly Airflow backfill was run for Jan-Dec 2024 and
  all twelve execution dates completed successfully in Airflow Grid/Calendar.
- Presenter note: Airflow's Task Tries tab may show a retry spike for April and
  July because of earlier interrupted/manual reruns. Use Grid or Calendar as
  the main evidence that all monthly DAGRuns succeeded.
- Real-time API serving is not justified for the supplied batch data.
- Dashboard can be deployed separately on Render as a read-only monitoring
  surface.

### Slide 8: Performance monitoring

Use the corrected performance chart:

- Training-window P0/P1 is intentionally suppressed as in-sample reference.
- Validation recall: 0.769; validation PR-AUC: 0.654.
- Test recall: 0.742; test PR-AUC: 0.663.
- Latest OOT monitoring month, Dec 2024: recall 0.800 and PR-AUC 0.677.
- Dec 2024 predicted default rate: 38.1%; observed default rate: 27.2%.
- Interpret Jan-Jun 2024 as early deployment monitoring and Jul-Dec 2024 as the
  period where clickstream population coverage changes.
- Explain delayed-label monitoring: PSI/CSI is immediate, outcome performance
  is evaluated only after labels mature.

### Slide 9: Stability monitoring and drift investigation

- Dec 2024 prediction score PSI is 0.170, which sits in the watch band. The
  strongest monthly population drift occurs in Nov 2024, where PSI reaches
  0.303 and crosses the significant-drift threshold.
- The largest CSI values are the standardised clickstream features.
- Drift investigation evidence: the clickstream file continues monthly through
  December 2024, but it covers only the original 8,974-customer panel. From July
  2024 onward, the LMS application population switches to a new cohort with zero
  clickstream overlap. The Jan-Dec 2024 monitoring window contains 3,000 of
  those new-cohort application customers; the wider LMS source contains 3,526
  post-July application customers.
- Consequently post-June 2024 application rows have missing clickstream values
  that are train-median imputed; CSI values around 12 flag this distribution
  collapse.
- This is a feature-availability / covariate-drift incident. It is not automatic
  proof that the model algorithm itself must be replaced.

### Slide 10: Governance SOP, limitations and next actions

| Trigger | Response |
|---|---|
| Recall below 0.70 | Immediate escalation; review threshold, data and model |
| PSI/CSI 0.10-0.25 | Investigate and place the month/features on watch |
| PSI/CSI above 0.25 | Escalate data-quality and population review |
| Clickstream coverage below 80% | Treat as feature-source incident; investigate upstream coverage before retraining |
| Sustained drift or P0/P1 degradation | Retrain challengers and apply the promotion gate |
| Changed feature contract | Require explicit review; do not auto-promote |

Limitations:

- teaching/synthetic dataset rather than live banking data;
- no causal interpretation of feature drift;
- no fairness or protected-class assessment;
- no calibrated expected-loss or financial-cost optimisation;
- dashboard deployment remains read-only and batch-oriented.

## Implementation checklist

| Requirement or design consideration | Implemented in code? | Evidence |
|---|---|---|
| Supervised binary target | Yes | Gold `label_store`, `30dpd_6mob` |
| Leakage separation | Yes | Repayment outcome fields excluded from feature/model stores |
| 2023 loan-level development split and 2024 OOT window | Yes | `data_split` in Gold stores |
| Train-only preprocessing | Yes | Gold preprocessing metadata fitted from train |
| Multiple model candidates | Yes | 36 candidates across Logistic Regression, Random Forest, Histogram GB, XGBoost and top-40/top-60/all feature budgets |
| Mandatory P0 gate | Yes | Training fails if no candidate passes recall 0.70 |
| Validation-based champion selection | Yes | Eligible models ranked by validation PR-AUC |
| Test/OOT windows excluded from selection | Yes | They are reporting and monitoring windows |
| Reproducible model comparison | Yes | Loan-level stratified split, stable loan_id hash order and shared seed 42 |
| Versioned model bank | Yes | Versioned pickle plus champion pointer and JSON registry |
| Fair incumbent/challenger comparison | Yes | Both evaluated on the current validation population |
| Governed champion refresh | Yes | Routine backfills reuse the champion; explicit refresh evaluates challengers and applies incumbent comparison |
| Leakage-safe backfill | Yes | Monthly Airflow `snapshot_date`, frozen champion and train-only preprocessing |
| Monthly predictions Gold table | Yes | `gold/model_predictions` |
| P0/P1 monitoring Gold table | Yes | `gold/model_monitoring` |
| PSI and CSI monitoring | Yes | Model and feature drift Gold tables |
| Train-period performance suppression | Yes | Marked `in_sample_reference` |
| Monitoring dashboard | Yes | Docker service on port 8050 |
| Marker-friendly Airflow run | Yes | Manual DAG defaults to December 2024 OOT monitoring month |
| Historical OOT monitoring backfill | Yes | Separate paused monthly catchup DAG for Jan-Dec 2024 |
| Retraining recommendation | Partly automated | Status is calculated; final retraining remains governed/human-approved |
| Real-time serving | Not implemented by design | Batch deployment is better aligned with monthly source data |
| Fairness/explainability report | Not yet implemented | Present as a limitation or optional enhancement |

## Third-party rubric audit

Official marking:

| Criterion | Marks | Current evidence | Audit judgement |
|---|---:|---|---|
| Docker Compose opens Airflow | 2 | Clean webserver/scheduler startup and healthy UI | Strong |
| Airflow DAG creates models, predictions and monitoring | 3 | All six manual-DAG tasks pass; outputs exist in model bank and Gold | Strong |
| Technical design and monitoring visualisation | 3 | Design, results and four monitoring charts exist | Strong content, deck still required |
| Corporate-quality slideument | 2 | No final Assignment 2 PDF yet | Not yet scoreable |

### Latest pipeline verification

On 15 June 2026, the corrected Assignment 2 split was rerun inside Docker using
the updated Assignment 2 source data. The full pipeline verification produced
the following results:

- `docker compose run --rm airflow-webserver python /opt/airflow/project/main.py`: passed;
- Bronze, Silver, Gold, model bank, prediction and monitoring outputs were recreated;
- champion model was promoted as `hist_gradient_boosting_compact__all_features`;
- latest model version was `20260615T162528Z`;
- end-to-end Docker runtime was approximately ten minutes after image startup.

On 21 June 2026, the Airflow wrapper scripts and monthly Gold upserts were
hardened and rechecked:

- direct `scripts/run_medallion.py --snapshotdate 2024-12-01`: passed and
  skipped rebuild when complete Gold stores already existed;
- direct `scripts/ensure_champion.py`: passed and reused the governed champion;
- direct `scripts/run_inference.py --snapshotdate 2024-12-01`: passed;
- direct `scripts/run_monitoring.py --snapshotdate 2024-12-01`: passed;
- `airflow dags test mle_assignment_2_pipeline 2024-12-01`: passed;
- real monthly backfill for Jan-Dec 2024: passed in Airflow, with all execution
  dates showing `success`.

Confirmed monthly Airflow states:

| Execution month | Airflow state |
|---|---|
| 2024-01 | success |
| 2024-02 | success |
| 2024-03 | success |
| 2024-04 | success |
| 2024-05 | success |
| 2024-06 | success |
| 2024-07 | success |
| 2024-08 | success |
| 2024-09 | success |
| 2024-10 | success |
| 2024-11 | success |
| 2024-12 | success |

July appears as `manual__2024-07-01...` in Airflow because it was originally
triggered from the UI before the backfill rerun, but it completed successfully
for the correct July execution date and can be read as valid Calendar/Grid
evidence.

Before final submission, the repository should be pushed and checked once from a
fresh Git clone or clean folder before packaging.

### Current score if submitted immediately

The code component is approximately **5.0/5.0** based on executed tests.
However, without the required final PDF slideument, the submission would score
approximately **5.0/10.0** overall.

### Projected score after converting this content into a polished deck

| Area | Projected mark | Remaining risk |
|---|---:|---|
| Docker/Airflow availability | 2.0/2.0 | Verified with running Docker Compose services |
| DAG outputs | 3.0/3.0 | Manual DAG plus Jan-Dec 2024 backfill states verified |
| Technical deck content | 2.7-3.0/3.0 | Must show actual charts and explain forward-window clickstream drift |
| Deck quality | 1.5-2.0/2.0 | Depends on visual hierarchy, legibility and restraint |
| **Projected total** | **9.2-10.0/10.0** | Final PDF, GitHub push, and final ZIP naming remain |

### Highest-value moves to close the gap

1. Build the final PDF at no more than 10 slides using the structure above.
2. Use actual monitoring charts rather than conceptual placeholders.
3. Put the Jul-Dec 2024 clickstream availability finding on the monitoring slide.
4. Show the automatic champion promotion gate and the latest promotion decision
   from `model_registry.json`.
5. Keep architecture readable; do not overload one diagram with every column.
6. Include a concise deployment choice and governance SOP.
7. Push the current code and docs to GitHub after reviewing generated `datamart`
   churn separately from source-code changes.
8. Verify the one-line `Readme.txt` GitHub link and the Docker/Airflow URLs.
9. After the final PDF is added, create the submission ZIP from the tested Git
   revision and perform a quick content check before uploading.

## Reproducibility decision

The train, validation and test populations are fixed by a deterministic loan-level, label-stratified hash split inside Jan-Dec 2023. Jan-Dec 2024 is fixed as OOT monitoring and is not used for champion selection. All stochastic candidate algorithms use the same project seed, `42`, and
the split is reproducible because loan IDs are ordered by a stable hash before fitting and evaluation.

Using a different seed for every model would make the comparison less fair
because performance differences could come from randomisation rather than the
algorithm. In a production model-development exercise, robustness can be tested
separately using repeated seeds or rolling time-based backtests. The governed
champion-selection run should remain fixed and reproducible.



