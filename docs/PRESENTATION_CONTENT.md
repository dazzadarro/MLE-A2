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
candidates use the same chronological train/validation/test/OOT split and the
same random seed. This makes the comparison fair: differences come from the
learning algorithm, hyperparameters and feature budget, not from different data
samples.

| Best candidate per family | Shortlist justification | Validation recall | Validation PR-AUC | Governance score | OOT recall | OOT PR-AUC |
|---|---|---:|---:|---:|---:|---:|
| Logistic Regression `C=3.0`, top 60 features | Governance baseline. It is fast, stable, coefficient-based and easy to explain to business users. It also tests whether linear decision boundaries are sufficient after engineered ratios, standardised numerics and one-hot categories. | 0.736 | 0.573 | 0.570 | 0.738 | 0.474 |
| Random Forest depth 10, leaf 5, top 60 features | Robust nonlinear benchmark. It handles interactions and non-monotonic relationships without heavy preprocessing, and bagging reduces variance. It is less transparent than logistic regression, but still easier to explain than boosted ensembles through feature importance. | 0.724 | 0.624 | 0.616 | 0.695 | 0.524 |
| Histogram Gradient Boosting deeper, all features | Efficient advanced tabular model. It captures nonlinear patterns and interactions with lower runtime and governance complexity than XGBoost. It is a strong fit for the dataset size and provides the best performance/complexity balance. | 0.736 | **0.661** | **0.647** | 0.709 | 0.538 |
| XGBoost depth 4, lr 0.05, top 60 features | High-performing boosted-tree challenger. It is included because it is a proven tabular ML benchmark and handles class imbalance through `scale_pos_weight`. It has more tuning and governance complexity, so it must clearly outperform simpler options before deployment. | 0.739 | 0.650 | 0.632 | 0.723 | **0.549** |

Histogram Gradient Boosting deeper with all features is the champion because it
passed the P0 recall floor and achieved the highest governance score after both
model-complexity and feature-count penalties. XGBoost performed strongly on
OOT, but OOT was deliberately not used for champion selection.

The earlier dashboard view showing recall close to 1.00 came from months inside
the training window. Those values were in-sample and therefore not valid
evidence of generalisation. The monitoring output now suppresses train-period
P0/P1 and reports performance only for validation, test and OOT months:
validation recall is 0.736 and OOT recall is 0.709.

Full candidate search:

| Family | Hyperparameter variants | Feature budgets | Best validation candidate |
|---|---:|---|---|
| Logistic Regression | 3 | top 40 / top 60 / all | `logistic_regression_c3_0__top_60_features` |
| Random Forest | 3 | top 40 / top 60 / all | `random_forest_depth10_leaf5__top_60_features` |
| Histogram Gradient Boosting | 3 | top 40 / top 60 / all | `hist_gradient_boosting_deeper__all_features` |
| XGBoost | 3 | top 40 / top 60 / all | `xgboost_depth4_lr0_05__top_60_features` |

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
5. **OOT holdout:** OOT is used for post-selection reporting, not for choosing
   the champion.

This avoids the common mistake of averaging business-critical recall with a
secondary metric. P0 is the non-negotiable risk-control requirement. P1 is the
main ranking metric among acceptable candidates, while simplicity prevents
unnecessary model complexity when performance is close.

| Comparison | Decision |
|---|---|
| Logistic Regression versus HGB | Logistic is simpler, but HGB improves validation PR-AUC by 0.088 absolute while still passing P0. The gain is large enough to justify the added complexity. |
| Random Forest versus HGB | Random Forest is less complex, but HGB has materially higher PR-AUC and better ranking quality. |
| XGBoost versus HGB | XGBoost has higher validation recall and slightly better OOT PR-AUC, but HGB has higher validation PR-AUC and lower governance complexity. Since OOT is reporting-only, HGB remains the champion. |

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

## Automated but governed champion promotion

1. Airflow fingerprints the model code and Gold training inputs.
2. Unchanged inputs reuse the current champion, avoiding needless retraining
   during monthly backfills.
3. Changed code or data triggers all 36 model and feature-budget candidates to
   be trained and evaluated again.
4. A challenger is promoted only if it passes P0 recall and outranks the
   incumbent on the simplicity-adjusted validation governance score, with raw
   PR-AUC, recall and precision as tie-breakers.
