# VoiceMap Accessibility Audit (WCAG 2.1 AA)

> Run via `/design:accessibility-review` 2026-05-10
> Target: VoiceMap v1.0.0-dev desktop GUI (Tkinter on Windows 11)

## Caveat — desktop tooling vs. WCAG-as-written

WCAG 2.1 was written for the web. Tkinter has **inherent platform-level
a11y constraints** that no app-level fix can override:

- `tk.Frame` / `tk.Canvas` widgets don't expose roles to MSAA / UI
  Automation by default — Microsoft Narrator reads them as opaque
  panels. `ttk` widgets DO expose roles (Button, Entry, Combobox)
  natively.
- Custom drawn UI (our `ModernPopup`, `ModernMenubar`, `MetricPopup`)
  are tk Toplevels with `tk.Frame` rows — Narrator sees the popup as
  a single window, not as a list of menu items.
- Native menu (`tk.Menu`) WOULD expose role=menu/menuitem to assistive
  tech. We chose `ModernPopup` to bypass the white border (Win32 USER
  chrome) — accessibility was the trade.

So this audit applies WCAG criteria where they map cleanly, and notes
"platform-limited" where the standard expects something Tkinter can't
deliver.

---

## Summary

| | |
|---|---|
| **Standard** | WCAG 2.1 AA |
| **Platform** | Tkinter on Windows 11, Microsoft YaHei UI font |
| **Issues found** | 8 (1 critical, 4 major, 3 minor) |
| **Critical** | 1 — placeholder text fails AA contrast |
| **Major** | 4 — keyboard nav coverage, focus indicators, custom popups opaque to AT, hover-row-only state |
| **Minor** | 3 — touch targets, border contrast, language switch announcement |

---

## Findings

### Perceivable

| # | Issue | Criterion | Severity | Recommendation |
|---|---|---|---|---|
| P-1 | `TEXT_MUTED` (`#737373`) on `PANEL` measures **3.67:1** for placeholder / disabled / caption text. Fails 1.4.3 (≥ 4.5:1 for normal text). | 1.4.3 Contrast (Min) | 🔴 Critical | Lift `TEXT_MUTED` to `#8a8a8a` (≥ 4.5:1) or `#959595` (≥ 5:1). Updates 1 token in `theme.py`, propagates everywhere. |
| P-2 | Track row hover (`PANEL_HI` over `PANEL`) is only **1.21:1** non-text contrast — invisible to users with low contrast sensitivity. | 1.4.11 Non-text Contrast | 🟡 Major | Already mitigated: 4 px ACCENT marker on the active row provides multi-modal feedback (`8.10:1`). Document this in the audit but no code change needed. |
| P-3 | `BORDER` (`#3a3a3a`) divider on `PANEL` is **1.53:1** — used for menubar / inspector card edges. | 1.4.11 Non-text Contrast | 🟢 Minor | tk renders 1 px crisp lines so the BORDER is noticeable in motion. Acceptable. If clinically reviewed: bump to `#5a5a5a` (`2.7:1`). |
| P-4 | `ERR` (`#ef4444`) severity color on `PANEL` measures **4.62:1**, just over AA. Passes for normal text but tight; fails AAA. | 1.4.3 Contrast (Min) | 🟢 Minor | Acceptable. If targeting AAA, switch to `#f87171` (`5.4:1`). Severity is also encoded by tier order (good/normal/watch/abnormal) so colorblind users get info without relying on color. |

### Operable

