# VoiceMap GUI Design Critique

> Run via `/design:design-critique` 2026-05-10
> Stage: **final polish** (v1.0.0 prep)
> Target: 1600 × 1180 default Tk window, dark + amber palette, Win11 100-150% DPI

## Overall Impression

The interface reads as a **competent dark-mode scientific tool** — close cousins are Audacity, Praat, and the SuperCollider analyzer this project descends from. The amber-on-charcoal palette (`#f59e0b` on `#1a1a1a`) gives it a "studio recording" feel rather than a clinical one, which actually flatters the multi-modal use case (clinical + voice training + research).

**Biggest opportunity**: The first-second eye path is fragmented. There are 5 amber accents fighting for attention on initial open (header title, tracks label, metric label, metric button, action button), and the canvas area where the actual analysis lives takes up only 50% of the visual weight. A small reduction in amber density would make the canvas read as the hero, which it should be.

---

## First Impression (2-second test)

| | |
|---|---|
| What draws the eye first | The **Tracks Panel** (~160 px tall, second from top) — because it's the only thing with a 4 px ACCENT marker stripe + drop-zone with bold "拖入 .wav…" |
| Is that correct? | ✓ for first-time users (need to load a file) but ✗ for repeat users (the canvas + Inspector should dominate after first analysis) |
| Emotional reaction | "Professional / dense / safe" — no playful mascot, no marketing chrome. Good for clinical credibility. |
| Is the purpose clear? | ✓ Stereo WAV → voice map heatmap. The placeholder "♪ + 打开文件或文件夹以开始" + axis labels (MIDI 30-96, SPL 40-120 dB) tells the user this is voice acoustics within 1-2 seconds. |

---

## Usability

| Finding | Severity | Recommendation |
|---|---|---|
| **Inspector value pill is in the bottom-right corner** while the user's hover is on the heatmap (top-center). The eye has to dart 700 px diagonally to read the value at the cell they just hovered. | 🟡 Moderate | Add an inline cell readout floating near the cursor (matplotlib's existing `text()` annotation), keep the pill as the persistent focal value. The pill stays useful for "tab away then come back" but the inline readout matches eye gaze. |
| **Metric bar hierarchy reads as 4 equal entries** ("指标" label / metric_btn / Prev / Next) — but Prev/Next are secondary navigation, not primary controls. They visually balance the metric_btn so users may try to "click" them as the primary toggle. | 🟢 Minor | Drop Prev/Next opacity to ~70% (use `MUTED` instead of default fg in idle state — already partially done) and reduce font size by 1pt. The recently-added arrow glyph (← / →) helps. |
| **The metric button is 312 × 55 px** — bigger than ttk.Buttons in the dialogs (which are ~80 × 28 px). This implicitly trains the user that clicking it is the main action. Probably correct, but worth verifying the size matches user expectation of "click here to switch metric". | ✓ OK | The size is intentional and consistent with action hierarchy: load file → pick metric → see result. Keep it. |
| **Drop zone has a hover state (amber border)** but no equivalent keyboard "drop here when focused" indicator. Tab + Enter should also pick a file. | 🟢 Minor | (Already covered by Ctrl+O / Ctrl+Shift+O global shortcuts after a11y O-1 / R-1 fixes.) |
| **No undo / redo** for analysis state. If user runs analysis on wrong file, they re-pick + re-run. | 🟢 Minor | Acceptable for a scientific tool — analysis is deterministic, "redo by re-running" is the convention. Not worth changing. |

---

## Visual Hierarchy

**The heads-up axis** (top to bottom):

| z | Element | Visual weight | Should it be? |
|---|---|---|---|
| 1 | Menubar (32 px) | Low — neutral PANEL bg, no accent | ✓ |
| 2 | Header title `嗓音声学品质多维分析图谱` (FONT_TITLE 14 bold, ACCENT) | High | Slightly too high. Currently the longest amber text on screen. Consider `MUTED` text colour and let the canvas's metric title (e.g. "CPP [dB]") carry the analytical ID. |
| 3 | Tracks Panel (162 px) | High when tracks present (orange marker stripe), Medium when empty | Empty state is fine. Loaded state is the biggest visual weight allocation in the chrome — if user has 5 tracks, this can take 25% of the window vertical without contributing to the analysis. The 145 px viewport cap is the right move; consider 110 px instead. |
| 4 | Metric Bar (67 px) | High | ✓ The metric is the "current view" identifier — should be prominent. |
| 5 | Canvas + Inspector (812 px) | Should be highest | ✓ Canvas is white-on-dark-frame, contrast pulls the eye in. Inspector is properly secondary (PANEL bg, smaller fonts). |
| 6 | Status Bar (34 px) | Low | ✓ |

**Reading flow**: top → tracks → metric → main pane. This is correct top-to-bottom for first-time use ("what file → what metric → what does it look like"). For repeat use the user wants to skip 1-3 and go straight to 4-5. The fact that Tracks Panel can be scrolled (cap 145 px) AND the metric bar is one-line tall does the right thing.

**Emphasis check**:
- ✓ Active track row marked by 4 px ACCENT stripe + PANEL_HI bg.
- ✓ Active metric pill has ACCENT_HI bg.
- ✓ Inspector metric name in 19 pt bold ACCENT — clearly the focal element.
- ⚠️ Inspector "本次值" (Current value) header in 11 pt bold ACCENT — fights with the metric name above it. The two ACCENT-colored bold elements 200 px apart in a 420 px column is busy.

---

## Consistency

