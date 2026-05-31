# Validation Conventions

> Tolerances, units, file-naming, and other low-level conventions used by
> every validation file. **Update this file whenever a convention changes**;
> never leave per-metric files contradicting it.

## 1. Tolerance defaults

Used by `scripts/validate_metric.py` unless overridden in the metric's
md file.

| Class of metric | Default tolerance | Notes |
|---|---|---|
| Time-domain perturbation (jitter, shimmer in %) | `atol=1e-6` (fraction) | Praat-parity scale |
| dB-domain (HNR, NHR, CPP, CPPS, ShimmerDB, AlphaRatio, Hammarberg) | `atol=0.5 dB` | Within "one bin" of Praat's reporting precision |
| Frequency (F0, formants F1-F3 in Hz) | `rtol=0.02` (= 2 %) | Roughly one semitone |
| Bandwidth (B1-B3 in Hz) | `rtol=0.10` (10 %) | Bandwidth is high-variance |
| Spectral moments (centroid, bandwidth, rolloff) | `rtol=1e-2` | librosa-level |
| MFCC | `rtol=1e-2` | librosa-level after parameter alignment |
| Entropy-class (PPE, CSE) | `atol=0.05` (absolute) | These are bounded [0, 1] or similar |
| Vibrato rate | `atol=0.3 Hz` | FFT bin resolution at W=40 cycles |
| Vibrato extent | `rtol=0.10` (10 %) | Extent is amplitude-dependent |
| Counts (n_cycles, n_voiced_frames) | `relative ≤ 5 %` | Cycle marking implementations vary |

If a metric needs tighter or looser tolerance, document it in the metric's
`docs/validation/metrics/<name>.md` Section 4 + Section 7.

## 2. Units

| Quantity | Unit | Notes |
|---|---|---|
| F0 | Hz | always |
| MIDI | semitones (continuous) | not rounded |
| Period | seconds | never samples in output |
| Jitter (% form) | percent | not fraction |
| Jitter (absolute form) | seconds | always |
| Shimmer (% form) | percent | not fraction |
| Shimmer (dB form) | dB | always |
| Spectrum centroid / bandwidth / rolloff | Hz | always |
| Time | seconds | from start of recording |
| Sample rate | Hz | int |

## 3. Test-signal file naming

`{kind}_{property1}_{property2}_{duration}s.wav`

Examples:
- `vowel_modal_200Hz_5s.wav`
- `vowel_jitter_0p5pct_F200_3s.wav`
- `vowel_shimmer_5pct_F200_3s.wav`
- `vowel_vibrato_6Hz_100cent_F200_5s.wav`

Decimal points written as `p` (`0p5` = 0.5) to keep filenames shell-safe.

All test signals must come with a manifest entry in
`docs/validation/test_signals/manifest.json` containing:

```json
{
  "filename": "vowel_modal_200Hz_5s.wav",
  "sample_rate": 44100,
  "duration_s": 5.0,
  "ground_truth": {
    "F0_Hz": 200.0,
    "jitter_local_pct": 0.0,
    "shimmer_local_pct": 0.0,
    "formants_Hz": [700, 1200, 2600],
    "SNR_dB": null
  },
  "generator_seed": 0,
  "generator_function": "synthesize_vowel_modal"
}
```

## 4. Reference tools

| Reference | Python entry | Version pinned in `requirements-validation.txt` |
|---|---|---|
| Praat | `parselmouth` | `praat-parselmouth>=0.4.7` |
| librosa | `librosa` | `librosa>=0.10` |
| scipy | `scipy.signal` | (already a runtime dep) |
| nolds | `nolds.sampen` | for Sample Entropy reference |
| OpenSMILE eGeMAPS | `opensmile` Python wrapper | optional, used only for Alpha/Hammarberg parity |

**Never rely on locally-installed CLI tools** (e.g. `praat` executable
on PATH); always go through a Python binding so CI can reproduce.

## 5. Status badge wording (used in metric md Section 6)

- **PASS** — all stated validation criteria met. Date + commit recorded.
- **IN_PROGRESS** — partial validation; section 5 (Results) populated but
  at least one criterion still failing. Section 7 explains what remains.
- **FAIL** — known-broken metric that cannot meet acceptance criteria.
  Section 7 explains why and proposes next action (re-implement, remove,
  scope-restrict). Do NOT ship a FAIL metric without explicit GUI/CLI
  warning.

A metric without a Section 6 Status is treated as **UNKNOWN** and
excluded from any paper-grade output.

## 6. Commit message → log.md → metric md cross-reference

Every commit that touches metric code or a validation file must:

1. Have a commit message starting `validate(<metric>):` or `fix(<metric>):`
   or `docs(validation):`.
2. Append a paragraph to `docs/validation/log.md`.
3. Update Section 8 (Change Log) of the affected `metrics/<name>.md`.
4. If Status changes, update Section 6 too.

Failing to do any of these is reverted; it's the only way the audit trail
stays trustworthy for a methodology paper submission.
