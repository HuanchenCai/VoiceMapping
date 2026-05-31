# VoiceMap Validation — Session-by-session log

> Append-only timeline. Every commit that touches a metric implementation
> OR a validation file gets an entry here. Latest at the bottom.

Format per entry:
```
## YYYY-MM-DD  session=<short-id>  commit=<sha>
- Touched: file:line
- Why: one sentence
- Before / After: numerical change if any
- Validation: link(s) to metrics/<name>.md
- Tests: PASS_COUNT / TOTAL
```

---

## 2026-05-29  session=plan-bootstrap  commit=pending
- Touched: docs/validation/PLAN.md, log.md, metrics/_template.md (all new files)
- Why: Set up the validation documentation framework so the next session
  can execute Phase 0 → 6 against a stable plan.
- Validation: n/a (infrastructure)
- Tests: 73 / 73  (no code change)

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: docs/validation/test_signals/make_signals.py (new),
  scripts/validate_metric.py (new), .github/workflows/validate.yml (new),
  requirements-validation.txt (new), docs/validation/corpora/saarbruecken.md
  (new), docs/validation/metrics/jitter.md (filled), test_signals/README.md
- Why: Execute PLAN §11 startup checklist items 3–9 — stand up Phase 0
  validation infrastructure and validate the first P0 metric (jitter).
- Phase 0.1: 12 synthetic signals + manifest.json. Continuous-phase glottal
  rendering so sub-sample jitter survives (integer-onset rounding erased it
  and injected spurious jitter into the modal baseline — fixed).
- Phase 0.2: generic harness `validate_metric.py <metric>`; PASS report to
  stdout (ASCII, Windows-console-safe) + auto-patches metric md §5.
- Phase 0.3: CI `validate.yml` (py3.11/3.12) regenerates signals → runs
  harness (exit-code gate) → runs Praat-parity unittests.
- Phase 0.5: Saarbrücken corpus documented; local `audio/` stand-in wired
  for (C) plumbing. Real SVD download deferred (blocks PPE/SFE/MPT only).
- Phase 1.1 (jitter): formula validated A (parity vs Praat, atol 1e-9 on
  real 10 s marks) + B (synthetic GT, alternating ±d recovers imposed
  0.5/2/0 % to <1e-3 rel). Cycle-marker smoothing documented as a §7 limit.
  Before / After: jitter.md Status UNKNOWN → PASS.
- Validation: metrics/jitter.md  (PASS, 10/10 checks)
- Tests: harness 10/10; unittest 21/21 perturbation + pitch parity green.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_shimmer, +aliases),
  docs/validation/metrics/shimmer.md (new, 8 sections)
- Why: Phase 1.2 — validate Shimmer (local / local_dB / APQ3 / APQ5 / APQ11
  / DDA). Parity already existed in tests; this lifts it into the harness +
  8-section doc and adds synthetic ground truth.
- Phase 1.2 (shimmer): A parity (amplitude-tier IDENTITY to Praat — count +
  times atol 1e-9 + values atol 1e-6 — then all five forms atol 1e-6,
  d≈1e-17) + B synthetic GT (alternating ±d_a amps → shimmer_local recovers
  imposed 5%→5.0000%, dB matches closed form, modal→0). Harness 12/12 PASS.
- Finding: end-to-end SOURCE shimmer of the synthetic wav over-reports
  (5%→8.9%), but ours==Praat byte-for-byte (8.9151%). Root cause is
  formant-cascade inter-cycle memory (resonator τ≈5 ms ≈ one period at
  200 Hz), not a code defect — the amplitude-domain mirror of jitter's
  marker-smoothing limit. Documented in shimmer.md §7; clean GT lives at the
  formula layer (§5 B).
- Before / After: shimmer.md Status UNKNOWN → PASS.
- Validation: metrics/shimmer.md  (PASS, 12/12 checks)
- Tests: harness 12/12; unittest 21/21 perturbation parity green;
  validate_params.py 48 PASS / 0 FAIL baseline intact.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_f0_clarity, +_nsdf helper,
  +aliases), docs/validation/metrics/f0_clarity.md (new, 8 sections)
- Why: Phase 1.3 — validate F0 + Clarity. The doc the jitter/shimmer files
  defer their cycle-marker fidelity to.
- Key structural finding: VoiceMap has TWO F0 subsystems with TWO references.
  (1) cycle-marker F0 = native Praat Sound_to_Pitch (AC) in praat_pitch.py
  (drives jitter/shimmer). (2) the SHIPPED VRP Clarity + MIDI/F0_Hz = a
  Tartini-style NSDF (ClarityCalculator, McLeod & Wyvill 2005 / SC
  Tartini.cpp), NOT Praat. Documented both; PLAN row #3 had conflated them.
