# -*- coding: utf-8 -*-
"""VoiceMap ML demo — voice → features → classifier (Phase 6.5).

End-to-end demonstration of the scikit-learn integration: synthesise a small
labelled corpus of three phonation types, turn each recording into a
fixed-length feature vector with ``voicemap.ml.VoiceFeatureExtractor``, and
train a classifier in a standard sklearn ``Pipeline``.

The corpus is generated on the fly (the bundled 12 validation signals are
single unique test cases, not a multi-sample classification set), so this demo
is fully self-contained and reproducible — no external corpus needed.

Run as a script::

    python examples/ml_demo.py            # default 8 samples / class
    python examples/ml_demo.py 12         # 12 / class

Or open in Jupyter / VS Code: the ``# %%`` markers make each block a cell.
"""

# %% [markdown]
# # VoiceMap ML demo
# **voice → features → classifier**, using `VoiceFeatureExtractor` in a sklearn
# pipeline. Three synthetic phonation classes:
# - **modal** — clean periodic vowel (high HNR, ~0 jitter/shimmer)
# - **breathy** — additive noise (low HNR / NHR up, CPP down)
# - **rough** — elevated jitter + shimmer
#
# Each class has several samples with randomised F0 and within-class
# perturbation, so the classes are separable but not trivial.

# %%
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "docs", "validation", "test_signals"))

import make_signals as ms           # noqa: E402  synth_vowel / normalize / SR
from voicemap.ml import VoiceFeatureExtractor  # noqa: E402
from voicemap.config import VoiceMapConfig      # noqa: E402
from voicemap.logger import setup_logger        # noqa: E402

import logging                                   # noqa: E402
setup_logger("voicemap", level=logging.WARNING)  # quiet per-file analysis logs

N_PER_CLASS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
DURATION_S = 2.0


# %% [markdown]
# ## 1. Synthesise a labelled corpus
# `synth_vowel(dur, f0_inst, jitter_frac, shimmer_frac, snr_db, seed)` renders a
# source-filter vowel. We vary F0 and the class-defining parameter per sample.

# %%
def _make_class(label: str, n: int, out_dir: str):
    """Write `n` randomised mono WAVs for one phonation class. Returns paths."""
    rng = np.random.default_rng({"modal": 1, "breathy": 2, "rough": 3}[label])
    paths = []
    for i in range(n):
        f0 = float(rng.uniform(150.0, 260.0))          # within-class F0 spread
        if label == "modal":
            jit, shim, snr = 0.0, 0.0, None
        elif label == "breathy":
            jit, shim, snr = 0.0, 0.0, float(rng.uniform(6.0, 14.0))
        else:  # rough
            jit = float(rng.uniform(0.02, 0.04))
            shim = float(rng.uniform(0.08, 0.13))
            snr = None
        y = ms.synth_vowel(DURATION_S, (lambda c: (lambda t: c))(f0),
                           vowel="neutral", jitter_frac=jit,
                           shimmer_frac=shim, snr_db=snr, seed=1000 + i)
        path = os.path.join(out_dir, f"{label}_{i:02d}_{int(f0)}Hz.wav")
        sf.write(path, ms.normalize(y), ms.SR)
        paths.append(path)
    return paths


corpus_dir = tempfile.mkdtemp(prefix="voicemap_ml_demo_")
classes = ["modal", "breathy", "rough"]
paths, labels = [], []
for c in classes:
    cp = _make_class(c, N_PER_CLASS, corpus_dir)
    paths += cp
    labels += [c] * len(cp)
y = np.array(labels)
print(f"corpus: {len(paths)} files, {len(classes)} classes "
      f"({N_PER_CLASS}/class) in {corpus_dir}")


# %% [markdown]
# ## 2. Extract features
# One fixed-length vector per recording. These are mono (no EGG), so
# `analysis_mode='acoustic'` — EGG-category features come out 0 and carry no
# information here (the classifier simply ignores them).

# %%
cfg = VoiceMapConfig()
cfg.analysis_mode = "acoustic"
extractor = VoiceFeatureExtractor(config=cfg)
X = extractor.fit_transform(paths)
feat_names = extractor.get_feature_names_out()
print(f"feature matrix: {X.shape}  ({len(feat_names)} features/recording)")
print(f"finite fraction: {np.isfinite(X).mean():.3f}")


# %% [markdown]
# ## 3. Train + cross-validate a classifier
# Standard sklearn pipeline: median-impute → standardise → logistic regression.
# With few samples and many features we report stratified k-fold accuracy.

# %%
from sklearn.pipeline import Pipeline          # noqa: E402
from sklearn.impute import SimpleImputer        # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_score  # noqa: E402

clf = Pipeline([
    ("impute", SimpleImputer(strategy="median")),
    ("scale", StandardScaler()),
    ("logreg", LogisticRegression(max_iter=2000, C=1.0)),
])
n_splits = min(5, N_PER_CLASS)
cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
scores = cross_val_score(clf, X, y, cv=cv, scoring="accuracy")
print(f"{n_splits}-fold CV accuracy: {scores.mean():.3f} ± {scores.std():.3f}")


# %% [markdown]
# ## 4. Which features separate the classes?
# Univariate ANOVA F-score on the informative features. EGG-category features
# are constant (0) here — mono recordings have no EGG channel — so we drop
# zero-variance columns first (otherwise the F-score is undefined for them).

# %%
from sklearn.feature_selection import f_classif  # noqa: E402

Xf = SimpleImputer(strategy="median").fit_transform(X)
nonconst = Xf.std(axis=0) > 0
n_const = int((~nonconst).sum())
Xf = StandardScaler().fit_transform(Xf[:, nonconst])
names_nz = feat_names[nonconst]
F, _ = f_classif(Xf, y)
order = np.argsort(np.nan_to_num(F))[::-1][:12]
print(f"({n_const} constant features dropped — EGG metrics are 0 in mono mode)")
print("Top discriminative features (ANOVA F):")
for idx in order:
    print(f"  {names_nz[idx]:<28} F={F[idx]:8.1f}")

# %%
print("\nDemo complete. VoiceFeatureExtractor → sklearn Pipeline works "
      "end-to-end on a labelled corpus.")
