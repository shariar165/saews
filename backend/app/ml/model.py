"""Loading and scoring the active risk model, with per-feature contributions (FR4/FR5/FR10)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ..config import get_settings
from .features import FEATURES


class ModelUnavailable(RuntimeError):
    """Raised when no valid model can be loaded or scoring fails."""


@dataclass
class LoadedModel:
    version: str
    algorithm: str
    features: list[str]
    pipeline: object  # sklearn Pipeline(imputer, scaler, clf)

    def predict(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Return (probabilities, contributions[n, n_features]).
        Contribution = coefficient x standardized value (log-odds units)."""
        X = X[self.features].astype(float)
        try:
            proba = self.pipeline.predict_proba(X)[:, 1]
            steps = self.pipeline.named_steps
            z = steps["scaler"].transform(steps["imputer"].transform(X))
            contrib = z * steps["clf"].coef_[0]
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailable(f"Model scoring failed: {exc}") from exc
        if not np.all(np.isfinite(proba)):
            raise ModelUnavailable("Model produced non-finite probabilities")
        return proba, contrib


_lock = threading.Lock()
_cache: dict[str, LoadedModel] = {}


def registry_path() -> Path:
    return Path(get_settings().model_dir) / "registry.json"


def load_active_model() -> LoadedModel:
    reg = registry_path()
    if not reg.exists():
        raise ModelUnavailable("No trained model is registered (run the training script)")
    try:
        info = json.loads(reg.read_text(encoding="utf-8"))
        path = reg.parent / info["artifact"]
        key = f"{path}:{path.stat().st_mtime_ns}"
    except Exception as exc:  # noqa: BLE001
        raise ModelUnavailable(f"Model registry unreadable: {exc}") from exc
    with _lock:
        if key in _cache:
            return _cache[key]
        try:
            bundle = joblib.load(path)
            model = LoadedModel(
                version=bundle["version"],
                algorithm=bundle["algorithm"],
                features=bundle["features"],
                pipeline=bundle["pipeline"],
            )
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailable(f"Model artifact could not be loaded: {exc}") from exc
        if model.features != FEATURES:
            raise ModelUnavailable("Model feature list does not match the current feature pipeline")
        _cache.clear()
        _cache[key] = model
        return model


def reset_cache() -> None:
    with _lock:
        _cache.clear()


def model_status() -> dict:
    try:
        m = load_active_model()
        return {"available": True, "version": m.version, "algorithm": m.algorithm, "error": None}
    except ModelUnavailable as exc:
        return {"available": False, "version": None, "algorithm": None, "error": str(exc)}
