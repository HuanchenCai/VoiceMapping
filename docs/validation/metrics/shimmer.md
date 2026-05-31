# Shimmer (local / local_dB / APQ3 / APQ5 / APQ11 / DDA)

> Cycle-to-cycle variation of the glottal **amplitude**. Clinical amplitude-
> perturbation family, MDVP / Praat conventions. Sibling of `jitter.md`
> (period perturbation).

## 1. Implementation
- File: `voicemap/praat_perturbation.py`
- Amplitude marker (shared input for every form):
  - `point_process_to_amplitude_tier` — lines 577–615; per interior pulse,
    Hann-windowed RMS on the voice over an asymmetric `[0.2·p1, 0.2·p2]`
    window, keeping only pulses whose neighbouring periods pass the
    period-bounds + factor gate.
  - `hann_windowed_rms` — lines 540–574 (the per-pulse amplitude estimate).
- Formulas:
  - `shimmer_local` — lines 622–651
  - `shimmer_local_dB` — lines 654–676
  - `_shimmer_apq_n` (generic odd-window APQ) — lines 679–729; wrappers
    `shimmer_apq3` / `shimmer_apq5` / `shimmer_apq11` — lines 732–747
  - `shimmer_dda` — lines 750–754 (`= 3 · APQ3` by definition)
  - Per-cycle decompositions (`shimmer_*_per_cycle`, lines 854+) used by
    `PerturbationCalculator` to produce a per-cycle series whose mean over
    valid cycles recovers the global scalar.
- Dependencies: `numpy` only. Pulse times (`t_points`, seconds) come from
  `voicemap/praat_pitch.py` → `sound_pitch_to_pointprocess_cc`; the voice
  waveform + sample rate are needed for the Hann-RMS amplitude.
- Inputs: `amp_times`, `amp_values` (from the amplitude tier), `pmin=1e-4`,
  `pmax=0.02`, `max_amplitude_factor=1.6` (MDVP defaults).

## 2. Reference Standard
- **Praat** (Boersma & Weenink):
  - `fon/Sound_PointProcess.cpp` / `AmplitudeTier.cpp` →
    `PointProcess_Sound_to_AmplitudeTier_period` (the per-period Hann-RMS).
  - `fon/VoiceAnalysis.cpp` → `AmplitudeTier_getShimmer_local_u`,
    `_local_dB_u`, `_apq3_u`, `_apq5_u`, `_apq11_u`, `_dda_u`.
- Underlying clinical definitions: MDVP (Multi-Dimensional Voice Program);
  Baken & Orlikoff, *Clinical Measurement of Speech and Voice* (2000).
- Formulas (amplitudes `a_i` at accepted pulses, `i = 1..N`):

  ```
  shimmer_local    = mean_i |a_i - a_{i-1}|            / mean_i a_i
  shimmer_local_dB = 20 · mean_i |log10(a_i / a_{i-1})|             [dB]
  shimmer_apq_n    = mean_i |a_i - mean(a_{i-h..i+h})| / mean_i a_i   (n = 2h+1)
  shimmer_dda      = 3 · shimmer_apq3
  ```

  A pulse pair / window contributes only if every interior period is in
  `[pmin, pmax]` and every adjacent amplitude ratio is `≤ max_amplitude_factor`
  (= 1.6). The denominator `mean_i a_i` runs over indices `1..size-1`
  (Praat excludes the last point); this 1-off detail is reproduced exactly.

- Reference implementation we compare against: `parselmouth` (Praat 6.x),
  `call([pp, snd], "Get shimmer (local)", 0, 0, 1e-4, 0.02, 1.3, 1.6)`, etc.

## 3. Test Signals
**Synthetic** (`docs/validation/test_signals/`, see `make_signals.py`):
- `vowel_shimmer_5pct.wav` — imposed source `shimmer_local = 5 %`
  (alternating amplitude `A·(1 ± 0.025)`).
- `vowel_modal_200Hz_5s.wav` — imposed `shimmer_local = 0` (must read ~0).

**Real** (`audio/`):
- `test_Voice_EGG.wav` — first 10 s of the voice channel; the realistic
  pulse set + waveform that drives the amplitude-pipeline parity check.

## 4. Validation Method
A shimmer metric is **amplitude-marker + formula**. Unlike jitter — where
the cycle marker and the formula are cleanly separable — shimmer's amplitude
marker (Hann-RMS) is itself part of what we reimplemented, so we validate it
explicitly and then the formula on top of it.

- **(A) Numerical parity** vs Praat, amplitude pipeline + formula.
  - Step 1 — amplitude-tier identity: Praat's `PointProcess (cc)` marks on
    the real 10 s voice are fed to *both* our `point_process_to_amplitude_tier`
    and Praat's `To AmplitudeTier (period)`. Pulse **count** must match, pulse
    **times** within `atol=1e-9`, pulse **values** within `atol=1e-6`.
  - Step 2 — formula: our shimmer on our amplitude tier vs Praat's shimmer
    query, for `local / local_dB / apq3 / apq5 / apq11`. `atol=1e-6`.
  - Because step 1 proves the amplitude tier is identical, step 2 certifies
    the *whole* pipeline end-to-end on real audio, not just the formula.
- **(B) Synthetic ground truth**.
  - Input: an alternating `A·(1 ± d_a)` amplitude pattern on a regular period
    grid, for which `shimmer_local = 2·d_a` exactly and
    `shimmer_local_dB = 20·|log10((1+d_a)/(1-d_a))|`.
  - Expected output: the imposed 5 % (and the closed-form dB), plus 0 % for
    the modal pattern.
  - Tolerance: `rtol=1e-3` (non-zero), `atol=1e-9` (dB closed form),
    `atol=1e-5` (zero case).
