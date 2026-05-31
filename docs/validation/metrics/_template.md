# <Metric Name>

## 1. Implementation
- File: `voicemap/<file>.py`
- Class / function: `<Class>.<method>`
- Lines: <start>-<end>
- Dependencies: <list other internal modules used>

## 2. Reference Standard
- Author / year / paper title:
- Algorithm sketch (one paragraph):
- Formulas (LaTeX or plain text):
- Reference implementation we compare against (Praat / librosa / etc.):

## 3. Test Signals
**Synthetic** (from `docs/validation/test_signals/`):
- `<file>.wav` — purpose

**Real** (from `audio/` or corpora):
- `<file>` — purpose

## 4. Validation Method
Pick one or more of:
- **(A) Numerical parity** vs `<reference tool>`.
  - Tolerance: `atol=` or `rtol=`
  - Acceptance: e.g. `median |Δ| < 0.5 dB`
- **(B) Synthetic ground truth**:
  - Input: signal with known property X
  - Expected output: Y
  - Tolerance: ε
- **(C) Real corpus behavior**:
  - Corpus: <name>
  - Expected: e.g. "healthy mean > 20 dB"

Exact reproducible steps:
```bash
python scripts/validate_metric.py <metric_name>
```

## 5. Results

| Test | Reference | Our Value | Δ | Pass? |
|---|---|---|---|---|
| ... | ... | ... | ... | ✓ / ✗ |

Optional plots embedded as relative paths.

## 6. Status
**PASS** | FAIL | IN_PROGRESS
- validated_on: YYYY-MM-DD
- session: <id>
- validator: <name or session note>

## 7. Known Limitations
- e.g. "Fails for F0 < 60 Hz"
- e.g. "Window length sensitivity not characterised"

## 8. Change Log
- 2026-MM-DD — <what changed> (commit <sha>)
- ...
