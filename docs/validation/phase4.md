# Phase 4 — End-to-end & performance

> Validates the analyzer as a whole (not per-metric): output stability across
> the three analysis modes, performance scaling, cross-platform reproducibility,
> and batch robustness. Run on `audio/test_Voice_EGG.wav` + the 12 synthetic
> signals (the only assets on hand — see limitations).

## 4.1 — Three-mode end-to-end CSV regression ✅
- Harness: `scripts/e2e_regression.py`; baseline
  `docs/validation/regression/e2e_baseline.json`.
- Runs the full analyzer in each mode on short in-memory fixtures and reduces
  the VRP to a per-column signature (`n_nonzero`, `mean`), compared to the
  committed baseline (mean rtol 2e-2 + atol 1e-3; categorical label columns on
  cell-count only).
  - **mono** — synthetic modal vowel, `analysis_mode='acoustic'`
  - **stereo+EGG** — 5 s slice of `test_Voice_EGG.wav`, `analysis_mode='full'`
  - **stereo+no-EGG** — voice ch1 + seeded noise ch2, `analysis_mode='acoustic'`
- Result: re-run reproduces the baseline — **all columns within tolerance, 0
  drift** across the 3 modes (231 columns total after the MPT / VoicingRatio /
  DUV removal). Any future metric-formula change that shifts a column mean > 2 %
  turns this red; `--update` regenerates the baseline after an intended change.

## 4.2 — Performance benchmark ✅
- Harness: `scripts/benchmark.py` (numba warm-up discarded; peak RSS sampled at
  50 ms). Stereo+EGG (heaviest mode), Windows / `fonadyn` env.

  | audio (s) | wall (s) | wall/audio | Δram (MB) | peak (MB) | cycles | ms/cycle |
  |---|---|---|---|---|---|---|
  | 10 | 3.22 | 0.32 | 173 | 435 | 1 240 | 2.60 |
  | 30 | 8.89 | 0.30 | 598 | 860 | 4 214 | 2.11 |
  | 60 | 18.20 | 0.30 | 1 224 | 1 504 | 10 103 | 1.80 |

- **Wall time is linear O(N)** — ~0.30× real-time (≈ 3× faster than real-time);
  the 60 s/10 s `wall/audio` ratio is 0.94× (fixed overhead amortises, so it is
  slightly *super*-linear in throughput). ms/cycle falls 2.6 → 1.8 for the same
  reason.
- **Memory scaled linearly** — ~20 MB working-set per audio-second (peak 1.5 GB
  at 60 s → a 1-hour clip would peak ~70–90 GB). **BLOCKER for the batch /
  long-recording use case; being fixed, not accepted.**
- **Root cause (profiled per stage):** it is NOT one hog — *several* frame-based
  calculators each materialise full-length `(n_frames × nfft)` FFT/frame
  matrices (≈1 GB each at 60 s, linear in length). At 60 s the peak was
  `SpectralMomentsCalculator` (it holds ~10 simultaneous `(n_frames × 2049)`
  matrices — `mag/psd/log_mag/mag_db/norm_psd/cum` + `diff^2/3/4` for the
  moments). The others of the same shape: HNR, MFCC, Burg formants, Formant
  extras (SPR), EGG-shape Cluster.
- **Fix:** process frames in fixed-size blocks (peak ≈ `BLOCK × nfft`,
  independent of audio length) — math identical, guarded by the 4.1 e2e
  baseline (0 drift).
  - Done (BLOCK 512–1024, all e2e 0-drift): SpectralMoments, HNR, MFCC,
    FormantExtras-SPR, FormantCalculator-SFE. (Burg formants were already
    chunked.) **60 s peak 1522 → 797 MB (−48 %).** The peak has moved to the
    SPL/Clarity/CPP stage.
- **Diminishing returns + rising risk on the tail.** The next peak is
  `ClarityCalculator` (NSDF) — also a per-window FFT matrix, but it is complex
  (octave correction + fallback) and feeds F0/MIDI, which drives all cell
  binning, so block-processing it is riskier. Beyond it the per-cycle DFT /
  entropy / perturbation calculators are smaller.
