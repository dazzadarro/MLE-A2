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

| Model | Why it was shortlisted | Validation recall | Validation PR-AUC | OOT recall | OOT PR-AUC |
|---|---|---:|---:|---:|---:|
| Logistic Regression | Explainable and fast baseline | 0.739 | 0.573 | 0.738 | 0.474 |
| Random Forest | Nonlinear bagging benchmark | 0.748 | 0.616 | 0.716 | 0.532 |
| Histogram Gradient Boosting | Efficient nonlinear tabular challenger | 0.736 | **0.654** | 0.723 | 0.522 |
| XGBoost | Strong advanced tabular challenger | 0.712 | 0.642 | 0.702 | **0.551** |

Histogram Gradient Boosting is the champion because it passed the P0 recall
floor and achieved the highest validation PR-AUC. XGBoost performed strongly on
OOT, but OOT was deliberately not used for champion selection.

The earlier dashboard view showing recall close to 1.00 came from months inside
the training window. Those values were in-sample and therefore not valid
evidence of generalisation. The monitoring output now suppresses train-period
P0/P1 and reports performance only for validation, test and OOT months:
validation recall is 0.736, test recall is 0.753 and OOT recall is 0.723.

## Automated but governed champion promotion

1. Airflow fingerprints the model code and Gold training inputs.
2. Unchanged inputs reuse the current champion, avoiding needless retraining
   during monthly backfills.
3. Changed code or data triggers all four challengers to be trained and
   evaluated again.
4. A challenger is promoted only if it passes P0 recall and outranks the
   incumbent on validation PR-AUC, with recall and precision as tie-breakers.
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
- OOT result: recall 0.723, PR-AUC 0.522 and ROC-AUC 0.770.
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
- Financial ratios and aggregated clickstream features.
- Chronological 80/10/10 split plus latest month as OOT.
- Train-only median imputation, p1/p99 capping, standardisation and one-hot
  encoding.
- No future repayment fields in model features.

### Slide 5: Candidate models and metric hierarchy

Use the candidate-model table above. Emphasise:

- P0 recall >= 0.70 is a mandatory business-risk gate.
- P1 PR-AUC ranks eligible models under class imbalance.
- Precision and ROC-AUC provide supporting trade-off information.
- Accuracy is not used for champion selection.

### Slide 6: Champion result and governed promotion

- Show the four-model validation and OOT comparison.
- Histogram Gradient Boosting wins on validation PR-AUC after passing P0.
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
- Test recall: 0.753.
- OOT recall: 0.723.
- OOT predicted default rate: 37.1%; observed default rate: 26.8%.
- Explain delayed-label monitoring: PSI/CSI is immediate, outcome performance
  is evaluated only after labels mature.

### Slide 9: Stability monitoring and root-cause finding

- OOT score PSI: 0.320, therefore significant population drift.
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
| Multiple model candidates | Yes | Logistic Regression, Random Forest, Histogram GB, XGBoost |
| Mandatory P0 gate | Yes | Training fails if no candidate passes recall 0.70 |
| Validation-based champion selection | Yes | Eligible models ranked by validation PR-AUC |
| OOT excluded from selection | Yes | OOT records are reporting-only |
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

### Current score if submitted immediately

The code component is approximately **5.0/5.0** based on executed tests.
However, without the required final PDF slideument, the submission would score
approximately **5.0/10.0** overall.

### Projected score after converting this content into a polished deck

| Area | Projected mark | Remaining risk |
|---|---:|---|
| Docker/Airflow availability | 2.0/2.0 | Reconfirm from the final ZIP |
| DAG outputs | 3.0/3.0 | Reconfirm clean manual run |
| Technical deck content | 2.7-3.0/3.0 | Must show actual charts and explain OOT clickstream drift |
| Deck quality | 1.5-2.0/2.0 | Depends on visual hierarchy, legibility and restraint |
| **Projected total** | **9.2-10.0/10.0** | Final PDF and clean-package test are still required |

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
8. Extract the final ZIP into a new folder and repeat Docker build, startup and
   manual DAG execution before submission.
