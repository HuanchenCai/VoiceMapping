# VoiceMap Reproducibility

> How to reproduce every VoiceMap analysis result, validation pass, and figure
> from a clean machine. Companion to `docs/methodology.md` (what the algorithms
> are) and `docs/ml_schema.md` (the output contract).

VoiceMap is an **offline, deterministic** analyzer: the same input file + the
same config produce the same Voice Range Profile, on the same platform, every
run. This document pins the environment, the commands, and the (small,
documented) sources of cross-platform numerical variation.

## 1. Environment

Python **3.11 or 3.12** (CI matrix; 3.10 works locally, 3.14 has no
`parselmouth` wheel yet).

```bash
# Runtime only (GUI + CLI analysis)
conda create -n voicemap python=3.11
conda activate voicemap
pip install -r requirements.txt

# To additionally reproduce the metric validation (Praat / librosa / openSMILE
# parity), install the reference tools on top:
pip install -r requirements-validation.txt
```

Core runtime deps (`requirements.txt`): numpy, scipy, pandas, soundfile,
matplotlib, scikit-learn, numba. Optional: openpyxl (Excel), statsmodels
(LOWESS overlay), pywin32 / tkinterdnd2 (Windows GUI niceties),
praat-parselmouth (only the parity tests need it). Parquet export needs
`pyarrow`.

Validation deps (`requirements-validation.txt`) pin the reference tools so
parity numbers are stable: `praat-parselmouth>=0.4.7`, `librosa>=0.10`,
`opensmile>=2.4`, `nolds==0.5.2` (0.6.x eagerly loads a dataset and crashes on
3.11).

## 2. One-command reproductions

All commands run from the repo root.

| Goal | Command | Expected |
|---|---|---|
| **Metric correctness** (Praat/librosa parity on the bundled real fixture) | `python tests/validate_params.py audio/test_Voice_EGG.wav` | `PASS=49  WARN=0  FAIL=0` |
| **Per-metric validation harness** (A/B/C evidence) | `python scripts/validate_metric.py <metric>` | exit 0 = within tolerance |
| **End-to-end output regression** (3 analysis modes vs committed baseline) | `python scripts/e2e_regression.py` | `0 drifted column(s) across 3 modes` |
| **Regenerate synthetic ground-truth signals** | `python docs/validation/test_signals/make_signals.py` | 12 WAVs + manifest |
| **Performance scaling** (wall + peak RSS) | `python scripts/benchmark.py` | O(N) wall, table |
| **Batch stability / leak** | `python scripts/batch_stability.py --runs 30` | 0 crash / 0 NaN / no leak |
| **Chunked-vs-whole parity** | `python scripts/compare_chunked_vs_whole.py audio/test_Voice_EGG.wav 60` | per-column median rel-diff |
| **Regenerate the ML schema doc** | `python scripts/gen_ml_schema.py` | `docs/ml_schema.md` |

The committed regression baseline lives at
`docs/validation/regression/e2e_baseline.json`; `python scripts/e2e_regression.py
--update` regenerates it after an *intended* formula change.

## 3. Determinism by design

- **K-means** (EGG-shape `Cluster 1..5`, phonation `cPhon 1..5`) uses
  `random_state=0` and the empty-cluster rescue is deterministic — same cycles
  → same labels.
- The **only stochastic element** is the CPP tie-break dither
  (`cpp_dither_amp=1e-6`, ≈0.03 dB), far below any reporting precision and
  absorbed by the validation tolerances.
- No wall-clock / RNG seeding leaks into results (timestamps appear only in
  output *filenames*, never in metric values).
- The **chunked path** (`analyze_and_output_vrp_chunked`, auto-selected above
  `config.chunk_threshold_s`) is deterministic too, and matches the whole-signal
  path to ~1 % on jitter/shimmer (per-chunk pitch tracking; see
  `docs/validation/phase4.md`); all other metrics match to <0.5 %.

## 4. Cross-platform

- **Windows**: the reference platform — `validate_params` 49 PASS,
  `e2e_regression` 0 drift.
- **Linux**: CI (`.github/workflows/validate.yml`, ubuntu, Python 3.11/3.12)
  regenerates the signals and runs the harness + Praat-parity unit tests on
  every push/PR. Running `e2e_regression.py` there against the Windows-built
  baseline confirms Win↔Linux agreement within tolerance.
- **macOS**: not yet exercised (no machine) — expected to match within
  tolerance.
- **Bit-identical (±1e-9) across platforms is *not* guaranteed**: numba and
  BLAS reductions reorder floating-point sums differently per platform/CPU. The
  practical guarantee is **tolerance-based** (e2e mean rtol 2e-2, atol 1e-3;
  per-metric tolerances in each `docs/validation/metrics/*.md`). Within one
  platform, results are exactly reproducible run-to-run.

## 5. What "reproducible" covers

1. **Metric values** — deterministic given (input, config, platform); validated
   against Praat / librosa / openSMILE and synthetic ground truth.
2. **The VRP output schema** — frozen at v1.0.0 (`docs/ml_schema.md`,
   `docs/api_stability.md`).
3. **The validation evidence** — every metric's parity/GT test is a committed
   script; re-running reproduces the PASS/WARN status recorded in
   `docs/validation/log.md`.
