# VoiceMap Public API & Stability (v1.0.0)

> The stable surface third parties may depend on, and the semantic-versioning
> promise around it. Companion to `docs/ml_schema.md` (output contract) and
> `docs/reproducibility.md` (determinism).

VoiceMap follows **[Semantic Versioning 2.0.0](https://semver.org/)**. The
current release is **1.0.0** — the public API and the VRP output schema are
frozen for the 1.x line.

## 1. Versioning policy

Given `MAJOR.MINOR.PATCH`:

- **MAJOR** — backward-incompatible changes to anything in §2 (renamed/removed
  public symbol, changed call signature, removed or renamed VRP column, changed
  column units/meaning).
- **MINOR** — backward-compatible additions (new metric *column*, new optional
  keyword argument with a default, new public helper). Adding a column is
  additive: existing columns keep their name, position-independent meaning, and
  units.
- **PATCH** — bug fixes and metric-accuracy corrections that do not change the
  schema. A fix may shift a metric *value* (it was wrong before); such changes
  are noted in the release notes and re-baseline `e2e_baseline.json`.

The single source of truth for the version is `voicemap/__version__.py` (read by
the About dialog, CSV headers, PyInstaller, and `pyproject.toml`).

## 2. Public API surface

Everything below is stable under the policy above. Anything **not** listed is
internal and may change in any release.

### 2.1 Top-level package (`import voicemap`)

| Symbol | Kind | Notes |
|---|---|---|
| `VoiceMapAnalyzer` | class | Main analysis facade (§2.2). |
| `VoiceMapConfig` | dataclass | Analysis configuration (all fields keyword-only, defaulted). |
| `DEFAULT_CONFIG` | instance | A `VoiceMapConfig()` with defaults. |
| `__version__`, `__title_zh__`, `__title_en__`, `__author__`, `__email__`, `__license__`, `__copyright__` | metadata | From `voicemap.__version__`. |

Calculator classes, the GUI, plotter, and CSV-writer internals are intentionally
**not** re-exported — import-and-depend at your own risk; they are not covered
by this promise.

### 2.2 `VoiceMapAnalyzer` methods

| Method | Stability | Purpose |
|---|---|---|
| `analyze_and_output_vrp(file_path, return_df=False, plot_mode=…, export_plots=None, write_disk=True)` | stable | Whole-signal analysis → VRP CSV (+ DataFrame if `return_df`). |
| `analyze_and_output_vrp_auto(file_path, …, write_disk=True)` | stable | **Recommended entry.** Routes long files to the bounded-memory chunked path, short ones to the whole-signal path. Same return shape. |
| `analyze_and_output_vrp_chunked(file_path, chunk_s=120, overlap_s=1, …)` | stable | Explicit bounded-memory path for very long recordings. |
| `load_centroids(path)` / `save_centroids(path)` | stable | Persist / load EGG-shape K-means centroids. |
| `output_vrp_csv(metrics, …, write_disk=True)` | stable | Lower-level: per-cycle metrics dict → grouped VRP. |

`return_df=True` yields the per-cell VRP `pandas.DataFrame`; `write_disk=False`
suppresses all CSV/PNG side effects (used by the ML extractor).

### 2.3 ML integration (`import voicemap.ml`)

| Symbol | Stability | Purpose |
|---|---|---|
| `VoiceFeatureExtractor` | stable | sklearn `BaseEstimator`+`TransformerMixin`: audio/VRP files → fixed-length feature matrix. `fit` / `transform` / `fit_transform` / `get_feature_names_out`. |
| `read_vrp(path)` | stable | Read a `;`-separated VRP CSV → DataFrame. |
| `vrp_to_parquet(df, path)` / `read_parquet(path)` | stable | Parquet round-trip (needs `pyarrow`). |
| `feature_schema(...)` | stable | DataFrame describing every feature column. |

`VoiceFeatureExtractor` constructor parameters (`config`, `aggregations`,
`include_categories`, `include_mfcc`, `on_error`) and the feature-naming scheme
(`<MetricKey>__<agg>` + `vrp_n_cells` / `vrp_n_cycles`) are part of the contract.

### 2.4 Output schema

The VRP CSV column set, names, units, and missing-value conventions in
`docs/ml_schema.md` are part of the public contract. New columns may be **added**
in a MINOR release; existing columns are not renamed or repurposed within 1.x.

## 3. What is explicitly NOT stable

- Calculator classes (`voicemap.metrics.*`), `metrics_registry` internals, the
  GUI (`voicemap.gui.*`), `plotter`, `csv_writer`, `report`, `excel_export`.
- Exact floating-point values across platforms (see `reproducibility.md` — the
  guarantee is tolerance-based, not bit-identical).
- Internal file layout under `result/` and intermediate artifacts.

## 4. Deprecation

Public symbols slated for removal will be deprecated (warning + docs note) for
at least one MINOR release before removal in the next MAJOR. Removed metric
columns, if ever, follow the same path.
