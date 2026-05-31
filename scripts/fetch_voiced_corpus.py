#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch a balanced subset of the VOICED corpus (PhysioNet) for (C)-type
real-corpus validation — the free fallback documented in
`docs/validation/corpora/saarbruecken.md`.

VOICED = "VOICe ICar fEDerico II" database (Cesari et al. 2018), 208 subjects,
sustained /a/ vowels, 8 kHz, with a per-subject `Diagnosis` (healthy vs four
dysphonia families). PhysioNet, Open Data Commons ODC-BY 1.0 — free for
research with attribution.

This downloads N healthy + N pathological recordings, converts the ASCII
sample files to 8 kHz WAV, and writes a manifest in the adapter schema
(`docs/validation/corpora/saarbruecken.md` §"Adapter contract"). The WAVs are
gitignored; only this script + the manifest are tracked, so the corpus is
reproducible without committing audio.

Usage:
    python scripts/fetch_voiced_corpus.py            # 50 healthy + 50 patho
    python scripts/fetch_voiced_corpus.py --n 30
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import urllib.request

import numpy as np
import soundfile as sf

BASE = "https://physionet.org/files/voiced/1.0.0/"
SR = 8000
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "docs", "validation", "corpora", "voiced")


def _get(url: str, timeout: float = 60.0) -> bytes:
    return urllib.request.urlopen(url, timeout=timeout).read()


def _diagnosis(rid: str) -> str:
    try:
        txt = _get(BASE + rid + "-info.txt").decode("utf-8", "replace")
        m = re.search(r"Diagnosis:\s*(.+)", txt)
        return m.group(1).strip() if m else "?"
    except Exception as e:                              # noqa: BLE001
        return f"ERR:{type(e).__name__}"


def _label(dx: str) -> str | None:
    d = dx.lower()
    if d == "healthy":
        return "healthy"
    if d.startswith("err") or d == "?":
        return None
    return "pathological"


def _fetch_wave(rid: str, label: str) -> dict | None:
    """Download voiceNNN.txt, write 8 kHz wav. Returns manifest row or None."""
    try:
        raw = _get(BASE + rid + ".txt").decode("ascii", "replace")
        x = np.array([float(v) for v in raw.split() if v], dtype=np.float64)
        if x.size < SR:                                # < 1 s → skip
            return None
        peak = np.max(np.abs(x)) or 1.0
        x = (x / peak * 0.95).astype(np.float32)
        rel = f"{label}/{rid}.wav"
        path = os.path.join(OUT_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sf.write(path, x, SR, subtype="FLOAT")
        return {"path": rel, "label": label, "egg": False, "id": rid}
    except Exception as e:                              # noqa: BLE001
        print(f"  ! {rid}: {type(e).__name__}: {e}")
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50,
                    help="recordings per class (healthy / pathological)")
    args = ap.parse_args()

    print("Fetching VOICED diagnoses (208 subjects)…")
    rids = [f"voice{i:03d}" for i in range(1, 209)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        dxs = list(ex.map(_diagnosis, rids))
    healthy = [r for r, dx in zip(rids, dxs) if _label(dx) == "healthy"]
    patho = [r for r, dx in zip(rids, dxs) if _label(dx) == "pathological"]
    print(f"  healthy={len(healthy)}  pathological={len(patho)}")

    take_h = healthy[: args.n]
    take_p = patho[: args.n]
    print(f"Downloading {len(take_h)} healthy + {len(take_p)} pathological wavs…")

    rows: list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_fetch_wave, r, "healthy"): r for r in take_h}
        futs.update({ex.submit(_fetch_wave, r, "pathological"): r
                     for r in take_p})
        for fut in concurrent.futures.as_completed(futs):
            row = fut.result()
            if row:
                rows.append(row)

    rows.sort(key=lambda r: r["id"])
    manifest = {"corpus": "voiced",
                "source": BASE,
                "license": "ODC-BY 1.0 (PhysioNet)",
                "sample_rate": SR,
                "n_healthy": sum(r["label"] == "healthy" for r in rows),
                "n_pathological": sum(r["label"] == "pathological" for r in rows),
                "recordings": rows}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Wrote {len(rows)} wavs + manifest.json to {OUT_DIR}")
    print(f"  healthy={manifest['n_healthy']}  "
          f"pathological={manifest['n_pathological']}")


if __name__ == "__main__":
    main()