| Element | Issue | Recommendation |
|---|---|---|
| **Padding scale** | App uses `2/3/4/6/8/10/12/14/16/18` half-pixel-grid in different places. UI_DESIGN.md spec calls for `4/8/12/16/24/32` 8-point grid. | Audit → consolidate to spec's 8-point scale. Defines `SPACE_XS=4 / SPACE_S=8 / …` token in `theme.py`. (Already in P1 audit list.) |
| **Button corner radius** | ttk.Button uses Tk's default ~2 px radius. Drop zone has a thicker frame border. Cards have no border-radius (Tk frames are square). | Tk doesn't natively support border-radius on Frames. Either accept square cards (current) or apply Win32 SetWindowRgn (already used on popups). For a "studio" aesthetic, square is fine — keep. |
| **Severity color use** | OK / WARN / ERR are used consistently in clinical bands ✓. They're ALSO used in the log window for INFO / WARN / ERR severity ✓. ACCENT is used both for "brand" AND for "active state" (active row marker, hovered button) — slight overload. | Acceptable. The amber-as-active-and-brand convention is consistent across the app, no real ambiguity. |
| **Font scale** | After last week's commits the scale is reasonably consistent: 9 / 10 / 11 / 11b / 12 / 13b / 14b (header) / 15b (unused) / 19b (Inspector) / 22b (Inspector value). 9 layers feel like a lot. | Drop FONT_H2 (15 pt, no callers); rename FONT_INSPECTOR_NAME → FONT_DISPLAY (already inverted: FONT_DISPLAY=22 bold → drop, replace by FONT_INSPECTOR_NAME=19). Net: 7 layers. (Tagged as P1 in audit.) |
| **Track row vs popup row spacing** | Track row is 28 px tall (compact). ModernPopup row is ~32-36 px (one-line padded label). They look similar but aren't. | Acceptable — they serve different purposes (track = data row, popup = action row). |
| **i18n integrity** | All user-visible text goes through `tr()`. zh⇔en symmetry verified by `test_i18n.py` and `test_metric_descriptions.py` (31 tests). | ✓ |

---

## Accessibility

(Detailed in `docs/ACCESSIBILITY_AUDIT.md`. Summary here.)

- ✓ Primary text contrast ≥ 13:1 everywhere → AAA.
- ✓ TEXT_MUTED placeholder bumped from 3.67:1 to 5.04:1 → AA pass.
- ✓ Severity colors all ≥ 4.5:1 (WARN/OK 8:1, ERR 4.6:1).
- ✓ All custom Label-buttons (◀/▶/Prev/Next/ⓘ/Track row) Tab-focusable with 2 px ACCENT focus ring.
- ✓ ModernPopup keyboard navigable (↑↓/Enter/←→).
- ✓ All menu actions have global shortcuts (Ctrl+E/R/D + F1/F2 + ←→).
- ⚠️ ModernPopup invisible to screen readers (platform limitation). Compensated by global shortcuts — blind users can drive the app without the visual menu.

---

## What Works Well

1. **The Inspector hover-update flow** — moving the cursor over a heatmap cell instantly updates the value pill (live readout via `motion_notify_event`). It's responsive, doesn't lag, and the severity color follows the clinical band. This is one of the most polished interactions in the app.

2. **The unified i18n + design-token architecture** — change one constant in `theme.py`, the entire UI follows. No `tk.Label(bg="#xxx")` cowboy code anywhere. After the recent token migration (commits `02ea3a5` → `c52b128`), the project has 0 GUI hex leaks.

3. **Modern colormap policy** — viridis / coolwarm / Okabe-Ito 5 across all 80 metrics replaces the old HSV rainbow sweeps. Colorblind-safe + print-friendly + perceptually uniform. This is the move that elevates the heatmaps from "1990s scientific tool" to "2026 publication-ready".

4. **HoverTooltip with formula details** — the ⓘ glyph + 500 ms hover delay + 440 px wraplength + zh tooltips going full NBSP shows real attention to typography. Most desktop tools don't get this right.

5. **Compare dialog responsive sizing** — 90% of screen width, auto-fits to canvas via `<Configure>` → `set_size_inches` + `tight_layout`. No more fixed 1500x640 that cropped the third subplot.

6. **The 4-tier severity system** (good / normal / watch / abnormal) is encoded both in color AND tier order — colorblind users still understand "abnormal > watch > normal > good" from position, no color reliance.

---

## Priority Recommendations (final-polish stage)

### Do before v1.0.0 tag
1. **Cool down the header app title** — change `_header_title` from ACCENT to TEXT (white). The brand color on a 14 pt bold title competes with the canvas's matplotlib title (e.g. "CPP [dB]") which is the analytical brand of the moment. Result: amber is reserved for "active state / interactive" everywhere; "嗓音声学品质多维分析图谱" reads as a softer overhead label.

2. **Inline cell readout near cursor** — when user hovers the heatmap, a small `(MIDI=60, SPL=85, value=18.2)` bubble follows the mouse. The Inspector value pill 700 px away keeps for navigation; the bubble closes the eye-gaze loop. ~30 lines of matplotlib code.

3. **Drop FONT_H2** (no callers); document the scale in `theme.py` docstring as a 7-layer ladder.

### Nice for v1.0.x next sprint
4. **Tracks Panel viewport** — drop from 145 px to 110 px (4-row cap instead of 5). Saves 35 px vertical for the canvas.

5. **Inspector "本次值" header** — drop ACCENT, use TEXT bold instead. Reduce visual fight with the metric name.

### Backlog
6. Padding scale → consolidate to `SPACE_XS / S / M / L / XL` from spec.
7. Inline tooltip for status dot (the • in the header status pill) describing analysis state in words.
8. Custom toolbar at top of canvas for matplotlib's pan/zoom/reset (currently hidden — power users may want it).
