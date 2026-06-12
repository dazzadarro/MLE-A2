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
