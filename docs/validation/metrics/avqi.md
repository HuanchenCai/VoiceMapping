# AVQI — Acoustic Voice Quality Index

> One overall voice-quality score combining six acoustic measures from the
> time, frequency and quefrency domains. Higher = more dysphonic.

## 1. Implementation
- File: `voicemap/metrics.py`
  - `AVQICalculator` — per-cycle Praat-scale inputs `cpps_praat`,
    `ltas_slope`, `ltas_tilt`.
  - `avqi_from_components()` + `AVQI_COEFFS` — the combination formula.
- File: `voicemap/csv_writer.py` → `write_vrp` — per (MIDI, dB) cell, AVQI is
  combined from the **cell means** of its six inputs
  (`CPPSPraat`, `HNR`, `Shimmer`, `ShimmerDB`, `LTASSlope`, `LTASTilt`).
  The formula is linear, so this equals the mean of per-cycle AVQI, and it
  keeps the shimmer decomposition's zero-filled cycles weighted exactly as in
  the `Shimmer` column.
- Pipeline stage 20 (`analyzer.calculate_all_metrics`).
- Config: `VoiceMapConfig.avqi_version` — `"03.01"` (default) or `"02.02"`.

HNR / Shimmer / ShimmerDB reuse the existing calculators (Praat parity, see
`hnr.md`, `shimmer.md`). CPPS is **recomputed** on the Praat scale because the
project's `CPP` / `CPPS` columns follow the SuperCollider cepstrum convention
(`cpp.md` §2), which is several dB off the scale the AVQI coefficients were
fitted on.

## 2. Reference Standard
- Maryn Y, Corthals P, Van Cauwenberge P, Roy N, De Bodt M (2010).
  *Toward improved ecological validity in the acoustic measurement of overall
  voice quality: combining continuous speech and sustained vowels.*
  J Voice 24(5):540–555. doi:10.1016/j.jvoice.2008.12.014
- Barsties B, Maryn Y (2016) — AVQI v03.01 coefficient set.
- Reference implementation: the AVQI Praat script (v02.02 / v03.01).
  The six measures, with the script's settings:

| Input | Praat command in the AVQI script |
|---|---|
| CPPS | `To PowerCepstrogram 60 0.002 5000 50` → `Get CPPS no 0.01 0.001 60 330 0.05 Parabolic 0.001 0 Straight Robust` |
| HNR | `Voice report` mean HNR (cc pitch 75–600 Hz) |
| Shimmer local (%) | `Get shimmer (local) 0 0 0.0001 0.02 1.3 1.6` × 100 |
| Shimmer local (dB) | `Get shimmer (local_dB) …` |
| LTAS slope | `To Ltas 1` → `Get slope 0 1000 1000 10000 energy` |
| LTAS tilt | `Compute trend line 1 10000` → `Get slope 0 1000 1000 10000 energy` |

Formulas:

- v03.01: `AVQI = (4.152 − 0.177·CPPS − 0.006·HNR − 0.037·Shim + 0.941·ShdB + 0.01·Slope + 0.093·Tilt) × 2.8902`
- v02.02: `AVQI = (3.295 − 0.111·CPPS − 0.073·HNR − 0.213·Shim + 2.789·ShdB − 0.032·Slope + 0.077·Tilt) × 2.208 + 1.797`
  (the 2010 regression, rescaled to 0–10)

Native re-implementation details:
- **CPPS**: resample to 10 kHz, pre-emphasis from 50 Hz, Gaussian window of
  2 × 3/60 s, 2 ms hop, power cepstrum `|IFFT(ln|X|²)|²`; moving average over
  5 frames (10 ms) and 10 quefrency bins (1 ms) in the power domain; dB;
  Sen/Theil trend line over pairs (i, i+n/2) from 1 ms; parabolic peak in
  60–330 Hz; prominence = peak − trend. Each cycle takes its nearest frame.
- **LTAS slope / tilt**: 50 ms Hann frames, 10 ms hop, PSD averaged over 9
  frames (~130 ms local LTAS). Slope = `10·log10(mean E[1–10 kHz] / mean
  E[0–1 kHz])`; tilt = the same on the least-squares dB-vs-Hz line fitted over
  1–10 kHz.

