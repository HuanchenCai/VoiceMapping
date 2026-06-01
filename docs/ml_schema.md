# VoiceMap ML Schema

> **Auto-generated** by `scripts/gen_ml_schema.py` from `voicemap.metrics_registry`.
> Do not edit by hand — re-run the script after changing the metric set.

This document defines the columns VoiceMap produces and the feature schema the
scikit-learn extractor (`voicemap.ml.VoiceFeatureExtractor`) emits. It is the
contract for downstream ML / pandas / parquet consumers.

## 1. VRP CSV layout

- One CSV per recording, **`;`-separated** (read with
  `voicemap.ml.read_vrp(path)` or `pandas.read_csv(path, sep=';')`).
- **One row per `(MIDI, dB)` cell** — a 2-D Voice Range Profile binned by
  semitone (MIDI note) × sound-pressure-level (dB).
- Key / bookkeeping columns (not model features):
  `MIDI`, `dB`, `Total` —
  `MIDI`/`dB` are the cell coordinates, `Total` is the cycle count in the cell.

### Missing-value conventions

- **Unpopulated cells** simply have no row (the grid is sparse).
- **Mono / acoustic-only recordings** (no EGG channel): all EGG-category
  columns are **0** (the metric does not exist without EGG) — treat 0 in an EGG
  column as "not measured", not as a real value.
- **Per-cell `mean` aggregation** is cycle-count-weighted; cells are never
  imputed at the CSV level.
- The extractor emits **`NaN`** for a whole recording only if it produced no
  analysable cycles (`on_error='nan'`), so put a `SimpleImputer` after it in a
  pipeline if your corpus has such files.

## 2. Feature columns (64 metrics, 44 cross-validated)

These continuous per-cell metrics (categories Acoustic / EGG / Singing, plus
MFCC) are the modelling features. "Validated ✅" means a numerical-parity or
synthetic-ground-truth test passed (see `docs/methodology.md` /
`docs/validation/metrics/`); "⚠" means computed but not yet cross-validated.

| Column | Category | Unit | Validated | Description |
|---|---|---|:---:|---|
| `Clarity` | Acoustic | — | ✅ | McLeod-Wyvill NSDF pitch-detection confidence. |
| `CPP` | Acoustic | dB | ✅ | Cepstral Peak Prominence. |
| `CPPS` | Acoustic | dB | ✅ | Smoothed CPP (Hillenbrand 1996). |
| `SpecBal` | Acoustic | dB | ✅ | 10·log10(E_below_1500Hz / E_above). |
| `Crest` | Acoustic | — | ✅ | Peak / RMS amplitude ratio. |
| `Entropy` | Acoustic | — | ✅ | Sample Entropy on per-cycle EGG harmonic vectors. |
| `Jitter` | Acoustic | % | ✅ | MDVP-style period perturbation with 1.3× factor. |
| `JitterRAP` | Acoustic | % | ✅ | MDVP-style period perturbation with 1.3× factor. |
| `JitterPPQ5` | Acoustic | % | ✅ | MDVP-style period perturbation with 1.3× factor. |
| `Shimmer` | Acoustic | % | ✅ | MDVP-style amplitude perturbation. |
| `ShimmerAPQ3` | Acoustic | % | ✅ | MDVP-style amplitude perturbation. |
| `ShimmerAPQ5` | Acoustic | % | ✅ | MDVP-style amplitude perturbation. |
| `ShimmerAPQ11` | Acoustic | % | ✅ | MDVP-style amplitude perturbation. |
| `ShimmerDB` | Acoustic | dB | ✅ | dB shimmer = mean \|20·log10(A[i]/A[i-1])\|. |
| `HNR` | Acoustic | dB | ✅ | Harmonics-to-Noise Ratio (Praat autocorrelation). |
| `NHR` | Acoustic | — | ⚠ | Noise-to-Harmonics Ratio = 1/10^(HNR/10). |
| `PPE` | Acoustic | — | ⚠ | Shannon entropy of log-period in sliding window. |
| `ZCR` | Acoustic | — | ⚠ | Per-cycle zero-crossings / cycle length. |
| `Qcontact` | EGG | — | ✅ | Integral-based contact quotient (normalised-EGG area). |
| `dEGGmax` | EGG | slope | ✅ | Peak amplitude of EGG derivative. |
| `Icontact` | EGG | — | ✅ | log10(dEGGmax) · Qcontact. |
| `HRFegg` | EGG | dB | ✅ | Harmonic Richness Factor on EGG DFT. |
| `OQ` | EGG | — | ✅ | (T - GOI) / T from dEGG peaks. |
| `SPQ` | EGG | — | ✅ | T_opening / T_closing. |
| `CIQ` | EGG | — | ✅ | (T_closing - T_opening) / T_open. |
| `VibratoRate` | Singing | Hz | ✅ | Dominant F0 modulation in 4-8 Hz band. |
| `VibratoExtent` | Singing | cents | ✅ | Peak-to-peak F0 modulation amplitude. |
| `F1` | Singing | Hz | ✅ | LPC spectrum peak ≥ f1_floor. |
| `F2` | Singing | Hz | ✅ | 2nd LPC peak above F1. |
| `F3` | Singing | Hz | ✅ | 3rd LPC peak. |
| `SingersFormant` | Singing | dB | ✅ | 2.8-3.4 kHz band energy / total (dB). |
| `H1H2` | Singing | dB | ✅ | Voice DFT amplitude difference H1 − H2 (dB). |
| `H1H3` | Singing | dB | ✅ | Voice DFT amplitude difference H1 − H3 (dB). |
| `RMS` | Acoustic | — | ⚠ | Time-domain root-mean-square per frame. |
| `F0_Hz` | Acoustic | Hz | ⚠ | Fundamental frequency in Hz (= 440·2^((MIDI-69)/12)). |
| `SpectralCentroid` | Acoustic | Hz | ⚠ | Σ(f·\|X\|²)/Σ\|X\|² — spectral 'center of mass'. |
| `SpectralBandwidth` | Acoustic | Hz | ⚠ | Spectral spread around centroid. |
| `SpectralRolloff85` | Acoustic | Hz | ⚠ | Frequency below which 85% of spectral energy lies. |
| `SpectralFlatness` | Acoustic | — | ⚠ | geomean / mean — 0 tonal, 1 noisy. |
| `SpectralSlope` | Acoustic | — | ⚠ | Linear slope of log10(\|X\|) vs frequency (0-5 kHz). |
| `SpectralSkewness` | Acoustic | — | ⚠ | Third spectral moment around centroid. |
| `SpectralKurtosis` | Acoustic | — | ⚠ | Fourth spectral moment − 3. |
| `AlphaRatio` | Acoustic | dB | ⚠ | 10·log10(E[50-1000Hz] / E[1-5kHz]). |
| `HammarbergIndex` | Acoustic | dB | ⚠ | max(0-2 kHz dB) − max(2-5 kHz dB). |
| `B1` | Singing | Hz | ⚠ | LPC root bandwidth = -ln\|z\|·Fs/π. |
| `B2` | Singing | Hz | ⚠ | LPC root bandwidth for F2. |
| `B3` | Singing | Hz | ⚠ | LPC root bandwidth for F3. |
| `FormantDispersion` | Singing | Hz | ⚠ | (F3 − F1) / 2 — vocal-tract length proxy. |
| `SPR` | Singing | dB | ⚠ | 10·log10(E[2-4kHz] / E[0-2kHz]). |
| `VibratoJitter` | Singing | % | ⚠ | CV (%) of vibrato cycle period in sliding window. |
| `GNE` | Acoustic | — | ✅ | Glottal-to-Noise Excitation (Michaelis 1997): max cross-band Hilbert-envelope correlation. ~1 clean glottal, ~0 noisy. |
| `MFCC1` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 1. |
| `MFCC2` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 2. |
| `MFCC3` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 3. |
| `MFCC4` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 4. |
| `MFCC5` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 5. |
| `MFCC6` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 6. |
| `MFCC7` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 7. |
| `MFCC8` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 8. |
| `MFCC9` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 9. |
| `MFCC10` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 10. |
| `MFCC11` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 11. |
| `MFCC12` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 12. |
| `MFCC13` | Acoustic | — | ✅ | Mel-frequency cepstral coefficient 13. |

