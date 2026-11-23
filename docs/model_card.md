# Model card — SAEWS baseline risk model

| Item | Value |
|---|---|
| Purpose | Estimate the likelihood that a student will experience academic difficulty (fail/withdraw) this term, early enough for supportive outreach. |
| Intended users | Authorized teachers and advisors, as one input to human judgement. |
| Out of scope | Grading, discipline, admission, scholarship or eligibility decisions; diagnosing health conditions; any automatic action. |
| Algorithm | Logistic regression with median imputation and standard scaling (scikit-learn). Chosen for interpretability. |
| Features | `attendance_rate`, `attendance_trend` (last 4 weeks − earlier), `avg_score`, `score_trend` (last 2 class tests/exams − earlier), `missing_rate`, `late_rate`, `engagement_change` (last 3 weeks vs earlier, relative), `avg_logins` (online learning portal), `prior_gpa` (previous exam GPA on the 5.00 scale; SSC GPA for college students). |
| Not used | Demographics or sensitive attributes. The synthetic `equity_group` is used **only** to evaluate subgroup error rates. |
| Training data | **Synthetic** historical cohort (1,500 fictional Bangladeshi school and college students, Class 9–12) from `seed/synthetic.py`. Must be replaced with approved institutional data and re-validated. |
| Outputs | Probability → level (Low < 0.20 ≤ Moderate < 0.40 ≤ High < 0.65 ≤ Critical; configurable), plus per-feature contributions (coefficient × standardized value) turned into plain-language reasons. |
| Data-quality gates | Completeness < 60% → *Insufficient data* (no prediction). Data older than 21 days or partially missing → result marked provisional with warnings. |
| Fallback | Transparent rules (`ml/rules.py`) when the model cannot be loaded or scored, labelled *Rule-based (fallback)*. If both fail → *Unavailable*. |

## Evaluation (synthetic held-out test set, 25%)
Run `python -m backend.app.ml.train` to reproduce. The run used for the demo reported roughly:

| | Recall | Precision | FPR | ROC-AUC | Brier |
|---|---|---|---|---|---|
| Model @ alert threshold (0.20) | 0.74 | 0.43 | 0.26 | 0.83 | 0.127 |
| Model @ high threshold (0.40) | 0.51 | 0.53 | 0.12 | 0.83 | 0.127 |
| Rule baseline (≥ moderate) | 0.65 | 0.48 | 0.19 | — | — |

Calibration is close in the low and very high bands (within ~0.01). The 0.4–0.8 bands over-predict by about 0.14–0.18 on
this small test set (36 and 22 students).
Exact numbers vary slightly per run and are shown on the **Administration → Model monitor** page.

## Fairness checks
Recall and false-positive-rate gaps are computed per `program` (class group, e.g. *School - Science*),
`year_of_study` (class 9–12) and `equity_group`. Gaps above 0.10 are marked **Needs review**. In the demo run,
all three are flagged (recall gaps ≈ 0.28 by class group, 0.27 by class and 0.14 by equity group). Six class groups
and four classes leave small test subgroups, so part of this is noise, and the flags show the check working. A high overall metric is **not** evidence of fairness.

## Known limitations
- Synthetic data cannot capture real institutional patterns; metrics here say nothing about real-world performance.
- Engagement signals can reflect access barriers (devices, connectivity, disability) rather than motivation. Recommendations are worded to check access, not to assume a cause.
- Linear model: interactions are not captured; contributions are relative to the training population.
- Thresholds trade recall against alert workload. They must be set with stakeholders.