## 3. Test Signals
**Synthetic** (in `tests/test_avqi.py`): harmonic-rich 200 Hz source with low
vs high additive noise (ordering + per-cycle alignment).

**Real**: `audio/test_Voice_EGG.wav`, ch1, segments at 0 / 15 / 30 / 45 / 60 s.

## 4. Validation Method
- **(A) Formula parity**: `avqi_from_components` vs the scripts' formulas,
  exact to 1e-10.
- **(A) CPPS parity** vs parselmouth `Get CPPS` on 6–8 s segments, |Δ| < 0.6 dB.
- **(A) LTAS slope / tilt definition parity** vs parselmouth `Ltas` on a
  long-term spectrum, |Δ| < 0.5 / 0.6 dB.
- **(B) Synthetic ordering**: more noise → lower CPPS, flatter slope.

```bash
python tests/test_avqi.py
python tests/validate_params.py audio/test_Voice_EGG.wav
```

## 5. Results

| Test | Praat | Ours | Δ | Pass? |
|---|---|---|---|---|
| CPPS 0–8 s | 18.36 dB | 18.64 dB | +0.28 | ✓ |
| CPPS 15–23 s | 17.13 dB | 17.36 dB | +0.23 | ✓ |
| CPPS 30–38 s | 17.39 dB | 17.68 dB | +0.29 | ✓ |
| CPPS 45–53 s | 17.60 dB | 18.05 dB | +0.45 | ✓ |
| CPPS 60–68 s | 16.83 dB | 17.21 dB | +0.38 | ✓ |
| LTAS slope 0–8 s (long-term) | −18.47 dB | −18.52 dB | −0.05 | ✓ |
| LTAS tilt 0–8 s (long-term) | −13.55 dB | −13.52 dB | +0.03 | ✓ |
| LTAS tilt 30–38 s (long-term) | −12.65 dB | −12.93 dB | −0.28 | ✓ |
| LTAS tilt 60–68 s (long-term) | −9.99 dB | −9.88 dB | +0.11 | ✓ |
| Formula v03.01 / v02.02 | script | identical | 0 | ✓ |

Whole recording, for orientation: Praat AVQI v03.01 = −1.1 (CPPS 17.6,
HNR 30.9, shimmer 1.1 %, 0.116 dB, slope −17.8, tilt −12.1). VRP cells,
cycle-weighted: AVQI −0.66. The recording is a very clean voice, so values
below 0 are what the formula gives (it is not clipped to 0–10).

## 6. Status
**PASS** (inputs) — per-cell AVQI is a new derived use, see §7.
- validated_on: 2026-10-16
- validator: tests/test_avqi.py + validate_params.py (PASS=49 WARN=0 FAIL=0)

## 7. Known Limitations
- **CPPS bias +0.2–0.45 dB** vs Praat. The cepstrogram itself and the peak
  match; the residual is in Praat's "Robust" trend-line fit, which our
  Sen/Theil-pairs fit does not reproduce exactly. Effect on AVQI v03.01:
  about −0.1 to −0.2 points.
- **Per-cell vs whole-recording LTAS**: AVQI's LTAS is one spectrum of all
  voiced audio, dominated by the loudest frames. A VRP cell holds cycles at
  one pitch/SPL, so its slope/tilt come from ~130 ms local spectra and differ
  from a whole-recording value (on the test file: slope −28 vs −18 dB). This
  is the intended per-cell reading, not an error, but per-cell AVQI must not
  be compared against published AVQI cut-offs as if it were a recording-level
  AVQI.
- **HNR**: VoiceMap's HNR uses a 40 ms window and reads ~6 dB higher than
  Praat on running voice (`hnr.md` §7). With v03.01 (HNR weight −0.006) the
  AVQI impact is ~0.1 point; with v02.02 (−0.073) it is ~1.3 points.
- AVQI was fitted on sustained vowel + connected speech, not singing; cut-offs
  (≈2.4–3.2 depending on language and version) are not validated per cell.
- Sample rates below 20 kHz cap the LTAS high band at Nyquist (logged).

## 8. Change Log
- 2026-10-16 — initial implementation (AVQICalculator, per-cell AVQI).