5. The versioned artefact and decision are recorded in `model_registry.json`;
   inference always retrieves the governed `champion_model.pkl` pointer.

Simply adding a model file does not deploy it. Promotion occurs only through
the evaluation gate, and OOT results remain reporting-only.

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

## How to show lessons from class

Do not spend a full slide listing generic lessons. Demonstrate them alongside
the implementation:

- chronological train/validation/test/OOT splitting prevents temporal leakage;
- preprocessing is fitted on train only;
- champion/challenger selection uses validation, with OOT kept untouched;
- Airflow receives `snapshot_date` and supports historical backfills;
- model versions, thresholds and metrics are stored in the model bank;
- delayed labels are separated from immediate stability monitoring;
- retraining is governed by evidence, not triggered by one noisy month.

## Recommended 10-slide slideument

### Slide 1: Executive summary

- Predict loan default at application time using a supervised binary classifier.
- Label: `30dpd_6mob`, engineered from future LMS repayment performance.
- Champion: Histogram Gradient Boosting.
- OOT result: recall 0.709, PR-AUC 0.538 and ROC-AUC 0.774.
- Airflow automates feature readiness, champion governance, inference and
  monitoring.

### Slide 2: Data, label and leakage boundary

- Four source domains: attributes, financials, clickstream and LMS.
- Application-time data enters the feature store.
- Future repayment fields enter the label store only.
- Show the chronological train/validation/test/OOT months.
- Explain that the label is generated, not supplied:
  `label = 1` when DPD is at least 30 at MOB 6.

### Slide 3: End-to-end architecture

Show:

`Raw CSV -> Bronze -> Silver -> Gold feature/label stores -> model training ->
model bank -> monthly inference -> Gold predictions -> monitoring Gold tables
-> dashboard`

Include the two Airflow entry points:

- manual marker DAG for an immediate full run;
- paused monthly catchup DAG for historical backfilling.

### Slide 4: Feature and model dataset preparation

- One row per loan.
- Financial ratios, including debt/income, EMI/income, investment/income,
  balance/debt, inquiries/loan and repayment ability, plus aggregated
  clickstream features.
- Chronological 80/10/10 split plus latest month as OOT.
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

- Show the four-family validation and OOT comparison.
- Histogram Gradient Boosting deeper with all features wins on the governance
  score after passing P0.
- OOT is not used during model selection.
- Show the controlled promotion sequence:
  fingerprint -> train challengers -> P0 gate -> compare current validation
  PR-AUC -> update champion pointer -> version predictions.

### Slide 7: Batch deployment and Airflow execution

- Selected deployment: monthly batch inference because source features arrive
  by snapshot month and the target matures after MOB 6.
- `champion_model.pkl` is the governed deployment pointer.
- Predictions are stored as Gold Parquet partitioned by `snapshot_date`.
- Real-time API serving is not justified for the supplied batch data.
- Dashboard can be deployed separately on Render as a read-only monitoring
  surface.

### Slide 8: Performance monitoring

Use the corrected performance chart:

- Training-window P0/P1 is intentionally suppressed as in-sample reference.
- Validation recall: 0.736.
- Test recall: 0.756.
- OOT recall: 0.709.
- OOT predicted default rate: 36.3%; observed default rate: 26.8%.
- Explain delayed-label monitoring: PSI/CSI is immediate, outcome performance
  is evaluated only after labels mature.

### Slide 9: Stability monitoring and root-cause finding

- OOT score PSI: 0.414, therefore significant population drift.
- The largest CSI values are the standardised clickstream features.
- Root cause: clickstream source data ends at December 2024, but the OOT
  application month is January 2025.
- Consequently January 2025 clickstream values are missing and train-median
  imputed; CSI values near 12 flag this distribution collapse.
- This is a data-availability incident, not automatic proof that the model
  algorithm itself must be replaced.

### Slide 10: Governance SOP, limitations and next actions