## 3. Categorical / density columns (excluded from features by default)

K-means **label IDs** (`maxCluster`, `maxCPhon`) and per-file cluster **shares**
(`Cluster 1..5`, `cPhon 1..5`) are written to the CSV but excluded from the
default feature set: each recording's K-means is fit independently, so label *k*
is not comparable across files. Use a shared centroid library
(`voicemap.centroids`) to make them comparable. `Total` is cycle density.

| Column | Category | Description |
|---|---|---|
| `Total` | Density | Number of analysed cycles in this (MIDI, dB) cell. |
| `maxCluster` | Cluster | argmax of EGG-shape cluster shares per cell. |
| `maxCPhon` | Cluster | argmax of cPhon (quality-K-means) shares per cell. |
| `Cluster 1` | Cluster | % of cycles in EGG cluster 1. |
| `cPhon 1` | Cluster | % of cycles in phonation cluster 1. |
| `Cluster 2` | Cluster | % of cycles in EGG cluster 2. |
| `cPhon 2` | Cluster | % of cycles in phonation cluster 2. |
| `Cluster 3` | Cluster | % of cycles in EGG cluster 3. |
| `cPhon 3` | Cluster | % of cycles in phonation cluster 3. |
| `Cluster 4` | Cluster | % of cycles in EGG cluster 4. |
| `cPhon 4` | Cluster | % of cycles in phonation cluster 4. |
| `Cluster 5` | Cluster | % of cycles in EGG cluster 5. |
| `cPhon 5` | Cluster | % of cycles in phonation cluster 5. |

## 4. Extractor output schema

`VoiceFeatureExtractor().fit_transform(paths)` returns an
`(n_files, n_features)` float array. With the default
`aggregations=('mean', 'std')` that is **130 features**: each of the
64 metric columns reduced across the recording's cells to a
cycle-count-weighted `mean` and `std`, plus two global descriptors.

- Feature naming: `<MetricKey>__<agg>` (e.g. `CPP__mean`, `HNR__std`).
- Global descriptors: `vrp_n_cells` (populated cell count), `vrp_n_cycles`
  (total analysed cycles).
- `get_feature_names_out()` returns the exact names, in order, for pipeline
  introspection.

First / last feature names:

```
Clarity__mean, Clarity__std, CPP__mean, CPP__std, CPPS__mean, CPPS__std, ..., MFCC13__std, vrp_n_cells, vrp_n_cycles
```

## 5. Formats

- **CSV** — canonical, `;`-separated, human/Excel readable.
- **Parquet** — `voicemap.ml.vrp_to_parquet(df, path)` / `read_parquet(path)`
  (columnar, typed, faster reload; requires `pyarrow`).
