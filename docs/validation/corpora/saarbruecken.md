# Corpus: Saarbrücken Voice Database (SVD)

> Public reference corpus for the **(C) real-corpus behaviour** evidence
> type (PLAN §1). Used to check that metric *distributions* on real voices
> match the literature (e.g. healthy vs pathological separation for PPE,
> CPP, HNR).

## Status

**STAND-IN (Phase 0.5).** The full SVD is not yet downloaded. Validation
phases that only need (A) parity + (B) synthetic GT (jitter, shimmer, F0,
spectral, MFCC …) are **not blocked**. Phases needing (C) — notably
**PPE** (Phase 1.11, target healthy-vs-pathological AUC > 0.7),
**Singer's Formant / SPR**, **MPT** — are **blocked until SVD is wired**.

Until then a tiny local stand-in (`audio/`) is used for smoke-testing the
adapter plumbing only (see [Stand-in](#stand-in-local-audio)).

## The corpus

- **Source**: Saarbrücken Voice Database, Institut für Phonetik, Universität
  des Saarlandes. http://www.stimmdatenbank.coli.uni-saarland.de/
- **Size**: ~2000 speakers, healthy + ~70 pathologies. Free for research.
- **Per recording**: sustained vowels [a, i, u] at neutral/low/high/rising
  pitch + a sentence. Includes simultaneous **EGG** for many sessions —
  directly relevant to VoiceMap's stereo (voice + EGG) mode.
- **Sample rate**: 50 kHz, 16-bit. (Resample to the project rate or pass
  through; document whichever in the metric md.)
- **Labels**: per-speaker pathology label + sex + age; "healthy" cohort
  explicitly marked. This gives the binary label needed for AUC tests.

## Acquisition (when un-blocking Phase C)

1. Export ≥ 50 healthy + ≥ 50 pathological sustained-/a/ recordings (with
   EGG where available) via the SVD web export.
2. Place under `corpora/saarbruecken/{healthy,pathological}/*.wav`
   (kept out of git — `*.wav` is gitignored; store a checksum manifest).
3. Write `corpora/saarbruecken/manifest.json` (schema below).

## Adapter contract

`scripts/validate_metric.py` will consume a corpus via a single JSON
manifest so no metric code hard-codes paths:

```json
{
  "corpus": "saarbruecken",
  "sample_rate": 50000,
  "recordings": [
    {"path": "healthy/0001-a_n.wav",       "label": "healthy",       "egg": true},
    {"path": "pathological/1623-a_n.wav",  "label": "pathological",  "egg": true}
  ]
}
```

A (C)-type validator then computes the metric per recording, splits by
`label`, and asserts the literature-expected separation (e.g. AUC, or
"healthy mean > X"). The exact acceptance number lives in each metric's
own md Section 4.

## Stand-in (local `audio/`)

Three local recordings exercise the adapter end-to-end today. They are
**all essentially healthy / normal voice** (no pathological label), so
they validate plumbing and value ranges — **not** class separation:

| file | channels | note |
|---|---|---|
| `audio/test_Voice_EGG.wav` | stereo (voice + EGG) | primary parity + range fixture |
| `audio/Jiang_Voice_EGG.wav` | stereo (voice + EGG) | second healthy voice |
| `audio/test_Log.aiff` | — | misc smoke input |

`corpora/standin_manifest.json` records this mapping in the adapter schema
so the (C) plumbing can be exercised before SVD lands.

## Alternative / supplementary corpora

- **MEEI** (Massachusetts Eye & Ear, Elemetrics KayPENTAX disordered voice
  database) — see `corpora/meei.md` (to be added). Licensed, not free.
- **VOICED** (PhysioNet) — free, 208 voices, healthy + pathological, no EGG.
  Good free fallback if SVD export is impractical.
