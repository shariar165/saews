"""Model evaluation: discrimination, calibration, and subgroup error rates (SRS §6.4)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score


def _rates(y: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision_score(y, pred, zero_division=0), 4),
        "recall": round(recall_score(y, pred, zero_division=0), 4),
        "fpr": round(fp / (fp + tn), 4) if (fp + tn) else None,
        "fnr": round(fn / (fn + tp), 4) if (fn + tp) else None,
        "flag_rate": round(float(pred.mean()), 4) if len(pred) else None,
    }


def classification_report(y: np.ndarray, proba: np.ndarray | None, pred: np.ndarray) -> dict:
    out = {"n": int(len(y)), "base_rate": round(float(y.mean()), 4), **_rates(y, pred)}
    if proba is not None:
        out["roc_auc"] = round(float(roc_auc_score(y, proba)), 4)
        out["brier"] = round(float(brier_score_loss(y, proba)), 4)
    return out


def calibration_table(y: np.ndarray, proba: np.ndarray, bins: int = 5) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (proba >= lo) & (proba < hi if hi < 1 else proba <= hi)
        if mask.sum() == 0:
            continue
        rows.append({
            "bin": f"{lo:.1f}-{hi:.1f}",
            "n": int(mask.sum()),
            "mean_predicted": round(float(proba[mask].mean()), 4),
            "observed_rate": round(float(y[mask].mean()), 4),
        })
    return rows


def subgroup_report(groups: pd.DataFrame, y: np.ndarray, pred: np.ndarray, min_n: int = 30) -> dict:
    """Per-subgroup recall/FPR/FNR. Groups smaller than ``min_n`` are reported but not compared."""
    report: dict[str, dict] = {}
    for col in groups.columns:
        rows = {}
        for value in sorted(groups[col].dropna().unique()):
            mask = (groups[col] == value).to_numpy()
            r = {"n": int(mask.sum()), "base_rate": round(float(y[mask].mean()), 4), **_rates(y[mask], pred[mask])}
            r["sufficient_sample"] = bool(mask.sum() >= min_n)
            rows[str(value)] = r
        comparable = [r for r in rows.values() if r["sufficient_sample"] and r["recall"] is not None]
        gap = (max(r["recall"] for r in comparable) - min(r["recall"] for r in comparable)) if len(comparable) > 1 else 0.0
        fpr_vals = [r["fpr"] for r in comparable if r["fpr"] is not None]
        fpr_gap = (max(fpr_vals) - min(fpr_vals)) if len(fpr_vals) > 1 else 0.0
        report[col] = {
            "groups": rows,
            "recall_gap": round(gap, 4),
            "fpr_gap": round(fpr_gap, 4),
            "needs_review": bool(gap > 0.10 or fpr_gap > 0.10),
        }
    return report
