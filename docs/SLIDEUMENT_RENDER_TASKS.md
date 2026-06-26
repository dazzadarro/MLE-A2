# Assignment 2 Slideument Render Tasks

Objective: regenerate the earlier Assignment 2 slideument style, not the A1-style deck, with stronger explanatory write-ups on every slide.

## Visual Route

- Use the earlier A2 deck visual language: white background, navy headings/tables, light evidence cards, dashboard screenshots and clean workflow bands.
- Do not use the A1-style deck.
- Do not generate AI images. Use real project evidence instead:
  - Airflow DAG graph screenshot
  - dashboard screenshot
  - dashboard performance/PSI chart row
  - model selection elbow chart

## Slide Tasks

1. Executive summary
   - Explain that A2 extends A1 into a full ML lifecycle.
   - State the fixed 2023 development window and 2024 production replay.

2. Requirements mapped to delivery
   - Map the 10-mark brief to Docker, Airflow, model store, Gold predictions, monitoring and dashboard.
   - Add interpretation that this is a reproducible MLE pipeline, not a notebook.

3. End-to-end architecture
   - Explain batch design, monthly snapshots, Gold outputs and dashboard review.
   - Make clear why real-time serving is out of scope.

4. Airflow backfill and DAG design
   - Use the Airflow graph evidence.
   - Explain real BashOperator scripts versus checkpoint checks.
   - Explain that failed checks require rerunning upstream stage.

5. Feature, label and leakage controls
   - Explain that labels can use future repayment outcome, but predictors cannot.
   - Show feature store, label store and excluded leakage fields.

6. Candidate search and metric hierarchy
   - Explain 4 x 3 x 3 = 36 candidates.
   - Explain P0/P1/P2/P3 and governance score.
   - Include feature budget/elbow rationale.

7. Champion selection result
   - Show best model per family and champion rationale.
   - Explain validation-only selection and why test/forward results are not used to pick champion.

8. Monthly inference and monitoring outputs
   - Explain frozen champion monthly scoring.
   - Show latest KPIs and chart row.
   - Explain delayed label availability.

9. Monitoring dashboard evidence and drift investigation
   - Show full dashboard screenshot.
   - Explain PSI/CSI and detection-only wording.
   - Include clickstream coverage/covariate drift finding.

10. Governance SOP and deployment position
   - Explain watch/escalate/retrain rules.
   - Explain controlled refresh, model registry update and future canary/A-B validation.

## QA Tasks

- Render every slide to PNG.
- Create a contact sheet for review.
- Check for text clipping, unreadable screenshots and unwanted overlap.
- Keep deck at 10 slides maximum.
