# Corpus: VOICED (PhysioNet)

> The **free** real-corpus used for **(C) real-corpus behaviour** evidence —
> the fallback flagged in `saarbruecken.md` while the SVD web export stays
> deferred. Wired and in use for **PPE** (Phase 1.11).

## Source & license
- **VOICED** = "VOICe ICar fEDerico II" database. Cesari, U. et al. (2018),
  *"A new database of healthy and pathological voices"*, Computers &
  Electrical Engineering.
- PhysioNet: https://physionet.org/content/voiced/1.0.0/
- License: **Open Data Commons ODC-BY 1.0** — free for research with
  attribution.

## Contents
- **208 subjects**, one sustained vowel /a/ each, **8 kHz**, 16-bit.
- Per-subject `-info.txt` with **Diagnosis**, age, sex, VHI/RSI scores, habits.
- Diagnosis distribution: **57 healthy**, 151 pathological across four families
  (hyperkinetic / hypokinetic dysphonia, reflux laryngitis, + sub-types).
- No EGG (acoustic only) — sufficient for the acoustic (C) tests (PPE, CPP,
  HNR distributions); EGG-dependent (C) tests still need SVD.

## Acquisition
```bash
python scripts/fetch_voiced_corpus.py --n 60
```
Downloads a balanced subset, converts the ASCII sample files to 8 kHz WAV
under `corpora/voiced/{healthy,pathological}/*.wav` (**gitignored**), and
writes `corpora/voiced/manifest.json` in the adapter schema
(see `saarbruecken.md` §"Adapter contract"). Only the script + manifest are
tracked, so the corpus is reproducible without committing audio. PhysioNet
occasionally times a request out; re-run to top up the cohort.

## Used by
| Metric | Test | Result |
|---|---|---|
| **PPE** (`metrics/ppe.md`) | healthy-vs-pathological ROC AUC | AUC 0.73 > 0.70 |

Candidate future (C) tests on this corpus: CPP, HNR, jitter/shimmer
distribution sanity (healthy vs disordered separation).

## Caveats
- PPE et al. are **sample-rate-independent** (period ratios) so 8 kHz is fine;
  any metric that needs > 4 kHz spectral content (Singer's Formant, high-band
  Alpha) should NOT use VOICED — its Nyquist is 4 kHz.
- The exact cohort depends on which downloads succeeded; the manifest records
  the actual set used for a given run.
