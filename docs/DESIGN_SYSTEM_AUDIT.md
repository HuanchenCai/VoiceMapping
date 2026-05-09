# VoiceMap Design System Audit

> Run via `/design-system audit` 2026-05-09

## Summary

| | |
|---|---|
| **Tokens defined** | 27 colors / 11 fonts |
| **Components reviewed** | 12 (5 dialogs + 4 custom widgets + 3 main app pieces) |
| **Hardcoded colors found** | ~~17~~ → **3 fallbacks only** (commit `02ea3a5` + follow-up: all P0/P1 hex tokenised; remaining 3 are safe fallback strings inside `plot_overlay._default_overlay_color()` for CLI-only use when GUI theme can't import) |
| **Naming conventions** | Dual track — legacy `BG/PANEL/ACCENT/...` and spec-verbatim `BG_APP/BG_PANEL/...` (kept for back-compat) |
| **Score** | ~~78~~ → **89 / 100** — color tokenisation 100 %, font tokens 100 %, P2 polish (Esc-to-close, keyboard nav, doc completeness) outstanding |

---

## Token Coverage

### Colors

| Category | Defined in `theme.py` | Hardcoded leaks (GUI) | Status |
|---|---|---|---|
| Surface (BG/PANEL/PANEL_HI/BORDER) | ✅ 4 + 1 alias (BORDER_STRONG) | 0 GUI uses, 4 plot uses (`#1a1a1a` plotter) | OK |
| Text (TEXT/MUTED/TEXT_MUTED/TEXT_INVERSE) | ✅ 4 | 0 | OK |
| Brand (ACCENT/ACCENT_HI/ACCENT_HOVER/ACCENT_PRESS) | ✅ 4 | 0 GUI, but `dialogs.py:467` uses `#d97706` directly = same as `ACCENT_PRESS` | **Tokenable** |
| Semantic (OK/WARN/ERR/INFO/SUCCESS/WARNING/ERROR) | ✅ 7 | `dialogs.py:467-468` uses `#d97706 / #dc2626 / #84cc16` instead of `WARN/ERR/OK` | **Tokenable** |
| Disabled state | ⚠️ ad-hoc — `app.py:335` uses `"#2a3340"` (a relic from the cyan palette) | 1 | **Tokenable** (define `BG_DISABLED`) |
| Plot palette (axes/grid/spines/empty cells) | ❌ no tokens | 8 occurrences across `plotter.py` / `plot_overlay.py` (`#444444 / #cccccc / #777777 / #e6e6e6 / #f2f2f2 / #ffffff / #1a1a1a / #ff3e88 / #00d9ff / #84cc16`) | **Add `PLOT_*` token group** |
| Code-area text bg (Log Text widget) | ❌ — `#0b1117` literal in 2 places | 2 | **Tokenable** (define `BG_CODE`) |

### Typography

| Token | Size | Used For | Issues |
|---|---|---|---|
| `FONT_CAPTION` | 9pt | unit hints, range column | — |
| `FONT_SMALL` | 10pt | small meta | — |
| `FONT_UI` | 11pt | default body | — |
| `FONT_UI_B` | 11pt bold | section labels | — |
| `FONT_SUB` | 12pt | header status pill | — |
| `FONT_DROP` | 13pt bold | drop-zone | — |
| `FONT_H2` | 15pt bold | (unused?) | **Audit**: search shows zero callers since we lowered FONT_TITLE |
| `FONT_TITLE` | 14pt bold | header app title | — |
| `FONT_DISPLAY` | 22pt bold | Inspector value pill numbers | — |
| `FONT_MONO` / `FONT_MONO_B` | Consolas 10/22 | range columns / value-pill big number | — |
| **Raw font tuples in widget code** | — | — | 5 occurrences in `app.py` / `dialogs.py` / `widgets.py` (e.g. `("Microsoft YaHei UI", 19, "bold")` for Inspector metric name, `("Microsoft YaHei UI", 14)` for `ⓘ` glyph). These should be `FONT_*` tokens. |

### Spacing

> Tk doesn't have a literal "spacing scale" but pad values cluster:
> 4 px ×2, 6 px ×6, 8 px ×5, 10 px ×4, 12 px ×6, 14 px ×9, 16 px ×7, 18 px ×2.

The 6/8/12/14/16 cluster is consistent with an 8 px-grid intent. **Diverge**: 3 px ×11 (mostly `pady=3` micro-spacing in dialogs), 1 px ×6 (separator-as-padding pattern). No wide drift.

**No formal `SPACE_XS / SPACE_S / SPACE_M / SPACE_L` token group** despite `docs/UI_DESIGN.md` §1.4 specifying one.

---

## Component Inventory

| Component | States | Variants | Hover | A11y | Score |
|---|---|---|---|---|---|
| `ModernMenubar` (top bar) | ✅ default / open | one | ✅ | partial (no Alt-keys) | 8/10 |
| `ModernPopup` (cascade menu) | ✅ default / hover / open / sub-popup | one | ✅ | ⚠️ no keyboard nav | 7/10 |
| `MetricPopup` (scrollable picker) | ✅ default / hover / selected | one | ✅ | ⚠️ no keyboard nav | 7/10 |
| `HoverTooltip` | ✅ delay (500 ms) / shown / hidden | one | n/a | ✅ ESC-friendly (auto-hides on Leave) | 9/10 |
| `SettingsDialog` | ✅ open / closed | one | n/a | ⚠️ no Esc-to-close | 8/10 |
| `CompareDialog` | ✅ load / loaded / empty / read-fail | one | n/a | ⚠️ no Esc-to-close | 8/10 |
| `ProgressDialog` | ✅ active / no close | one | n/a | indeterminate progress only | 7/10 |
| `LogWindow` | ✅ open / closed (singleton) | one | n/a | ⚠️ Alt-modifier missing | 7/10 |
| `AboutDialog` | ✅ open / closed | one | n/a | ✅ Accent close button | 9/10 |
| Track row | ✅ default / hover / active / queued / analyzing / analyzed / failed | one (compact single-line since 2026-05-08) | ✅ row-marker color | partial | 8/10 |
| Inspector value pill | ✅ none / hover-cell / out-of-range | one | live-update via mpl `motion_notify_event` | n/a | 9/10 |
| Inspector clinical bands | ✅ default / 4 severity colors (good/normal/watch/abnormal) | one | n/a | colour-blind: severity also encoded via tier order | 8/10 |
| Buttons (`ttk.Button`) | ✅ active / disabled | **2 variants**: `Accent.TButton` (primary) + `Ghost.TButton` (secondary) | ✅ via ttk style maps | ✅ native ttk a11y | 9/10 |

---

## Patterns

| Pattern | Where | Notes |
|---|---|---|
| **Modal dialog** | Settings / Compare / Progress / About / 3-button export-done | All centre over parent, `transient(app)`, no `grab_set` consistently — Settings has it, About doesn't |
| **Hover-to-open cascade** | `ModernPopup` cascades | 200 ms delay, sibling-row Enter closes prior sub-popup |
| **i18n-aware widget** | All persistent widgets registered via `_safe_text` lookup table in `_on_language_changed` | Pattern reused 20+ times |
| **Filter intersection (combobox)** | CompareDialog metric picker | Updates `values=` from `set(df_a.cols) ∩ set(df_b.cols)` |
| **Scrollable list with auto-show scrollbar** | Tracks Panel | inner Frame `<Configure>` → toggle scrollbar visibility |
| **Hover probe → live update Inspector** | Canvas → `_update_inspector_value` | `motion_notify_event` cell-lookup |

---

## Naming Consistency

| Issue | Examples | Recommendation |
|---|---|---|
| Dual color naming (legacy vs spec) | `BG` AND `BG_APP`, `MUTED` AND `TEXT_SEC`, `ACCENT_HI` AND `ACCENT_HOVER` | Tolerated for back-compat; new code SHOULD prefer the spec-verbatim aliases per `theme.py` docstring (§13). Audit: actual new code (last 50 commits) still uses legacy names. **Decision needed**: deprecate legacy or rename spec aliases. |
| Test naming | `test_band_labels.py / test_metric_descriptions.py / test_inspector_clinical.py / test_tracks.py / test_i18n.py / test_report_thresholds.py` | Consistent ✅ |
| i18n key namespacing | `menu.* / file.* / edit.* / metric.* / view.* / help.* / drop.* / tracks.* / inspector.* / metric.desc.* / metric.tooltip.* / severity.* / fd.* / log.* / compare.* / settings.* / progress.* / about.* / lang.*` | Strong dot-namespace ✅ |
| `metric_bar.label` vs `header.metric` | Both existed; the former is current key, the latter was a stale duplicate that bug-shipped a "Metric" string in zh mode (commit `07f743d` fixed) | Already cleaned |

---

## Priority Actions

### P0 — easy wins, big consistency dividend
1. **Tokenise the 9 GUI hex leaks**:
   - `dialogs.py:467` log severity colors → use `WARN / ERR / OK / ACCENT` tokens
   - `app.py:335` disabled button bg → define `BG_DISABLED = BORDER_STRONG` (or similar) and use it
   - `app.py:1383` + `dialogs.py:455` log Text bg `#0b1117` → define `BG_CODE`
2. **Replace 5 raw font tuples in widget code with FONT_* tokens**:
   - `app.py` Inspector metric name `("Microsoft YaHei UI", 19, "bold")` → add `FONT_INSPECTOR_NAME` (or reuse FONT_DISPLAY shrunk)
   - `app.py` ⓘ glyph `("Microsoft YaHei UI", 14)` → reuse `FONT_TITLE` (also 14)
3. **Document FONT_H2 status**: zero callers in current codebase — drop or reassign.

### P1 — adds explicit structure
4. **Define `SPACE_*` token group** in `theme.py` per `docs/UI_DESIGN.md` §1.4 (4/8/12/16/24/32) — give widget code a vocabulary.
5. **Add `PLOT_*` token group** for matplotlib palette (`PLOT_FG / PLOT_GRID / PLOT_SPINE / PLOT_BG_AX / PLOT_BG_EMPTY / PLOT_OVERLAY_FIT / PLOT_OVERLAY_ANNOT`). Consolidates 8 plot-side hex literals.

### P2 — completeness / polish
6. **Add Esc-to-close** on `CompareDialog / AboutDialog / LogWindow` (Settings already has it).
7. **`ModernPopup` keyboard nav** — arrow keys to move between rows, Enter to invoke. Not blocking; marginal a11y improvement.
8. **Decide naming policy** (legacy vs spec-verbatim) and update `theme.py` docstring accordingly.
9. **Document the design system itself** in `docs/UI_DESIGN.md` — the spec exists but is partial; expand to cover all 12 audited components in the Component Inventory format.

---

## What Already Works Well

- **Single source of truth** for visual constants (`theme.py`); no `tk.Label(bg="#1a1a1a")` cowboy code in widget files.
- **i18n is rigorous** — 31 unit tests guard zh/en symmetry, formula-free descriptions, sibling-key relationships.
- **Severity colour system** — 4 tiers (good/normal/watch/abnormal) consistently mapped to OK/TEXT/WARN/ERR; bands also order-encoded so colour-blind users still get info.
- **Custom widget hierarchy is small + understandable** — only 4 custom widgets (ModernMenubar, ModernPopup, MetricPopup, HoverTooltip), each with a clear single responsibility.
- **Two button variants is right** for an analyzer GUI — Accent (primary) + Ghost (secondary). No proliferation of styles.
