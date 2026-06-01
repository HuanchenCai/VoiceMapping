# -*- coding: utf-8 -*-
"""Generate docs/ml_schema.md from the live metric registry.

The schema doc is auto-derived so it can never drift from the code: re-run
this after adding/removing a metric.

    python scripts/gen_ml_schema.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voicemap.ml import (  # noqa: E402
    feature_schema, VoiceFeatureExtractor, VRP_SEP, _NON_FEATURE_COLS,
)
from voicemap import metrics_registry as reg  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "ml_schema.md")


def _esc(s: str) -> str:
    return str(s).replace("|", "\\|")


def _metric_table(df) -> str:
    lines = ["| Column | Category | Unit | Validated | Description |",
             "|---|---|---|:---:|---|"]
    for _, r in df.iterrows():
        unit = r["unit"] or "—"
        ok = "✅" if r["validated"] else "⚠"
        lines.append(f"| `{r['key']}` | {r['category']} | {_esc(unit)} | "
                     f"{ok} | {_esc(r['description'])} |")
    return "\n".join(lines)


def _cluster_table() -> str:
    lines = ["| Column | Category | Description |", "|---|---|---|"]
    for s in reg.REGISTRY.values():
        if s.category in ("Cluster", "Density"):
            lines.append(f"| `{s.key}` | {s.category} | {_esc(s.description)} |")
    return "\n".join(lines)


def main():
    sch = feature_schema()
    n_total = len(sch)
    n_val = int(sch["validated"].sum())
    ex = VoiceFeatureExtractor()
    names = list(ex.get_feature_names_out())

    doc = f"""# VoiceMap ML Schema

> **Auto-generated** by `scripts/gen_ml_schema.py` from `voicemap.metrics_registry`.
> Do not edit by hand — re-run the script after changing the metric set.

This document defines the columns VoiceMap produces and the feature schema the
scikit-learn extractor (`voicemap.ml.VoiceFeatureExtractor`) emits. It is the
contract for downstream ML / pandas / parquet consumers.

## 1. VRP CSV layout

- One CSV per recording, **`{VRP_SEP}`-separated** (read with
  `voicemap.ml.read_vrp(path)` or `pandas.read_csv(path, sep='{VRP_SEP}')`).
- **One row per `(MIDI, dB)` cell** — a 2-D Voice Range Profile binned by
  semitone (MIDI note) × sound-pressure-level (dB).
- Key / bookkeeping columns (not model features):
  {", ".join(f'`{c}`' for c in _NON_FEATURE_COLS)} —
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

## 2. Feature columns ({n_total} metrics, {n_val} cross-validated)

These continuous per-cell metrics (categories Acoustic / EGG / Singing, plus
MFCC) are the modelling features. "Validated ✅" means a numerical-parity or
synthetic-ground-truth test passed (see `docs/methodology.md` /
`docs/validation/metrics/`); "⚠" means computed but not yet cross-validated.

{_metric_table(sch)}

## 3. Categorical / density columns (excluded from features by default)

K-means **label IDs** (`maxCluster`, `maxCPhon`) and per-file cluster **shares**
(`Cluster 1..5`, `cPhon 1..5`) are written to the CSV but excluded from the
default feature set: each recording's K-means is fit independently, so label *k*
is not comparable across files. Use a shared centroid library
(`voicemap.centroids`) to make them comparable. `Total` is cycle density.

{_cluster_table()}

## 4. Extractor output schema

`VoiceFeatureExtractor().fit_transform(paths)` returns an
`(n_files, n_features)` float array. With the default
`aggregations=('mean', 'std')` that is **{len(names)} features**: each of the
{n_total} metric columns reduced across the recording's cells to a
cycle-count-weighted `mean` and `std`, plus two global descriptors.

- Feature naming: `<MetricKey>__<agg>` (e.g. `CPP__mean`, `HNR__std`).
- Global descriptors: `vrp_n_cells` (populated cell count), `vrp_n_cycles`
  (total analysed cycles).
- `get_feature_names_out()` returns the exact names, in order, for pipeline
  introspection.

First / last feature names:

```
{", ".join(names[:6])}, ..., {", ".join(names[-3:])}
```

## 5. Formats

- **CSV** — canonical, `{VRP_SEP}`-separated, human/Excel readable.
- **Parquet** — `voicemap.ml.vrp_to_parquet(df, path)` / `read_parquet(path)`
  (columnar, typed, faster reload; requires `pyarrow`).
"""
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"wrote {OUT}  ({n_total} metrics, {len(names)} features)")


if __name__ == "__main__":
    main()