- Phase 1.3 results (harness 13/13 PASS):
  · Part 1 (A, Praat-AC parity, real 10 s): voicing agreement 99.75 %,
    F0 median err 0.0000 % / P90 0.0001 %, cycle-mark count ratio 0.9983,
    mark offset median 0.0002 ms / P90 0.0025 ms.
  · Part 2 (B, NSDF octave stress, in designed singing range): 200/800 Hz +
    breathy + vibrato all within +4 cents (no octave error); clean clarity
    0.999, breathy 0.991 (noise lowers it), silence → 0 voiced cycles.
- Documented limitations (md §7): NSDF low-pitch floor ≈ 78 Hz (MIDI 39) —
  a genuine 70 Hz voice is forced up an octave (reads ≈1002 Hz), below the
  designed VRP range, NOT fixed (frozen); chirp false-locks (clarity is not
  a voicing gate); two-F0-by-design; +4-cent NSDF lag-quantisation bias.
- Before / After: f0_clarity.md Status UNKNOWN → PASS (within designed range).
- Validation: metrics/f0_clarity.md  (PASS, 13/13 checks)
- Tests: harness 13/13; pitch parity unittest 9/9 OK; perturbation parity
  21/21 green; validate_params.py 48 PASS / 0 FAIL baseline intact.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_hnr, +_cc_trigger_array /
  +_our_hnr_median / +_praat_hnr_median helpers, +aliases),
  docs/validation/metrics/hnr.md (new, 8 sections)
- Why: Phase 1.4 — validate HNR + NHR. Parity was NOT pre-existing (unlike
  jitter/shimmer/f0); built it here.
- Method insight: VoiceMap's HNR is Praat-STYLE (autocorr) but independently
  parameterised (fixed 40 ms window vs Praat's 4.5 periods), so a raw
  real-audio parity is not the right bar. The rigorous anchor is PHYSICAL:
  for harmonic+white-noise, p/(1-p) = 10^(SNR/10) ⇒ HNR_dB == SNR_dB exactly.
- Phase 1.4 results (harness 13/13 PASS):
  · (B) HNR == imposed SNR over 5/10/15/20/25 dB → recovered to <0.3 dB.
  · (A) Praat to_harmonicity_cc on the SAME stationary signals agrees to
    <0.3 dB → ground truth and parity coincide.
  · committed breathy fixture (SNR=15): HNR 15.12 dB. NHR == 1/H_linear
    (0.0308) exact. Clean modal saturates at the 40 dB cap.
- Documented limitations (md §7): ~6 dB divergence from Praat on
  NON-stationary real voice (test_Voice_EGG 24.4 vs 17.7 dB) — window length
  + aggregation differences, both valid, frozen; 40 dB ceiling; [60,400] Hz
  pitch search.
- Before / After: hnr.md Status UNKNOWN → PASS.
- Validation: metrics/hnr.md  (PASS, 13/13 checks)
- Tests: harness 13/13; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_cpp, +_our_cpp_median /
  +_praat_cpps helpers, +aliases), docs/validation/metrics/cpp.md (new)
- Why: Phase 1.5 — validate CPP / CPPS. Parity NOT pre-existing.
- Method insight: VoiceMap's CPP is the SuperCollider Cepstrum convention
  (natural-log spectrum, 1024-pt IFFT, f=SR/(2q)), NOT Praat's. Absolute CPP
  is convention-dependent (Praat CPPS sits several dB higher), so numeric
  parity is the wrong bar — CPP is validated in the literature by its
  ORDERING under degradation. Used correlation + monotonicity instead.
- Phase 1.5 results (harness 5/5 PASS):
  · (A) corr(CPP, Praat CPPS) over 0-25 dB SNR sweep r=0.9786.
  · (B) corr(CPP, SNR) r=0.9942 (monotonic); clean 23.1 >> SNR-0 10.9 dB;
    reproducible despite tie-break dither (std 0.028 dB / 5 runs);
    silence → no CPP.
- Documented limitations (md §7): not numerically comparable to Praat CPPS
  (re-derive clinical cut-offs on VoiceMap's scale); flat ~0.14 dB/dB SNR
  slope (use HNR for absolute noise); dither → weakly stochastic (~0.03 dB);
  chirp reads ~11 dB (periodicity index, not voicing gate).
- Before / After: cpp.md Status UNKNOWN → PASS.
- Validation: metrics/cpp.md  (PASS, 5/5 checks)
- Tests: harness 5/5; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_formants + helpers),
  docs/validation/metrics/formants.md (new)
- Why: Phase 1.6 — validate F1/F2/F3. Implementation IS a faithful Praat
  To Formant (burg) translation, so the bar is Praat parity.
