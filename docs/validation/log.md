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

<!-- next-session-anchor -->