| # | Issue | Criterion | Severity | Recommendation |
|---|---|---|---|---|
| O-1 | Track rows in Tracks Panel are clickable but not Tab-focusable; pressing Tab skips them. | 2.1.1 Keyboard | 🟡 Major | Add `takefocus=1` to row outer Frame + bind `<Return>` and `<space>` to row click handler. Add visible focus ring (4 px BORDER overlay when focused). |
| O-2 | `ModernPopup` has no keyboard navigation — Esc dismisses (works) but Up/Down arrow / Enter to activate items don't. | 2.1.1 Keyboard | 🟡 Major | Bind `<Up>` / `<Down>` to move highlight, `<Return>` to activate. Track currently highlighted row index in popup state. Cascade open via `<Right>`, close sub via `<Left>`. |
| O-3 | Several action buttons (`metric_btn`, `prev_btn` / `next_btn` ◀▶ canvas-edge arrows, ⓘ glyph) lack visible focus indicators despite being focusable. | 2.4.7 Focus Visible | 🟡 Major | Bind `<FocusIn>` / `<FocusOut>` on each to swap a 1-2 px ACCENT outline. ttk.Button already shows focus ring — the issue is custom tk.Label / tk.Button widgets used for icons and arrows. |
| O-4 | Inspector ⓘ glyph and metric name are clickable for tooltips but trigger only on hover, not on focus + Enter. Keyboard-only users can't read tooltips. | 2.1.1 Keyboard | 🟢 Minor | Add `<KeyPress-F1>` or `<Return>` binding when widget has focus → show the tooltip. Auto-dismiss on FocusOut. |
| O-5 | Touch targets: `metric.prev` / `metric.next` Label buttons measure ~80 × 24 px (height under 44 px guideline). | 2.5.5 Target Size | 🟢 Minor | Desktop convention is ~28-32 px tall; the 44 px guideline is for touchscreens. Acceptable for keyboard + mouse. Worth a one-line increase to `pady=8` if expanding to tablets. |

### Understandable

| # | Issue | Criterion | Severity | Recommendation |
|---|---|---|---|---|
| U-1 | Language switch (帮助 → 语言 → 中文/English) re-renders the menubar live. Screen reader users may miss the announcement. | 3.2.1 On Focus, 4.1.3 Status Messages | 🟢 Minor | After `set_language()`, write to `log_text` widget (already wired up to status announcements via `_append_log("META", ...)`); add an aria-live equivalent — e.g. announce "language switched to [lang]" via `app.bell()` or a status pill flash. |
| U-2 | All form inputs (Settings dialog: Spinboxes for clarity / cluster k / output dir) have visible labels next to them — labels-attached relationship is positional, not semantic. | 3.3.2 Labels or Instructions | ✓ OK | ttk.Label adjacent to ttk.Spinbox is the documented pattern; MSAA picks it up via Spinbox's `name` derived from preceding Label. No change. |

### Robust

| # | Issue | Criterion | Severity | Recommendation |
|---|---|---|---|---|
| R-1 | Custom-drawn `ModernMenubar` / `ModernPopup` / `MetricPopup` expose only as opaque tk Toplevel windows to UI Automation. Narrator reads them as "window" not "menu / menuitem". | 4.1.2 Name, Role, Value | 🟡 Major | Platform-limited. Workarounds: (a) maintain a parallel native `tk.Menu` mirror activated via `<Alt+F>` etc. — a11y users get the standard menu, sighted users get the styled one; (b) live with it, since the `ttk.Button` on canvas + keyboard shortcuts (Ctrl+O, Ctrl+S, Ctrl+,) still work for power users. |
| R-2 | Status icon (●) in header reads as "●" or nothing in Narrator. | 4.1.2 Name, Role, Value | 🟢 Minor | Add `tooltip` text via the existing `HoverTooltip` mechanism; UI Automation will read tooltip text on focus. |

---

## Color Contrast Check (computed against current `theme.py`)

| Pair | Ratio | AA (≥4.5) | AAA (≥7) |
|---|---|---|---|
| primary text on window BG | 18.16 : 1 | ✓ | ✓ |
| primary text on panel | 15.96 : 1 | ✓ | ✓ |
| text on hover row (PANEL_HI) | 13.17 : 1 | ✓ | ✓ |
| BG-on-ACCENT (button hovered) | 9.22 : 1 | ✓ | ✓ |
| MUTED secondary text | 6.90 : 1 | ✓ | ✗ |
| **TEXT_MUTED placeholder** | **3.67 : 1** | **✗** | ✗ |
| ACCENT section heading | 8.10 : 1 | ✓ | ✓ |
| OK / WARN severity tags | 8.10–8.81 : 1 | ✓ | ✓ |
| ERR severity tag | 4.62 : 1 | ✓ | ✗ |

**UI-component contrast (≥ 3:1 required by 1.4.11)**

| Component | Ratio | Pass |
|---|---|---|
| Hover row vs normal row | 1.21 : 1 | ✗ (mitigated by 4 px ACCENT marker — multi-modal) |
| BORDER divider on PANEL | 1.53 : 1 | ✗ |
| ACCENT row marker on PANEL | 8.10 : 1 | ✓ |
| Card edge (PANEL on BG) | 1.14 : 1 | ✗ (mitigated by padding) |
| Disabled button bg | 2.53 : 1 | ✗ (close, marginal) |

---