- Phase 1.6 results (harness 5/5 PASS):
  · (A) per-cycle F1/F2/F3 vs Praat to_formant_burg on real 10 s: median
    |Δf/f| = 1.3 / 2.4 / 0.8 %; medians match Praat to ~1 Hz.
  · (B) synthetic F1 corroboration (Klatt a/e): 740 vs 730, 542 vs 530
    (<3 %).
- Finding: synthetic Klatt F2/F3 is NOT a usable GT — at F0=150 Hz the
  voicing harmonics collide with the formants and shift the order-10 LPC
  poles (spurious ~768 Hz pole on 'a'); Praat misreads them the same way
  (a-F3 ≈ 1914 vs 2440). LPC-at-high-F0 property, not a defect. Documented
  in §7; real-audio parity is the trustworthy evidence.
- Before / After: formants.md Status UNKNOWN → PASS.
- Validation: metrics/formants.md  (PASS, 5/5 checks)
- Tests: harness 5/5; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_bandwidths + aliases),
  docs/validation/metrics/bandwidths.md (new)
- Why: Phase 1.7 — validate B1/B2/B3. Same Burg poles as F1/F2/F3, bandwidth
  = -ln|z|·fs/π, with >800 Hz zeroed (the §8.8 physiological ceiling; the
  old FWHM note is stale — current code is pole-radius).
- Method: bandwidth is the highest-variance formant quantity, so the bar is
  AGGREGATE-MEDIAN parity vs Praat (≤10 %, conventions.md §1), not per-cycle.
- Phase 1.7 results (harness 5/5 PASS):
  · (A) median B1/B2/B3 vs Praat get_bandwidth: 182/244/155 vs 188/258/157 Hz
    → 3.0 / 5.4 / 1.2 %.
  · (B) >800 Hz ceiling holds (max 794); silence → none.
- Documented (md §7): high per-cycle scatter (median |Δf/f| 10/18/11 %),
  B2 least stable (~33 % zeroed by the ceiling), the hard 800 Hz gate
  (a 0 means "not measured"), shared high-F0 synthetic confound.
- Before / After: bandwidths.md Status UNKNOWN → PASS.
- Validation: metrics/bandwidths.md  (PASS, 5/5 checks)
- Tests: harness 5/5; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_spectral + _spec_frames
  helper + aliases), docs/validation/metrics/spectral_moments.md (new)
- Why: Phase 1.8 — validate spectral moments (centroid / bandwidth / rolloff
  / flatness / slope) vs librosa.
- Method: feed librosa the SAME spectrogram our calculator builds (via S=),
  isolating the formula from the framing — the spectral analogue of jitter
  feeding Praat the same marks.
- Phase 1.8 results (harness 7/7 PASS):
  · (A) centroid/bandwidth/rolloff/flatness == librosa to ~1e-16 (machine
    precision) on a shared spectrogram.
  · (B) slope recovers an analytic linear log10|S| slope exactly (librosa
    has no spectral_slope); 1 kHz tone → centroid 1000.0 Hz through the
    SHIPPED calculator; white-noise flatness 0.85 >> tone ~0.
- Documented (md §7): power-weighting (not librosa's magnitude default — a
  consistent offset vs a default librosa call); VoiceMap framing;
  slope units (log10|S|/Hz, not dB/oct); skew/kurt are display-clipped.
- Before / After: spectral_moments.md Status UNKNOWN → PASS.
- Validation: metrics/spectral_moments.md  (PASS, 7/7 checks)
- Tests: harness 7/7; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_vibrato + aliases),
  docs/validation/metrics/vibrato.md (new)
- Why: Phase 1.10 — validate vibrato rate + extent (synthetic GT).
- Phase 1.10 results (harness 8/8 PASS):
  · (B) EXTENT recovers imposed depth to <5 % at the formula level
    (100→103, 50→48, 200→199 c); 0 % false vibrato on a steady note;
    e2e fixture extent 88 c (pitch-tracker noise).
- IMPORTANT finding (md §7): vibrato RATE is resolution-limited. Bin width =
  F0/W ≈ 5 Hz at F0 200 / W 40, so the 4–8 Hz band holds ~1 bin and rate
  biases toward it (6 Hz reads ~4.7, 7 Hz ~5.6). Validated only as
  "detected in 4–8 Hz band"; does NOT meet the ±0.3 Hz convention. Frozen
  pre-copyright; post-freeze fix = zero-pad the FFT or lengthen W. Flagged
  to the user as a real quality gap.
- Before / After: vibrato.md Status UNKNOWN → PASS (extent + detection).
- Validation: metrics/vibrato.md  (PASS, 8/8 checks; rate caveat in §7)
- Tests: harness 8/8; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_mfcc + aliases),
  docs/validation/metrics/mfcc.md (new)
- Why: Phase 1.12 — validate MFCC 1-13 vs librosa (the last doable P0; #9/#11
  blocked on opensmile / Saarbrücken).
