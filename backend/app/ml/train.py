r"""Train, evaluate and register the baseline risk model.

    .\.venv\Scripts\python.exe -m backend.app.ml.train [--students 1500] [--seed 7]

Trains a scaled logistic regression (interpretable baseline) on a synthetic historical
cohort, compares it with the transparent rule baseline, checks calibration and subgroup
error rates, saves a versioned artifact and marks it active in ``registry.json``.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..config import get_settings
from ..seed.synthetic import generate_cohort, term_start_for
from .evaluate import calibration_table, classification_report, subgroup_report
from .features import FEATURES, compute_features
from .model import reset_cache
from .rules import evaluate_rules

ALGORITHM = "LogisticRegression (median imputation + standard scaling)"


def train_model(out_dir: str | Path | None = None, n_students: int = 1500, seed: int = 7, verbose: bool = True) -> dict:
    s = get_settings()
    out_dir = Path(out_dir or s.model_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Historical (previous-term) cohort with known outcomes.
    hist_start = term_start_for(date.today() - timedelta(weeks=26))
    cohort = generate_cohort(n_students, seed=seed, term_start=hist_start, code_prefix="H", with_outcome=True)
    feats = compute_features(cohort.frames(), as_of=hist_start + timedelta(weeks=10))
    meta = cohort.students.set_index("student_code").loc[feats.index]
    X = feats[FEATURES]
    y = meta["outcome_at_risk"].to_numpy()

    X_tr, X_te, y_tr, y_te, m_tr, m_te = train_test_split(X, y, meta, test_size=0.25, stratify=y, random_state=seed)

    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, C=1.0)),
    ])
    pipe.fit(X_tr, y_tr)
    proba = pipe.predict_proba(X_te)[:, 1]

    alert_threshold = s.risk_threshold_moderate
    pred = (proba >= alert_threshold).astype(int)
    model_metrics = classification_report(y_te, proba, pred)
    model_metrics_high = classification_report(y_te, proba, (proba >= s.risk_threshold_high).astype(int))

    rule_pred = np.array([
        int(evaluate_rules({f: (None if np.isnan(v) else v) for f, v in row.items()})[1] in ("moderate", "high", "critical"))
        for row in X_te.to_dict("records")
    ])
    rule_metrics = classification_report(y_te, None, rule_pred)

    groups = m_te[["program", "year_of_study", "equity_group"]].copy()
    fairness = subgroup_report(groups, y_te, pred)

    version = "lr-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    coefs = dict(zip(FEATURES, [round(float(c), 4) for c in pipe.named_steps["clf"].coef_[0]], strict=True))
    metrics = {
        "alert_threshold": alert_threshold,
        "thresholds": {
            "moderate": s.risk_threshold_moderate,
            "high": s.risk_threshold_high,
            "critical": s.risk_threshold_critical,
        },
        "model_at_alert_threshold": model_metrics,
        "model_at_high_threshold": model_metrics_high,
        "rule_baseline": rule_metrics,
        "calibration": calibration_table(y_te, proba),
        "coefficients": coefs,
        "training": {
            "n_train": int(len(y_tr)),
            "n_test": int(len(y_te)),
            "data": "synthetic historical cohort (fictional) — replace with approved institutional data",
        },
    }

    artifact = f"model_{version}.joblib"
    joblib.dump({"version": version, "algorithm": ALGORITHM, "features": FEATURES, "pipeline": pipe},
                out_dir / artifact)
    (out_dir / f"metrics_{version}.json").write_text(json.dumps({"metrics": metrics, "fairness": fairness}, indent=2))
    (out_dir / "registry.json").write_text(json.dumps({"active": version, "artifact": artifact}, indent=2))
    reset_cache()

    result = {"version": version, "algorithm": ALGORITHM, "artifact": str(out_dir / artifact),
              "metrics": metrics, "fairness": fairness}
    if verbose:
        _print_report(result)
    return result


def register_in_db(result: dict) -> None:
    from ..database import SessionLocal
    from ..models import ModelRegistry

    with SessionLocal() as db:
        db.query(ModelRegistry).update({ModelRegistry.is_active: False})
        db.add(ModelRegistry(version=result["version"], algorithm=result["algorithm"], features=FEATURES,
                             metrics=result["metrics"], fairness=result["fairness"],
                             artifact_path=result["artifact"], is_active=True))
        db.commit()


def _print_report(r: dict) -> None:
    m = r["metrics"]
    print(f"\nModel {r['version']}  ({r['algorithm']})")
    print(f"Train/test: {m['training']['n_train']}/{m['training']['n_test']}  (synthetic data)")
    for label, key in [("Model @ alert threshold", "model_at_alert_threshold"),
                       ("Model @ high threshold", "model_at_high_threshold"),
                       ("Rule baseline", "rule_baseline")]:
        x = m[key]
        extra = f"  AUC={x['roc_auc']}  Brier={x['brier']}" if "roc_auc" in x else ""
        print(f"  {label:<24} recall={x['recall']}  precision={x['precision']}  "
              f"FPR={x['fpr']}  flag_rate={x['flag_rate']}{extra}")
    print("  Calibration:", ", ".join(f"{c['bin']}: pred {c['mean_predicted']} / obs {c['observed_rate']}"
                                     for c in m["calibration"]))
    print("  Subgroup checks:")
    for col, rep in r["fairness"].items():
        flag = "REVIEW" if rep["needs_review"] else "ok"
        print(f"    {col:<14} recall_gap={rep['recall_gap']}  fpr_gap={rep['fpr_gap']}  [{flag}]")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--students", type=int, default=1500)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--no-db", action="store_true", help="skip writing to the model_registry table")
    args = p.parse_args()
    result = train_model(n_students=args.students, seed=args.seed)
    if not args.no_db:
        try:
            register_in_db(result)
            print("Registered in database.")
        except Exception as exc:  # noqa: BLE001
            print(f"(Model saved; database registration skipped: {exc})")


if __name__ == "__main__":
    main()