- **The persistent floor is the real wall for 1 hour.** Even with every
  transient FFT capped, the audio is held as float64 (+ filtered copies) and
  the per-cycle dict is O(N), so a 1-hour clip still needs several GB and the
  summed transients still scale. **Block-processing reduces the peak ~2× but
  does NOT bound 1-hour memory.**
- **Definitive fix = chunked pipeline (IMPLEMENTED).**
  `VoiceMapAnalyzer.analyze_and_output_vrp_chunked` (+ `_compute_metrics_chunked`,
  + a `skip_clustering` hook on `calculate_all_metrics`). Reads the audio in
  N-second blocks (with overlap so per-cycle metrics see full context + filters
  settle), runs the existing per-cycle calculators per block with clustering
  deferred, keeps the cycles whose onset is in the block's core, and fits the
  two K-means clusterings ONCE on the accumulated features at the end (the
  "cluster once at the end" insight removes the cross-chunk label problem).
  Existing whole-signal path untouched (opt-in).
  - **Memory bounded:** the working set is flat in audio length — +629 / +613 /
    +634 MB at 120 / 300 / 600 s (chunk_s=60), vs whole-signal +593 (60 s) →
    +1717 MB (180 s, linear). 180 s peak 2024 → 1074 MB at the same wall time
    (chunking overhead negligible). A real 1-hour run projects to ~1.2–1.5 GB
    (≈ one chunk + the ~400 MB accumulated per-cycle table) vs ~35 GB.
  - **Output parity:** cell grid + cycle count match (510 vs 509 cells, 12523 vs
    12494 cycles); all per-cycle metrics match the whole-signal path **except
    jitter/shimmer** (median ~15 % diff) and GNE (~6 %). Jitter/shimmer
    decompose a *window-global* Praat scalar (per-cycle = local |ΔT| ÷
    window-mean-period), so a chunk window ≠ the whole window — inherent, since
    making it chunk-invariant would change the (Praat-validated) definition.
    For 1-hour recordings the whole-signal path cannot run anyway, so chunked
    per-window perturbation is the natural/only option; larger chunks shrink the
    gap. A 2-pass global-mean prepass could make it exact if required.

## 4.3 — Cross-platform reproducibility ⚠ (partial)
- Determinism by design: K-means uses `random_state=0`; the only stochastic
  element is the CPP tie-break dither (`cpp_dither_amp=1e-6`, ≈0.03 dB), which
  the 4.1 tolerance absorbs.
- **Windows**: verified (4.1 re-run, 0 drift). **Linux**: the CI (`validate.yml`,
  ubuntu) can run `e2e_regression.py` against the Windows-built baseline to
  confirm Win↔Linux agreement within tolerance — wiring tracked as a follow-up.
- **macOS**: no machine available — deferred.
- The PLAN's ±1e-9 bit-identical target across platforms is **not** met (numba /
  BLAS reductions differ across platforms); the tolerance-based e2e check is the
  practical cross-platform guarantee.

## 4.4 — Batch stability / leak ✅
- Harness: `scripts/batch_stability.py` — N repeated analyses cycling through
  the 12 synthetic + the real fixture, asserting no crash and no NaN/Inf in any
  numeric VRP column, tracking RSS (with `gc.collect()` per run) for leaks.
- Result (30 runs): **0 crashes, 0 NaN/Inf**. RSS warms 212 → 262 MB over the
  first ~half (numba / matplotlib module caches), then **plateaus** — 2nd-half
  growth +1 MB ⇒ no leak. PASS. (The leak heuristic measures the second-half
  slope so cache warm-up is not mistaken for a leak.)
- Limitation: no 100+ **distinct-voice** corpus on hand — coverage is breadth
  (every fixture, all three mode paths) × repetition, not 100 unique voices.
  Run `--runs 100` for the PLAN's count; a real multi-voice corpus (e.g. SVD)
  would strengthen this.

## Status
- 4.1 PASS · 4.2 PASS · 4.3 partial (Win ok; Linux via CI follow-up; Mac
  deferred) · 4.4 PASS.