## Keyboard Navigation Status

| Element | Tab to | Enter / Space | Esc | Arrow keys |
|---|---|---|---|---|
| ttk.Button (Settings, Compare, Accent) | ✓ | ✓ | dialog: ✓ | n/a |
| ttk.Spinbox / Combobox (Settings) | ✓ | ✓ | n/a | ✓ inc/dec |
| Drop zone (Tracks empty state) | ✗ | ✗ | n/a | n/a |
| Track row | ✗ | ✗ | n/a | n/a |
| metric_btn (canvas amber pill) | ✓ via tk.Button | ✓ | n/a | ✗ |
| Prev / Next nav (metric bar) | ✗ (Label, no focus) | ✗ | n/a | global ←→ if bound |
| Canvas-edge ◀ ▶ arrows | ✗ | ✗ | n/a | n/a |
| ModernPopup item rows | ✗ | mouse only | ✓ | ✗ |
| Cascade arrow | ✗ | hover only | n/a | ✗ |

**Global shortcuts already wired** (good): Ctrl+O (open WAV), Ctrl+S (save image), Ctrl+, (settings), ←/→ (cycle metric).

---

## Screen Reader Behaviour (Microsoft Narrator)

| Element | Read As | Issue |
|---|---|---|
| ttk.Button (e.g. Settings save) | "Save button" + label text | ✓ OK |
| ttk.Combobox (Compare metric picker) | "Combo box, CPP" + label | ✓ OK |
| Inspector metric name (tk.Label) | the text only | ✓ OK |
| Inspector ⓘ glyph | "ⓘ" character or silence | ⚠️ no role exposed |
| ModernPopup (Help / View etc.) | "Window, no name" | ✗ no menu role |
| Popup row | not announced (Frame children) | ✗ no menuitem role |
| Track row | not announced | ✗ |
| Drop zone | not announced | ✗ |
| Canvas (matplotlib) | "Drawing" or "Image" | ✓ matplotlib provides alt-text via figure.set_title; readable via toolbar |

---

## Priority Fixes

### 🔴 Critical (do before v1.0.0)
1. **P-1** — bump `TEXT_MUTED` from `#737373` to `#8a8a8a` so placeholder / unit hints / disabled labels meet AA 4.5:1. One-line edit in `theme.py`. Affects ~10 widget sites.

### 🟡 Major (do before A1 software-copyright submission, where reviewer accessibility is plausible)
2. **O-1** — Tab-focusable track rows + Enter/Space activation + visible focus ring.
3. **O-2** — keyboard nav inside ModernPopup (Up/Down/Enter, Left/Right for cascades).
4. **O-3** — focus-visible indicator on tk.Label-as-button widgets (ⓘ, ◀, ▶, Prev/Next).
5. **R-1** — accept platform-limited or invest in a parallel `tk.Menu` mirror (~3 hours).

### 🟢 Minor (post-v1.0.0)
6. **O-4** — keyboard tooltip trigger.
7. **O-5** — only relevant for tablet deployments.
8. **U-1** — `app.bell()` or status flash on language switch.
9. **R-2** — tooltip text on status dot.
10. **P-3** — bump BORDER if a clinical reviewer flags it.

---

## What Already Works

- Strong primary-text contrast everywhere (15-18:1).
- All severity tiers pass AA; tier ordering encodes severity in addition to color (good < normal < watch < abnormal) — colorblind users still understand.
- `ttk.Button` / `ttk.Spinbox` / `ttk.Combobox` use the OS-native focus ring + screen-reader role.
- Most-used keyboard shortcuts already wired (Ctrl+O / Ctrl+S / Ctrl+, / ←/→ / Esc-to-close on dialogs).
- Heatmap plots use perceptually-uniform `viridis` / `coolwarm` / Okabe-Ito 5-class — colorblind-safe and printable.
- Language switch via menu, persists across restarts; both languages tested 31/31 unit tests.
- High-DPI awareness via `SetProcessDpiAwareness(2)` so text scales rather than rasterises.

---

## Out of scope

- WCAG 2.2 (2023) — not yet AA-required for software-copyright filing.
- Cognitive-load criteria (3.3.5 Help, 3.3.6 Error Prevention) — single-user clinical workflow without irreversible actions, low cognitive risk.
- Time-based criteria (2.2.x) — VoiceMap has no auto-refresh / time-out.
- Reduced motion — VoiceMap has no animations beyond matplotlib draw.