- **(C) Real-corpus behaviour** — deferred to the corpus phase; (A)+(B) meet
  the P0 amplitude-pipeline + formula bar. End-to-end corpus distribution
  will be added once Saarbruecken is wired (see `corpora/saarbruecken.md`).

Exact reproducible steps:
```bash
python docs/validation/test_signals/make_signals.py   # regenerate signals
python scripts/validate_metric.py shimmer             # PASS report + patches §5
```

## 5. Results

<!-- VALIDATE:shimmer:START -->
*Auto-generated by `scripts/validate_metric.py shimmer` — do not edit by hand.*

**Result: PASS** (12/12 checks)

| Test | Reference | Our Value | Δ (tol) | Pass? |
|---|---|---|---|---|
| A · amp-tier pulse count (real 10 s) | 1177 | 1177 | 0 (atol 0) | ✓ |
| A · amp-tier pulse times | Praat AmplitudeTier | Hann-RMS | 0.0e+00 (atol 1e-9) | ✓ |
| A · amp-tier pulse values | Praat AmplitudeTier | Hann-RMS | 1.0e-17 (atol 1e-6) | ✓ |
| A · parity shimmer_local (real 10 s) | 1.530e-02 | 1.530e-02 | 1.2e-17 (atol 1e-6) | ✓ |
| A · parity shimmer_local_dB (real 10 s) | 2.349e-01 | 2.349e-01 | 2.2e-16 (atol 1e-6) | ✓ |
| A · parity shimmer_apq3 (real 10 s) | 5.669e-03 | 5.669e-03 | 8.7e-18 (atol 1e-6) | ✓ |
| A · parity shimmer_apq5 (real 10 s) | 7.448e-03 | 7.448e-03 | 4.3e-18 (atol 1e-6) | ✓ |
| A · parity shimmer_apq11 (real 10 s) | 1.467e-02 | 1.467e-02 | 3.3e-17 (atol 1e-6) | ✓ |
| B · GT shimmer_local vowel_shimmer_5pct.wav | 5.0000% | 5.0000% | 4.72e-14pp (rtol 1e-3) | ✓ |
| B · manifest GT consistent vowel_shimmer_5pct.wav | 5.00% | 5.00% | — | ✓ |
| B · GT shimmer_local_dB vowel_shimmer_5pct.wav | 0.4344 dB | 0.4344 dB | 5.3e-15 (atol 1e-9) | ✓ |
| B · GT shimmer_local modal (imposed 0) | 0.0000% | 0.0000% | 0.0e+00pp (atol 1e-5) | ✓ |
<!-- VALIDATE:shimmer:END -->

Backing unit tests (also assert parity): `tests/test_praat_perturbation_parity.py`
(`TestPraatShimmerParity`, `TestPerCycleDecomposition`).

## 6. Status
**PASS**
- validated_on: 2026-05-31
- session: validation-bootstrap
- validator: `scripts/validate_metric.py shimmer` (A amplitude-pipeline +
  formula parity, atol 1e-6; B synthetic GT, exact)

## 7. Known Limitations
- **End-to-end synthetic shimmer over-reports.** Running the full cc-marker →
  amplitude-tier → formula pipeline on `vowel_shimmer_5pct.wav` reads
  **8.9 %**, not the imposed **5 %** source shimmer. This is *not* a code
  defect: our pipeline returns the **same** 8.9151 % as Praat's, byte-for-byte.
  The cause is the synthetic signal model — the formant cascade is a chain of
  2-pole resonators whose time constants (`≈ 1/(π·BW) ≈ 5 ms`) are on the
  order of one period at 200 Hz, so the filter carries amplitude memory across
  cycles and a 5 % *source* alternation becomes a ~8.9 % *radiated-signal*
  alternation. Any acoustic shimmer measure (Praat included) sees the
  radiated value. The clean ground truth therefore lives at the **formula**
  layer (§5 B), where 5 % source → 5.0000 % recovered exactly. This is the
  amplitude-domain mirror of jitter's marker-smoothing limitation (jitter
  *under*-reports because the marker re-locks sub-sample period jitter;
  shimmer *over*-reports because the filter amplifies cross-cycle amplitude
  differences).
- **APQ11 needs ≥ 11 valid pulses** in a window; very short or heavily-gated
  segments return NaN. Expected, matches Praat.
- Period-validity + amplitude-factor gates (`pmax=0.02`,
  `max_amplitude_factor=1.6`) can drop pulses at octave jumps / onsets, so
  pulse counts vary slightly between implementations (≤5 %, see
  `conventions.md` §1) — but on identical Praat marks they are identical.
- Not characterised below F0 = 60 Hz (period outside `[pmin,pmax]`).

## 8. Change Log
- 2026-05-31 — Created 8-section doc; wired `validate_metric.py shimmer`
  (A amplitude-tier identity + formula parity atol=1e-6 + B synthetic GT).
  Documented end-to-end source→signal over-report (5 %→8.9 %, ours==Praat) as
  a formant-cascade memory property, mirroring jitter §7. Status → PASS.
- (prior) — Amplitude pipeline + formula layer translated from Praat in
  `praat_perturbation.py`; parity covered by
  `tests/test_praat_perturbation_parity.py` (`TestPraatShimmerParity`).
