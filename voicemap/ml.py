# -*- coding: utf-8 -*-
"""VoiceMap ML integration — sklearn-compatible feature extraction.

The analyzer produces a per-cell Voice Range Profile (one row per MIDI×dB cell,
~70 metric columns). For machine learning you usually want ONE fixed-length
feature vector per recording, regardless of how many cells it populated. This
module provides that bridge:

    from voicemap.ml import VoiceFeatureExtractor
    X = ["a.wav", "b.wav", ...]
    Xf = VoiceFeatureExtractor().fit_transform(X)      # (n_files, n_features)

`VoiceFeatureExtractor` is a standard ``BaseEstimator`` + ``TransformerMixin``,
so it drops into a ``sklearn.pipeline.Pipeline`` and exposes
``get_feature_names_out()``. Each metric column is reduced across the file's
populated cells to summary statistics (cycle-count-weighted mean + std by
default), so every recording maps to the same schema.

Feature metric set + units/descriptions are derived from
``voicemap.metrics_registry`` (single source of truth) — no column names are
hardcoded here.

Helpers:
    read_vrp(path)              read a ';'-separated VRP CSV into a DataFrame
    vrp_to_parquet / read_parquet   parquet round-trip
    feature_schema()            DataFrame describing every VRP column
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from voicemap import metrics_registry as _reg

# The VRP CSV uses a semicolon separator (European-Excel friendly, and avoids
# clashing with the comma in any locale decimal formatting).
VRP_SEP = ";"

# Per-cell key columns + density that are NOT model features.
_NON_FEATURE_COLS = ("MIDI", "dB", "Total")

# MFCC columns exist in the CSV but are intentionally absent from the registry
# (13 entries would clutter the GUI menu). Add them explicitly so power users
# get them as features.
_MFCC_KEYS = tuple(f"MFCC{i + 1}" for i in range(13))

# Categories whose columns are continuous per-cell metrics suitable as
# cross-file features. "Cluster" (categorical label IDs + per-file K-means
# shares) and "Density" (cycle count) are excluded by default — cluster labels
# are not comparable across independent K-means fits.
_DEFAULT_CATEGORIES = ("Acoustic", "EGG", "Singing")


# ─────────────────────────────────────────────────────────────────────────────
# IO helpers (Phase 6.4)
# ─────────────────────────────────────────────────────────────────────────────
def read_vrp(path: str) -> pd.DataFrame:
    """Read a VoiceMap VRP CSV (';'-separated) into a DataFrame."""
    return pd.read_csv(path, sep=VRP_SEP)


def vrp_to_parquet(df: pd.DataFrame, path: str) -> str:
    """Write a VRP DataFrame to parquet (columnar, typed, fast to reload)."""
    df.to_parquet(path, index=False)
    return path


def read_parquet(path: str) -> pd.DataFrame:
    """Read a VRP parquet file back into a DataFrame."""
    return pd.read_parquet(path)


def feature_schema(include_categories: Sequence[str] = _DEFAULT_CATEGORIES,
                   include_mfcc: bool = True) -> pd.DataFrame:
    """Describe the per-cell metric columns that feed the feature extractor.

    Columns: key, category, unit, dtype, validated, description. Derived from
    the metric registry (+ MFCC), so it always tracks the live metric set."""
    rows = []
    for key in _ordered_metric_keys(include_categories, include_mfcc):
        spec = _reg.get(key)
        if spec is not None:
            rows.append({
                "key": spec.key, "category": spec.category,
                "unit": spec.unit, "dtype": "float64",
                "validated": not spec.待验证,
                "description": spec.description,
            })
        else:  # MFCC — not in the registry
            n = key.replace("MFCC", "")
            rows.append({
                "key": key, "category": "Acoustic", "unit": "",
                "dtype": "float64", "validated": True,
                "description": f"Mel-frequency cepstral coefficient {n}.",
            })
    return pd.DataFrame(rows, columns=[
        "key", "category", "unit", "dtype", "validated", "description"])


def _ordered_metric_keys(include_categories: Sequence[str],
                         include_mfcc: bool) -> List[str]:
    """Registry metric keys in the given categories (registry insertion order),
    plus the MFCC columns. Stable + deterministic."""
    cats = set(include_categories)
    keys = [s.key for s in _reg.REGISTRY.values() if s.category in cats]
    if include_mfcc and "Acoustic" in cats:
        keys += list(_MFCC_KEYS)
    return keys


# ─────────────────────────────────────────────────────────────────────────────
# Weighted summary statistics
# ─────────────────────────────────────────────────────────────────────────────
def _weighted_mean_std(values: np.ndarray, weights: np.ndarray):
    """Cycle-count-weighted mean + std over finite, positively-weighted cells.
    Returns (nan, nan) when no cell qualifies."""
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    m = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not m.any():
        return np.nan, np.nan
    v, w = v[m], w[m]
    sw = w.sum()
    mean = float((v * w).sum() / sw)
    var = float((w * (v - mean) ** 2).sum() / sw)
    return mean, float(np.sqrt(max(var, 0.0)))


# ─────────────────────────────────────────────────────────────────────────────
# Feature extractor (Phase 6.1)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from sklearn.base import BaseEstimator, TransformerMixin
except Exception:  # pragma: no cover - sklearn is a hard dep, but degrade gracefully
    class BaseEstimator:  # type: ignore
        def get_params(self, deep=True):
            return {}

        def set_params(self, **p):
            for k, v in p.items():
                setattr(self, k, v)
            return self

    class TransformerMixin:  # type: ignore
        def fit_transform(self, X, y=None, **kw):
            return self.fit(X, y, **kw).transform(X)


class VoiceFeatureExtractor(BaseEstimator, TransformerMixin):
    """Map audio recordings (or pre-computed VRP CSV/parquet files) to a
    fixed-length feature matrix for scikit-learn.

    Parameters
    ----------
    config : VoiceMapConfig, optional
        Analysis config. Defaults to a fresh ``VoiceMapConfig()``. Only used
        when an input is an audio file (ignored for pre-computed VRP files).
    aggregations : tuple of {"mean", "std", "min", "max", "median"}
        Per-metric cell-aggregation statistics. "mean"/"std" are cycle-count
        weighted; "min"/"max"/"median" are unweighted over cell values.
    include_categories : tuple of str
        Registry categories used as features (default Acoustic/EGG/Singing).
        "Cluster"/"Density" are excluded — cluster label IDs are not comparable
        across independent K-means fits.
    include_mfcc : bool
        Append MFCC1..13 (default True).
    on_error : {"nan", "raise"}
        What to do when a file yields no analysable cycles. "nan" emits an
        all-NaN row (impute downstream); "raise" propagates the error.

    Notes
    -----
    - One row per input file. EGG-derived features are 0 for mono recordings
      (no EGG channel) — see docs/ml_schema.md.
    - ``transform`` accepts ``.wav``/audio paths (analysed, no disk side
      effects) or ``.csv``/``.parquet`` VRP files (read directly).
    """

    _AGG_CHOICES = ("mean", "std", "min", "max", "median")

    def __init__(self, config=None,
                 aggregations: Sequence[str] = ("mean", "std"),
                 include_categories: Sequence[str] = _DEFAULT_CATEGORIES,
                 include_mfcc: bool = True,
                 on_error: str = "nan"):
        self.config = config
        self.aggregations = aggregations
        self.include_categories = include_categories
        self.include_mfcc = include_mfcc
        self.on_error = on_error

    # -- sklearn API ----------------------------------------------------------
    def fit(self, X=None, y=None):
        """Stateless except for the (deterministic) output schema."""
        self.metric_keys_ = _ordered_metric_keys(
            self.include_categories, self.include_mfcc)
        self.feature_names_out_ = self._build_feature_names()
        self.n_features_out_ = len(self.feature_names_out_)
        return self

    def transform(self, X) -> np.ndarray:
        if not hasattr(self, "feature_names_out_"):
            self.fit(X)
        paths = self._as_path_list(X)
        rows = [self._features_for(p) for p in paths]
        return np.asarray(rows, dtype=np.float64)

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        if not hasattr(self, "feature_names_out_"):
            self.fit()
        return np.asarray(self.feature_names_out_, dtype=object)

    # -- internals ------------------------------------------------------------
    def _build_feature_names(self) -> List[str]:
        for a in self.aggregations:
            if a not in self._AGG_CHOICES:
                raise ValueError(
                    f"unknown aggregation {a!r}; choose from {self._AGG_CHOICES}")
        names: List[str] = []
        for key in self.metric_keys_:
            for agg in self.aggregations:
                names.append(f"{key}__{agg}")
        names += ["vrp_n_cells", "vrp_n_cycles"]
        return names

    @staticmethod
    def _as_path_list(X) -> List[str]:
        if isinstance(X, (str, os.PathLike)):
            return [os.fspath(X)]
        return [os.fspath(p) for p in X]

    def _vrp_df_for(self, path: str) -> Optional[pd.DataFrame]:
        """Return the per-cell VRP DataFrame for one input (audio → analyse,
        no disk; .csv/.parquet → read). None if analysis produced no cells."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".parquet":
            return read_parquet(path)
        if ext == ".csv":
            return read_vrp(path)
        # Treat everything else as audio.
        from voicemap.analyzer import VoiceMapAnalyzer
        from voicemap.config import VoiceMapConfig
        cfg = self.config or VoiceMapConfig()
        analyzer = VoiceMapAnalyzer(cfg)
        try:
            _, _, grouped = analyzer.analyze_and_output_vrp_auto(
                path, return_df=True, plot_mode="none",
                export_plots=False, write_disk=False)
            return grouped
        except Exception:
            return None

    def _features_for(self, path: str) -> List[float]:
        df = self._vrp_df_for(path)
        n_feat = len(self.feature_names_out_)
        if df is None or len(df) == 0:
            if self.on_error == "raise":
                raise ValueError(f"no analysable cycles in {path}")
            return [np.nan] * n_feat

        weights = (df["Total"].to_numpy(dtype=np.float64)
                   if "Total" in df.columns else np.ones(len(df)))
        out: List[float] = []
        for key in self.metric_keys_:
            col = (df[key].to_numpy(dtype=np.float64)
                   if key in df.columns else np.full(len(df), np.nan))
            wmean, wstd = _weighted_mean_std(col, weights)
            for agg in self.aggregations:
                if agg == "mean":
                    out.append(wmean)
                elif agg == "std":
                    out.append(wstd)
                else:
                    finite = col[np.isfinite(col)]
                    if finite.size == 0:
                        out.append(np.nan)
                    elif agg == "min":
                        out.append(float(finite.min()))
                    elif agg == "max":
                        out.append(float(finite.max()))
                    else:  # median
                        out.append(float(np.median(finite)))
        out.append(float(len(df)))                       # vrp_n_cells
        out.append(float(weights.sum()))                 # vrp_n_cycles
        return out