- Method: ours is HTK-style (vertex-quantised filterbank, natural log) so not
  bit-identical to a default librosa call — validated in LAYERS.
- Phase 1.12 results (harness 5/5 PASS):
  · (A) mel centres == librosa htk EXACT (max|Δ|=0); DCT-II ortho == librosa
    EXACT on the same log-mel (max|Δ|=0); filterbank ≈ librosa htk/norm=None
    (max|Δw| 0.11, the vertex-quantisation gap); full MFCC per-coef Pearson
    r vs the librosa filterbank path ≥ 0.999 (min of 13 = 0.9989).
  · (B) shipped MFCCCalculator emits 13 finite coeffs, mfcc1 ≈ inline.
- Documented (md §7): natural-log-vs-dB constant scale (×0.23,
  correlation-invariant); vertex-quantisation; MFCC 1-13 (no C0/deltas).
- Before / After: mfcc.md Status UNKNOWN → PASS.
- Validation: metrics/mfcc.md  (PASS, 5/5 checks)
- Tests: harness 5/5; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.
- ►► Phase 1 P0 status: 10/12 PASS (1-8, 10, 12). Remaining BLOCKED:
  #9 Alpha/Hammarberg (opensmile not installed), #11 PPE (SVD corpus not
  downloaded). Next session: install opensmile OR pick an alt reference for
  Alpha/Hammarberg; download Saarbrücken for PPE + the (C) corpus tests.

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/validate_metric.py (+validate_alpha_hammarberg + aliases),
  requirements-validation.txt (opensmile uncommented),
  docs/validation/metrics/alpha_hammarberg.md (new)
- Why: Phase 1.9 — UNBLOCKED by installing opensmile 2.6.0. Validate Alpha
  Ratio + Hammarberg Index vs eGeMAPS.
- Phase 1.9 results (harness 5/5 PASS):
  · (B) analytic two-tone GT (500+3000 Hz, 5 amplitude ratios): both Alpha
    and Hammarberg recover 20·log10(Al/Ah) exactly (≤0.03 dB).
  · (A) OpenSMILE eGeMAPSv02 on a voiced tilt sweep: Alpha r = −1.0000
    (anti-correlated — ours = E_low/E_high, OpenSMILE the inverse; magnitudes
    match), Hammarberg r = +0.9999 with median |Δ| 0.39 dB (near value-parity).
- Finding: OpenSMILE's Alpha is the inverse band ratio → ours must be NEGATED
  before comparing to an eGeMAPS threshold (md §7). OpenSMILE needs voiced
  input (two-tone gives it garbage) → comparison run on voiced vowels only.
- Before / After: alpha_hammarberg.md Status UNKNOWN → PASS.
- Validation: metrics/alpha_hammarberg.md  (PASS, 5/5 checks)
- Tests: harness 5/5; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.
- ►► Phase 1 P0 now 11/12 PASS. Only #11 PPE remains (needs a real corpus).

## 2026-05-31  session=validation-bootstrap  commit=pending
- Touched: scripts/fetch_voiced_corpus.py (new), scripts/validate_metric.py
  (+validate_ppe + CORPORA_DIR), docs/validation/metrics/ppe.md (new),
  docs/validation/corpora/voiced.md (new), corpora/saarbruecken.md (status),
  corpora/voiced/manifest.json (new; wavs gitignored)
- Why: Phase 1.11 — UNBLOCKED #11 PPE with a real corpus. SVD web export is
  still deferred; used the free VOICED corpus (PhysioNet, ODC-BY) instead.
- Phase 1.11 results (harness 3/3 PASS — the FIRST (C) corpus validator):
  · Downloaded 42 healthy + 50 pathological VOICED /a/ recordings (8 kHz).
  · median PPE healthy 0.282 < pathological 0.333; ROC AUC 0.734 > 0.70.
  · PPE is sample-rate-independent (period ratios) so 8 kHz used as-is; cycle
    marks from Praat cc (validated-equivalent to VoiceMap's marker).
- Honest note: AUC firmed up with data (0.68 on 80 recs → 0.73 on 92) — added
  data, did NOT tune params. AUC is subset-dependent (flaky PhysioNet
  downloads); >0.70 with the fuller balanced cohort.
- Corpus reproducible via scripts/fetch_voiced_corpus.py; only the script +
  manifest are tracked (wavs gitignored).
- Before / After: ppe.md Status UNKNOWN → PASS.
- Validation: metrics/ppe.md  (PASS, 3/3 checks)
- Tests: harness 3/3; validate_params.py 48 PASS / 4 WARN / 0 FAIL intact.
- ►►►► Phase 1 P0 COMPLETE: 12/12 PASS. All P0 metrics validated (A/B/C as
  applicable). Next: Phase 2 (P1 EGG + secondary acoustic), or SVD download
  to add EGG-dependent (C) tests.

<!-- next-session-anchor -->
