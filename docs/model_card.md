# Model card — SAEWS baseline risk model

| Item | Value |
|---|---|
| Purpose | Estimate the likelihood that a student will experience academic difficulty (fail/withdraw) this term, early enough for supportive outreach. |
| Intended users | Authorized teachers and advisors, as one input to human judgement. |
| Out of scope | Grading, discipline, admission, scholarship or eligibility decisions; diagnosing health conditions; any automatic action. |
| Algorithm | Logistic regression with median imputation and standard scaling (scikit-learn). Chosen for interpretability. |
| Features | `attendance_rate`, `attendance_trend` (last 4 weeks − earlier), `avg_score`, `score_trend` (last 2 assessments − earlier), `missing_rate`, `late_rate`, `engagement_change` (last 3 weeks vs earlier, relative), `avg_logins`, `prior_gpa`. |
| Not used | Demographics or sensitive attributes. The synthetic `equity_group` is used **only** to evaluate subgroup error rates. |
| Training data | **Synthetic** historical cohort (1,500 fictional students) from `seed/synthetic.py`. Must be replaced with approved institutional data and re-validated. |
| Outputs | Probability → level (Low < 0.20 ≤ Moderate < 0.40 ≤ High < 0.65 ≤ Critical; configurable), plus per-feature contributions (coefficient × standardized value) turned into plain-language reasons. |
| Data-quality gates | Completeness < 60% → *Insufficient data* (no prediction). Data older than 21 days or partially missing → result marked provisional with warnings. |
| Fallback | Transparent rules (`ml/rules.py`) when the model cannot be loaded or scored, labelled *Rule-based (fallback)*. If both fail → *Unavailable*. |

## Evaluation (synthetic held-out test set, 25%)
Run `python -m backend.app.ml.train` to reproduce. The run used for the demo reported roughly:

| | Recall | Precision | FPR | ROC-AUC | Brier |
|---|---|---|---|---|---|
| Model @ alert threshold (0.20) | 0.73 | 0.48 | 0.23 | 0.83 | 0.125 |
| Model @ high threshold (0.40) | 0.52 | 0.62 | 0.09 | 0.83 | 0.125 |
| Rule baseline (≥ moderate) | 0.63 | 0.57 | 0.14 | — | — |

The model is well calibrated on this data (predicted vs observed rates agree within ~0.05 per band).
Exact numbers vary slightly per run and are shown on the **Administration → Model monitor** page.

## Fairness checks
Recall and false-positive-rate gaps are computed per `program`, `year_of_study` and `equity_group`.
Gaps above 0.10 are marked **Needs review**. In the demo run, some gaps exceed this (e.g. by year of study, where
groups are small), which shows the check working. A high overall metric is **not** evidence of fairness.

## Known limitations
- Synthetic data cannot capture real institutional patterns; metrics here say nothing about real-world performance.
- Engagement signals can reflect access barriers (devices, connectivity, disability) rather than motivation. Recommendations are worded to check access, not to assume a cause.
- Linear model: interactions are not captured; contributions are relative to the training population.
- Thresholds trade recall against alert workload. They must be set with stakeholders.