| Trigger | Response |
|---|---|
| Recall below 0.70 | Immediate escalation; review threshold, data and model |
| PSI/CSI 0.10-0.25 | Investigate and place the month/features on watch |
| PSI/CSI above 0.25 | Escalate data-quality and population review |
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
| Chronological train/validation/test/OOT | Yes | `data_split` in Gold stores |
| Train-only preprocessing | Yes | Gold preprocessing metadata fitted from train |
| Multiple model candidates | Yes | 36 candidates across Logistic Regression, Random Forest, Histogram GB, XGBoost and top-40/top-60/all feature budgets |
| Mandatory P0 gate | Yes | Training fails if no candidate passes recall 0.70 |
| Validation-based champion selection | Yes | Eligible models ranked by validation PR-AUC |
| OOT excluded from selection | Yes | OOT records are reporting-only |
| Reproducible model comparison | Yes | Chronological split, stable row order and shared seed 42 |
| Versioned model bank | Yes | Versioned pickle plus champion pointer and JSON registry |
| Fair incumbent/challenger comparison | Yes | Both evaluated on the current validation population |
| Controlled automatic promotion | Yes | Code/data fingerprint and incumbent comparison |
| Monthly predictions Gold table | Yes | `gold/model_predictions` |
| P0/P1 monitoring Gold table | Yes | `gold/model_monitoring` |
| PSI and CSI monitoring | Yes | Model and feature drift Gold tables |
| Train-period performance suppression | Yes | Marked `in_sample_reference` |
| Monitoring dashboard | Yes | Docker service on port 8050 |
| Marker-friendly Airflow run | Yes | Manual DAG defaults to January 2025 OOT |
| Historical backfill | Yes | Separate paused monthly catchup DAG |
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

### Clean submission verification

On 13 June 2026, commit `7d2ceb6` was exported with `git archive` into a
new folder with no `.git`, virtual environment, or inherited Airflow database.
The marker-style verification produced the following results:

- `docker compose build`: passed;
- `docker compose up -d`: passed;
- Airflow metadatabase and scheduler health: passed;
- monitoring dashboard health: passed;
- Airflow DAG import errors: none;
- manual `mle_assignment_2_pipeline` run: passed;
- all six task instances completed with `success`;
- clean end-to-end DAG duration: approximately two minutes after startup.

The Docker build printed a dependency compatibility warning for Airflow's
unused `pandas-gbq` package versus `pyarrow==10.0.1`. It did not prevent the
image build, DAG execution, Parquet processing, or dashboard startup.

### Current score if submitted immediately

The code component is approximately **5.0/5.0** based on executed tests.
However, without the required final PDF slideument, the submission would score
approximately **5.0/10.0** overall.

### Projected score after converting this content into a polished deck

| Area | Projected mark | Remaining risk |
|---|---:|---|
| Docker/Airflow availability | 2.0/2.0 | Verified from a clean archived copy |
| DAG outputs | 3.0/3.0 | Clean manual run and all task states verified |
| Technical deck content | 2.7-3.0/3.0 | Must show actual charts and explain OOT clickstream drift |
| Deck quality | 1.5-2.0/2.0 | Depends on visual hierarchy, legibility and restraint |
| **Projected total** | **9.2-10.0/10.0** | Final PDF, GitHub push, and final ZIP naming remain |

### Highest-value moves to close the gap

1. Build the final PDF at no more than 10 slides using the structure above.
2. Use actual monitoring charts rather than conceptual placeholders.
3. Put the OOT clickstream availability finding on the monitoring slide.
4. Show the automatic champion promotion gate and the latest non-promotion
   decision from `model_registry.json`.
5. Keep architecture readable; do not overload one diagram with every column.
6. Include a concise deployment choice and governance SOP.
7. Create the GitHub repository named `MLE-A2`, push the committed code, and
   verify the one-line `Readme.txt` link.
8. After the final PDF is added, create the submission ZIP from the tested Git
   revision and perform a quick content check before uploading.

## Reproducibility decision

The train, validation, test and OOT populations are fixed chronologically by
`snapshot_date`; they are not randomly resampled for each model. All stochastic
candidate algorithms use the same project seed, `42`, and each split is sorted
by `snapshot_date` and `loan_id` before fitting and evaluation.

Using a different seed for every model would make the comparison less fair
because performance differences could come from randomisation rather than the
algorithm. In a production model-development exercise, robustness can be tested
separately using repeated seeds or rolling time-based backtests. The governed
champion-selection run should remain fixed and reproducible.
