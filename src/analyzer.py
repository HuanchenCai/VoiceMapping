#!/usr/bin/env python3
"""
VoiceMap Voice Range Profile Analyzer
Complete implementation of VoiceMap algorithms for VRP analysis
"""

import time
import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import butter, filtfilt, lfilter, fftconvolve
import os
import re
from datetime import datetime
from typing import Dict, Optional, Tuple
import logging

from config import VoiceMapConfig, DEFAULT_CONFIG
from logger import setup_logger, get_logger
from plotter import plot_vrp_dataframe, plot_vrp_combined
from metrics import (
    SPLCalculator, ClarityCalculator, CPPCalculator, SpecBalCalculator,
    CrestCalculator, QcontactCalculator, EntropyCalculator, HRFCalculator,
    ClusterCalculator, PhonClusterCalculator,
    PerturbationCalculator, HNRCalculator,
    VibratoCalculator, FormantCalculator, HarmonicDiffCalculator,
    OpenQuotientCalculator,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Numba JIT for sequential-dependency loops (falls back to pure Python)
# ---------------------------------------------------------------------------
try:
    from numba import njit as _njit
    _NUMBA = True
except ImportError:
    def _njit(fn):          # identity decorator fallback
        return fn
    _NUMBA = False


def _build_fir_bp_impulse() -> np.ndarray:
    """Build zero-phase FIR impulse response matching SC type=3 EGG bandpass filter.

    SC VRPSDIOfilterCoeffs.sc type=3:
      skirtHP = [0, 2.14897e-05, 0.061962938, 0.4636971375, 0.9199227347]  (bins 0-4)
      passband = 1.0 * 465                                                  (bins 5-469)
      skirtLP  = 10^(-0.01*i) for i=0..553                                 (bins 470-1023)
    This is a frequency-domain magnitude transfer function for FFT size 2048.
    """
    mags = np.zeros(1024)
    mags[0:5] = [0.0, 2.14897e-05, 0.061962938, 0.4636971375, 0.9199227347]
    mags[5:470] = 1.0
    mags[470:1024] = 10.0 ** (-0.01 * np.arange(554))
    # Add Nyquist bin (bin 1024 for 2048-pt FFT) ≈ 0 (LP already attenuated)
    mags_full = np.concatenate([mags, [mags[-1]]])
    # Zero-phase: irfft of real spectrum gives symmetric impulse response
    h = np.fft.irfft(mags_full, n=2048)
    return np.fft.fftshift(h)   # center impulse at index 1024


# Pre-build FIR impulse response once at module load
_FIR_BP_IMPULSE = _build_fir_bp_impulse()


def _pv_compander(signal: np.ndarray, thresh: float,
                  slope_below: float = 4.0,
                  fft_size: int = 2048, hop: int = 1024) -> np.ndarray:
    """Block-wise downward expander approximating SC PV_Compander.

    SC: PV_Compander(chain, thresh, 4.0, 1.0)
        "4.0 is dB-expand ratio below thresh"
    Below threshold, each FFT bin magnitude is scaled by (mag/thresh)^(slope_below-1).
    Above threshold: unity gain.
    """
    if thresh <= 0.0:
        return signal.copy()

    N = len(signal)
    output = np.zeros(N + fft_size, dtype=np.float64)
    norm   = np.zeros(N + fft_size, dtype=np.float64)
    win    = np.hanning(fft_size)
    win_sq = win * win

    for i in range(0, N, hop):
        frame = np.zeros(fft_size, dtype=np.float64)
        end   = min(i + fft_size, N)
        frame[:end - i] = signal[i:end]
        frame_win = frame * win

        X   = np.fft.rfft(frame_win)
        mag = np.abs(X)

        # Downward expansion below threshold
        safe = np.maximum(mag, 1e-15)
        scale = np.where(mag >= thresh, 1.0, (safe / thresh) ** (slope_below - 1))
        X *= scale

        y = np.fft.irfft(X, n=fft_size)
        output[i:i + fft_size] += y * win
        norm  [i:i + fft_size] += win_sq

    norm = np.maximum(norm, 1e-12)
    return (output / norm)[:N]


@_njit
def _peak_follower_inner(signal: np.ndarray, decay: float) -> np.ndarray:
    """O(N) peak follower — compiled with numba when available."""
    output = np.empty_like(signal)
    peak = 0.0
    for i in range(len(signal)):
        v = signal[i]
        if v > peak:
            peak = v
        else:
            peak *= decay
        output[i] = peak
    return output


@_njit
def _set_reset_ff_inner(set_sig: np.ndarray, reset_sig: np.ndarray) -> np.ndarray:
    """O(N) set-reset flip-flop — compiled with numba when available."""
    output = np.empty_like(set_sig)
    state = 0.0
    for i in range(len(set_sig)):
        if set_sig[i] > reset_sig[i]:
            state = 1.0
        elif reset_sig[i] > set_sig[i]:
            state = 0.0
        output[i] = state
    return output


class VoiceMapAnalyzer:
    """VoiceMap Voice Range Profile Analyzer"""

    def __init__(self, config: Optional[VoiceMapConfig] = None):
        self.config = config or DEFAULT_CONFIG

        self.spl_calculator      = SPLCalculator(self.config)
        self.clarity_calculator  = ClarityCalculator(self.config)
        self.cpp_calculator      = CPPCalculator(self.config)
        self.specbal_calculator  = SpecBalCalculator(self.config)
        self.crest_calculator    = CrestCalculator(self.config)
        self.qcontact_calculator = QcontactCalculator(self.config)
        self.entropy_calculator  = EntropyCalculator(self.config)
        self.hrf_calculator      = HRFCalculator(self.config)
        self.cluster_calculator  = ClusterCalculator(self.config)
        self.phon_calculator     = PhonClusterCalculator(self.config)
        self.perturb_calculator  = PerturbationCalculator(self.config)
        self.hnr_calculator      = HNRCalculator(self.config)
        self.vibrato_calculator  = VibratoCalculator(self.config)
        self.formant_calculator  = FormantCalculator(self.config)
        self.harmdiff_calculator = HarmonicDiffCalculator(self.config)
        self.oq_calculator       = OpenQuotientCalculator(self.config)

        logger.info("VoiceMap analyzer initialized (numba=%s)", _NUMBA)

    # ------------------------------------------------------------------
    # Centroid I/O (EGG-shape clusters).
    # Format: semicolon-delimited CSV. Header row:
    #   "# FonaDyn cluster centroids  k=<k>  n_harm=<n>  dim=<3n>"
    # Then one row per centroid: cluster_id;feat_0;feat_1;...;feat_{dim-1}
    # ------------------------------------------------------------------
    def save_centroids(self, path: str) -> None:
        cent = self.cluster_calculator.centroids_
        if cent is None:
            raise ValueError("No trained centroids yet — run an analysis first")
        n_harm = self.cluster_calculator.n_harmonics
        dim = cent.shape[1]
        k = cent.shape[0]
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# FonaDyn cluster centroids  k={k}  n_harm={n_harm}  dim={dim}\n")
            f.write("cluster;" + ";".join(f"f{i}" for i in range(dim)) + "\n")
            for i in range(k):
                row = [str(i + 1)] + [f"{v:.6g}" for v in cent[i]]
                f.write(";".join(row) + "\n")
        logger.info("Centroids saved: %s (k=%d, dim=%d)", path, k, dim)

    def load_centroids(self, path: str) -> None:
        header_n = None
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#"):
                    m = re.search(r"n_harm\s*=\s*(\d+)", s)
                    if m:
                        header_n = int(m.group(1))
                    continue
                parts = s.split(";")
                if parts[0].lower().startswith("cluster"):
                    continue   # skip column header
                rows.append([float(x) for x in parts[1:]])
        if not rows:
            raise ValueError(f"No centroid rows found in {path}")
        cent = np.asarray(rows, dtype=np.float64)
        self.cluster_calculator.centroids_ = cent
        self.cluster_calculator.n_clusters = cent.shape[0]
        if header_n is not None:
            self.cluster_calculator.n_harmonics = header_n
        logger.info("Centroids loaded: %s  k=%d  dim=%d",
                    path, cent.shape[0], cent.shape[1])

    # ------------------------------------------------------------------
    # Multi-recording joint centroid training.
    # Pools per-cycle EGG shape features across every wav in the list,
    # runs a single K-means fit, stashes the centroids on this analyzer
    # *and* returns them so the caller can save_centroids() to disk.
    # This is the canonical way to get cross-subject cluster-label parity.
    # ------------------------------------------------------------------
    def train_cluster_centroids(self, wav_paths, *,
                                 n_clusters: Optional[int] = None,
                                 n_harmonics: Optional[int] = None,
                                 random_state: int = 0,
                                 progress_cb=None) -> np.ndarray:
        """
        wav_paths    : iterable of .wav paths (stereo mic+EGG)
        n_clusters   : override k (default: current cluster calculator k)
        n_harmonics  : override n_harm (same)
        progress_cb  : callable(step:int, total:int, msg:str) for UI updates
        Returns the trained (k, 3·n_harm) centroid matrix.
        """
        from sklearn.cluster import KMeans
        from metrics import _compute_cycle_dft

        wavs = list(wav_paths)
        if not wavs:
            raise ValueError("train_cluster_centroids: empty wav list")

        k     = int(n_clusters  if n_clusters  is not None else self.cluster_calculator.n_clusters)
        nharm = int(n_harmonics if n_harmonics is not None else self.cluster_calculator.n_harmonics)

        feats_all = []
        for i, path in enumerate(wavs, 1):
            if progress_cb:
                progress_cb(i, len(wavs), f"loading {path}")
            voice, egg, sr, _ = self.load_audio(path)
            egg_p = self.preprocess_egg(egg)
            trig  = self.phase_portrait_cycle_detection(egg_p)
            idx   = np.where(trig > 0.5)[0]
            if len(idx) < 2:
                logger.warning("  %s: no cycles detected, skipping", path)
                continue
            amps, phases = _compute_cycle_dft(egg_p, idx, nharm)
            # Same 3n feature recipe as ClusterCalculator
            fund = amps[:, 0]
            valid = fund > 1e-12
            if valid.sum() == 0:
                continue
            a = amps[valid]; ph = phases[valid]
            eps = 1e-15
            damp_db = 20.0 * np.log10(
                np.maximum(a[:, 1:], eps) / np.maximum(a[:, :1], eps))
            dphi    = ph[:, 1:] - ph[:, :1]
            feats   = np.concatenate([damp_db, np.cos(dphi), np.sin(dphi)], axis=1)
            feats_all.append(feats)
            logger.info("  %s: %d valid cycles contributed", path, feats.shape[0])

        if not feats_all:
            raise RuntimeError("train_cluster_centroids: no valid cycles across inputs")

        X = np.vstack(feats_all)
        logger.info("Fitting K-means on %d pooled cycles (k=%d, dim=%d)...",
                    X.shape[0], k, X.shape[1])
        if progress_cb:
            progress_cb(len(wavs), len(wavs), f"fitting K-means on {X.shape[0]} cycles")
        km = KMeans(n_clusters=k, n_init=5, random_state=random_state)
        km.fit(X)
        centroids = km.cluster_centers_.copy()

        # Store on the analyzer so save_centroids() can dump them straight out
        self.cluster_calculator.centroids_   = centroids
        self.cluster_calculator.n_clusters   = k
        self.cluster_calculator.n_harmonics  = nharm
        logger.info("Joint centroids trained: k=%d  dim=%d  inertia=%.3g",
                    centroids.shape[0], centroids.shape[1], km.inertia_)
        return centroids

    # ------------------------------------------------------------------
    # Audio I/O
    # ------------------------------------------------------------------
    def load_audio(self, file_path: str) -> Tuple[np.ndarray, np.ndarray, int, float]:
        logger.info("Loading audio file: %s", file_path)
        signal, sr = sf.read(file_path)
        if signal.ndim == 2:
            voice, egg = signal[:, 0], signal[:, 1]
        else:
            voice, egg = signal, None
        duration = len(signal) / sr
        logger.info("Duration %.1fs  SR=%dHz  Samples=%d", duration, sr, len(signal))
        return voice, egg, sr, duration

    # ------------------------------------------------------------------
    # Pre-processing
    # ------------------------------------------------------------------
    def preprocess_voice(self, voice_signal: np.ndarray) -> np.ndarray:
        nyquist = self.config.sample_rate / 2
        b, a = butter(2, 30 / nyquist, btype='high')
        return filtfilt(b, a, voice_signal)

    def preprocess_egg(self, egg_signal: np.ndarray) -> np.ndarray:
        """Condition EGG signal matching SC VRPSDIO:
        1. FIR bandpass (type=3: HP~86Hz, LP~10kHz, matching PV_MagMul + bpBuffer)
        2. PV_Compander (downward expander below noise threshold)
        """
        # Step 1: FIR bandpass (zero-phase via fftconvolve 'same')
        egg = fftconvolve(egg_signal.astype(np.float64), _FIR_BP_IMPULSE, mode='same')

        # Step 2: PV_Compander — compute SC amplitude threshold from dBFS setting
        # SC: dBthresh.linexp(-120, -50, 0.007, 7)
        db = self.config.egg_compander_threshold_db
        thresh = 0.007 * (7.0 / 0.007) ** ((db - (-120.0)) / (-50.0 - (-120.0)))
        fft_sz = self.config.egg_compander_fft_size
        egg = _pv_compander(egg, thresh,
                            slope_below=self.config.egg_compander_slope_below,
                            fft_size=fft_sz, hop=fft_sz // 2)
        return egg

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------
    def phase_portrait_cycle_detection(self, egg_signal: np.ndarray) -> np.ndarray:
        """Phase Portrait method — matches current SC namePhasePortrait SynthDef.

        SC algorithm (VRPSDCSDFT.sc):
          integr = Integrator.ar(in, 0.999)   # leaky integrator
          inLP   = HPF.ar(integr, 50)          # remove integrated DC
          phi    = atan2(in, inLP)             # analytic phase
          z      = Dolansky.ar(phi, tau, 0.99) # cycle trigger from phase
        """
        logger.info("Using Phase Portrait method for cycle detection...")
        cfg = self.config
        egg = egg_signal.astype(np.float64)

        # Leaky integrator: y[n] = coeff*y[n-1] + x[n]
        integr = lfilter([1.0], [1.0, -cfg.phase_integr_coeff], egg)

        # HPF at 50 Hz to suppress integrated DC drift
        nyq = cfg.sample_rate / 2
        b, a = butter(2, cfg.phase_hpf_hz / nyq, btype='high')
        inLP = lfilter(b, a, integr)

        # Analytic phase
        phi = np.arctan2(egg, inLP)

        # Dolansky on phase signal
        cycle_triggers = self.dolansky_algorithm(phi, cfg.phase_tau, cfg.phase_dolansky_coeff)
        cycle_triggers = np.concatenate([cycle_triggers, [0]])
        return self.filter_cycles(cycle_triggers)

    def dolansky_algorithm(self, signal: np.ndarray,
                           decay: float, coeff: float) -> np.ndarray:
        peak_plus  = self.peak_follower(np.maximum(signal,  0), decay)
        peak_minus = self.peak_follower(np.maximum(-signal, 0), decay)
        pp_fos = self.fos_filter(peak_plus,  coeff)
        pm_fos = self.fos_filter(peak_minus, coeff)
        return self.set_reset_ff(pp_fos, pm_fos)

    def peak_follower(self, signal: np.ndarray, decay: float) -> np.ndarray:
        """O(N) — numba-compiled when available, pure Python otherwise."""
        return _peak_follower_inner(signal.astype(np.float64), decay)

    def fos_filter(self, signal: np.ndarray, coeff: float) -> np.ndarray:
        """First-order IIR: y[n] = coeff*(y[n-1] + x[n] - x[n-1]).
        Equivalent to scipy.signal.lfilter([c,-c],[1,-c], x).
        O(N) at C speed via lfilter — no Python loop.
        """
        return lfilter([coeff, -coeff], [1.0, -coeff], signal)

    def set_reset_ff(self, set_signal: np.ndarray,
                     reset_signal: np.ndarray) -> np.ndarray:
        """O(N) — numba-compiled when available, pure Python otherwise."""
        return _set_reset_ff_inner(
            set_signal.astype(np.float64),
            reset_signal.astype(np.float64)
        )

    def filter_cycles(self, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("  Filtering cycles...")
        trigger_indices = np.where(cycle_triggers > 0.5)[0]
        if len(trigger_indices) < 2:
            return cycle_triggers

        periods = np.diff(trigger_indices)
        valid_mask = (periods >= self.config.min_samples) & \
                     (periods <= self.config.max_period_samples)

        # First trigger always kept; keep i+1 when period[i] is valid
        keep = np.concatenate([[trigger_indices[0]],
                                trigger_indices[1:][valid_mask]])

        filtered = np.zeros_like(cycle_triggers)
        filtered[keep] = 1
        logger.info("  Cycles: %d → %d  (%.1f%%)",
                         len(trigger_indices), len(keep),
                         100 * len(keep) / len(trigger_indices))
        return filtered

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def calculate_all_metrics(self, voice_signal, egg_signal,
                               cycle_triggers,
                               progress_cb=None,
                               _base_step: int = 0,
                               _total_steps: int = 0) -> Dict[str, np.ndarray]:
        logger.info("Calculating all metrics...")

        def _step(offset: int, name: str):
            if progress_cb is not None and _total_steps > 0:
                progress_cb(_base_step + offset, _total_steps, name)

        # Precompute per-cycle EGG DFT once and share it across HRF, Entropy,
        # and ClusterCalculator — saves two passes over the Python-loop DFT.
        _step(1, "EGG DFT (每周期)")
        _dft_n = max(self.config.n_harmonics,
                     self.cluster_calculator.n_harmonics,
                     self.config.sampen_amplitude_harmonics,
                     self.config.sampen_phase_harmonics)
        _idx   = np.where(cycle_triggers > 0.5)[0]
        _dft   = None
        if len(_idx) >= 2:
            from metrics import _compute_cycle_dft
            _dft = _compute_cycle_dft(egg_signal, _idx, _dft_n)

        _step(2, "SPL / Clarity / CPP")
        spl_values                           = self.spl_calculator.calculate(voice_signal, cycle_triggers)
        midi_values, clarity_values          = self.clarity_calculator.calculate(voice_signal, cycle_triggers)
        cpp_values                           = self.cpp_calculator.calculate(voice_signal, cycle_triggers)

        _step(3, "SpecBal / Crest")
        specbal_values                       = self.specbal_calculator.calculate(voice_signal, cycle_triggers)
        crest_values                         = self.crest_calculator.calculate(voice_signal, cycle_triggers)

        _step(4, "Qcontact / Entropy / HRFegg")
        qcontact_values, deggmax_v, ic_v     = self.qcontact_calculator.calculate(egg_signal, cycle_triggers)
        entropy_values                       = self.entropy_calculator.calculate(egg_signal, cycle_triggers, dft=_dft)
        hrf_values                           = self.hrf_calculator.calculate(egg_signal, cycle_triggers, dft=_dft)

        _step(5, "EGG 波形聚类")
        cluster_values                       = self.cluster_calculator.calculate(egg_signal, cycle_triggers, dft=_dft)

        _step(6, "Jitter / Shimmer")
        perturb_values                       = self.perturb_calculator.calculate(voice_signal, cycle_triggers)
        _step(7, "HNR")
        hnr_values                           = self.hnr_calculator.calculate(voice_signal, cycle_triggers)
        _step(8, "Vibrato")
        vib_rate, vib_extent                 = self.vibrato_calculator.calculate(midi_values, _idx)
        _step(9, "Formants + Singer's Formant")
        formant_values                       = self.formant_calculator.calculate(voice_signal, cycle_triggers)
        _step(10, "H1-H2 / H1-H3")
        harmdiff_values                      = self.harmdiff_calculator.calculate(voice_signal, cycle_triggers)
        _step(11, "OQ / SPQ / CIQ")
        oq_values                            = self.oq_calculator.calculate(egg_signal, cycle_triggers)

        base = {
            'midi':     midi_values,
            'spl':      spl_values,
            'clarity':  clarity_values,
            'cpp':      cpp_values,
            'specbal':  specbal_values,
            'crest':    crest_values,
            'qcontact': qcontact_values,
            'deggmax':  deggmax_v,
            'icontact': ic_v,
            'entropy':  entropy_values,
            'hrf':      hrf_values,
            'cluster':  cluster_values,
            # P1
            'jitter':        perturb_values['jitter_local'],
            'jitter_rap':    perturb_values['jitter_rap'],
            'jitter_ppq5':   perturb_values['jitter_ppq5'],
            'shimmer':       perturb_values['shimmer_local'],
            'shimmer_db':    perturb_values['shimmer_db'],
            'shimmer_apq11': perturb_values['shimmer_apq11'],
            'hnr':           hnr_values,
            'vibrato_rate':   vib_rate,
            'vibrato_extent': vib_extent,
            'f1':  formant_values['f1'],
            'f2':  formant_values['f2'],
            'f3':  formant_values['f3'],
            'sfe': formant_values['sfe'],
            'h1h2': harmdiff_values['h1h2'],
            'h1h3': harmdiff_values['h1h3'],
            'oq':  oq_values['oq'],
            'spq': oq_values['spq'],
            'ciq': oq_values['ciq'],
        }
        # Phonation-type cluster uses the already-computed quality metrics
        # as features — must run AFTER them.
        _step(12, "Phonation cluster (cPhon)")
        base['phon'] = self.phon_calculator.calculate(base)
        return base

    def apply_clarity_filtering(self, metrics: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        logger.info("Applying Clarity threshold (%.2f)...", self.config.clarity_threshold)
        clarity_mask   = metrics['clarity'] >= self.config.clarity_threshold
        total          = len(metrics['midi'])
        kept           = int(np.sum(clarity_mask))
        logger.info("  %d / %d points pass clarity (%.1f%%)",
                         kept, total, 100 * kept / total if total else 0)

        out = {key: vals[clarity_mask] for key, vals in metrics.items()}
        return out

    # ------------------------------------------------------------------
    # Cluster aggregation helper
    # ------------------------------------------------------------------
    @staticmethod
    def _aggregate_cluster_labels(df: pd.DataFrame,
                                   label_col: str, n: int,
                                   prefix: str, max_col: str) -> pd.DataFrame:
        """
        For each (MIDI, dB) cell, compute:
          - `{prefix}k` (k=1..n) = percentage of cycles in that cell with label == k
          - `max_col` = k with the highest percentage (0 if cell is empty)
        Rows with label==0 are treated as "invalid/unclustered" and excluded
        from the denominator.
        """
        # Skip degenerate case: all-zero labels
        if (df[label_col] == 0).all():
            keys = df[['MIDI', 'dB']].drop_duplicates().reset_index(drop=True)
            for k in range(1, n + 1):
                keys[f"{prefix}{k}"] = 0.0
            keys[max_col] = 0
            return keys

        valid = df[df[label_col] > 0].copy()
        pivot = (valid.groupby(['MIDI', 'dB', label_col])
                      .size()
                      .unstack(label_col, fill_value=0))
        # Ensure every cluster column 1..n is present
        for k in range(1, n + 1):
            if k not in pivot.columns:
                pivot[k] = 0
        pivot = pivot[[k for k in range(1, n + 1)]]   # stable column order
        totals = pivot.sum(axis=1).replace(0, np.nan)
        pct = (100.0 * pivot.div(totals, axis=0)).fillna(0.0)
        pct.columns = [f"{prefix}{k}" for k in range(1, n + 1)]

        # maxCluster = argmax + 1 (labels are 1..n); 0 when no valid cycles
        argmax = pct.values.argmax(axis=1) + 1
        pct[max_col] = argmax

        return pct.reset_index()

    # ------------------------------------------------------------------
    # CSV output
    # ------------------------------------------------------------------
    def output_vrp_csv(self, metrics: Dict[str, np.ndarray],
                        return_df: bool = False,
                        plot_mode: str = "per-metric",
                        export_plots: Optional[bool] = None):
        """
        plot_mode:
          "none"       — skip PNG export (fastest; GUI embeds in-memory)
          "per-metric" — one PNG per active metric (default; CLI-compatible)
          "combined"   — single overview PNG with a grid of all metrics

        `export_plots` is a legacy bool kwarg. False ⇒ "none", True ⇒ keep
        current plot_mode; kept so older callers still work.
        """
        if export_plots is False:
            plot_mode = "none"
        logger.info("Outputting VRP CSV...")
        spl_corr = metrics['spl'] + self.config.spl_correction_db

        # Cluster labels may be shorter than metric arrays (e.g. trailing cycles
        # dropped during feature extraction); align to the shortest array.
        base_n = len(metrics['midi'])
        cluster = metrics.get('cluster', np.zeros(base_n, dtype=np.int32))
        phon    = metrics.get('phon',    np.zeros(base_n, dtype=np.int32))
        if len(cluster) < base_n:
            cluster = np.concatenate([cluster, np.zeros(base_n - len(cluster),
                                                         dtype=cluster.dtype)])
        if len(phon) < base_n:
            phon = np.concatenate([phon, np.zeros(base_n - len(phon),
                                                   dtype=phon.dtype)])

        # P1 per-cycle scalars: align to base_n same as cluster arrays
        def _pad(arr, n, dtype=np.float64):
            if arr is None:
                return np.zeros(n, dtype=dtype)
            arr = np.asarray(arr, dtype=dtype)
            if len(arr) < n:
                return np.concatenate([arr, np.zeros(n - len(arr), dtype=dtype)])
            return arr[:n]

        df = pd.DataFrame({
            'MIDI':     np.round(np.where(metrics['midi'] > 0, metrics['midi'], 0)).astype(int),
            'dB':       np.round(np.where(spl_corr > 0, spl_corr, 0)).astype(int),
            'Total':    1,
            'Clarity':  metrics['clarity'],
            'CPP':      metrics['cpp'],
            'SpecBal':  metrics['specbal'],
            'Crest':    metrics['crest'],
            'Entropy':  metrics['entropy'],
            'Qcontact': metrics['qcontact'],
            'dEGGmax':  metrics['deggmax'],
            'Icontact': metrics['icontact'],
            'HRFegg':   metrics['hrf'],
            'Jitter':        _pad(metrics.get('jitter'),        base_n),
            'JitterRAP':     _pad(metrics.get('jitter_rap'),    base_n),
            'JitterPPQ5':    _pad(metrics.get('jitter_ppq5'),   base_n),
            'Shimmer':       _pad(metrics.get('shimmer'),       base_n),
            'ShimmerDB':     _pad(metrics.get('shimmer_db'),    base_n),
            'ShimmerAPQ11':  _pad(metrics.get('shimmer_apq11'), base_n),
            'HNR':           _pad(metrics.get('hnr'),           base_n),
            'VibratoRate':   _pad(metrics.get('vibrato_rate'),   base_n),
            'VibratoExtent': _pad(metrics.get('vibrato_extent'), base_n),
            'F1':            _pad(metrics.get('f1'),  base_n),
            'F2':            _pad(metrics.get('f2'),  base_n),
            'F3':            _pad(metrics.get('f3'),  base_n),
            'SingersFormant': _pad(metrics.get('sfe'), base_n),
            'H1H2':           _pad(metrics.get('h1h2'), base_n),
            'H1H3':           _pad(metrics.get('h1h3'), base_n),
            'OQ':             _pad(metrics.get('oq'),  base_n),
            'SPQ':            _pad(metrics.get('spq'), base_n),
            'CIQ':            _pad(metrics.get('ciq'), base_n),
            '_cluster': cluster.astype(int),
            '_phon':    phon.astype(int),
        })
        logger.info("  Raw points: %d", len(df))

        range_mask = (
            (df['MIDI'] >= self.config.n_min_midi) & (df['MIDI'] <= self.config.n_max_midi) &
            (df['dB']   >= self.config.n_min_spl)  & (df['dB']   <= self.config.n_max_spl)
        )
        df = df[range_mask].copy()
        logger.info("  After range filter: %d", len(df))

        # Per-cell aggregation for scalar metrics
        grouped = df.groupby(['MIDI', 'dB']).agg({
            'Clarity': 'max',   # SC VRPControllerPlots: max(clarity, clarityMap.at(...) ? 0)
            'CPP': 'mean', 'SpecBal': 'mean',
            'Crest': 'mean', 'Entropy': 'mean', 'Qcontact': 'mean',
            'dEGGmax': 'mean', 'Icontact': 'mean', 'HRFegg': 'mean',
            'Jitter': 'mean', 'JitterRAP': 'mean', 'JitterPPQ5': 'mean',
            'Shimmer': 'mean', 'ShimmerDB': 'mean', 'ShimmerAPQ11': 'mean',
            'HNR': 'mean',
            'VibratoRate': 'mean', 'VibratoExtent': 'mean',
            'F1': 'mean', 'F2': 'mean', 'F3': 'mean',
            'SingersFormant': 'mean',
            'H1H2': 'mean', 'H1H3': 'mean',
            'OQ': 'mean', 'SPQ': 'mean', 'CIQ': 'mean',
            'Total': 'sum',
        }).reset_index()

        # Per-cell cluster aggregation: maxCluster = dominant label; Cluster k = %
        cluster_cols = self._aggregate_cluster_labels(
            df, label_col='_cluster', n=5, prefix='Cluster ', max_col='maxCluster')
        phon_cols = self._aggregate_cluster_labels(
            df, label_col='_phon',    n=5, prefix='cPhon ',   max_col='maxCPhon')

        grouped = grouped.merge(cluster_cols, on=['MIDI', 'dB'], how='left')
        grouped = grouped.merge(phon_cols,    on=['MIDI', 'dB'], how='left')

        standard_columns = [
            'MIDI', 'dB', 'Total', 'Clarity', 'Crest', 'SpecBal', 'CPP', 'Entropy',
            'dEGGmax', 'Qcontact', 'Icontact', 'HRFegg',
            # P3 (EGG timing)
            'OQ', 'SPQ', 'CIQ',
            # P1
            'Jitter', 'JitterRAP', 'JitterPPQ5',
            'Shimmer', 'ShimmerDB', 'ShimmerAPQ11', 'HNR',
            # P2 (singing-specific)
            'VibratoRate', 'VibratoExtent',
            'F1', 'F2', 'F3', 'SingersFormant',
            'H1H2', 'H1H3',
            # P0 cluster
            'maxCluster',
            'Cluster 1', 'Cluster 2', 'Cluster 3', 'Cluster 4', 'Cluster 5',
            'maxCPhon', 'cPhon 1', 'cPhon 2', 'cPhon 3', 'cPhon 4', 'cPhon 5',
        ]
        for col in standard_columns:
            if col not in grouped.columns:
                grouped[col] = 0
            grouped[col] = grouped[col].fillna(0)
        grouped = grouped[standard_columns]

        os.makedirs(self.config.output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = f"{self.config.output_dir}/complete_vrp_results_{ts}_VRP.csv"
        grouped.to_csv(out_file, index=False, sep=';')

        logger.info("=== VRP Statistics ===")
        logger.info("Unique (MIDI,dB) pairs: %d  Total cycles: %d",
                         len(grouped), grouped['Total'].sum())
        logger.info("MIDI %.1f  SPL %.1f dB  Clarity %.3f",
                         grouped['MIDI'].mean(), grouped['dB'].mean(),
                         grouped['Clarity'].mean())
        logger.info("Saved: %s", out_file)

        # --- Generate VRP map images ---
        # 22 PNGs at dpi=150 via savefig cost ~0.4s each → dominates wall time.
        # Caller picks the trade-off: none / per-metric / combined overview.
        if plot_mode == "none":
            logger.info("Skipping PNG export (plot_mode=none)")
        else:
            plot_dir = os.path.join(self.config.output_dir, "plots")
            ts_base  = os.path.splitext(os.path.basename(out_file))[0]
            if plot_mode == "combined":
                saved_path = plot_vrp_combined(grouped, ts_base, plot_dir)
                if saved_path:
                    logger.info("Combined overview saved: %s", saved_path)
            else:   # "per-metric"
                saved = plot_vrp_dataframe(grouped, ts_base, plot_dir)
                if saved:
                    logger.info("Plots saved to: %s  (%d images)",
                                plot_dir, len(saved))

        if return_df:
            return out_file, grouped
        return out_file

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    # Total pipeline stages reported via progress_cb. Pre + 12 metric
    # sub-steps + filter + CSV (+ optional plot export). Total is 16 whether
    # or not plot_mode writes PNGs — plot export is reported as step 16.
    TOTAL_STAGES = 16

    def analyze_and_output_vrp(self, file_path: Optional[str] = None,
                                return_df: bool = False,
                                plot_mode: str = "per-metric",
                                export_plots: Optional[bool] = None,
                                progress_cb=None):
        """
        progress_cb(step:int, total:int, label:str) — called at each
        pipeline stage. step is 1-based, total == TOTAL_STAGES.
        """
        logger.info("=" * 60)
        logger.info("VoiceMap Complete Analysis")
        logger.info("=" * 60)

        total = self.TOTAL_STAGES

        def _cb(step, label):
            if progress_cb is not None:
                progress_cb(step, total, label)

        audio_file = file_path or self.config.audio_file

        t0 = time.perf_counter()
        _cb(1, "加载音频")
        voice, egg, sr, duration = self.load_audio(audio_file)

        _cb(2, "预处理 (HPF / 带通滤波)")
        voice_p = self.preprocess_voice(voice)
        egg_p   = self.preprocess_egg(egg)

        _cb(3, "周期检测 (phase-portrait)")
        logger.info("Cycle detection...")
        cycle_triggers = self.phase_portrait_cycle_detection(egg_p)
        cycle_count = int(np.sum(cycle_triggers > 0.5))
        logger.info("Detected cycles: %d", cycle_count)

        # calculate_all_metrics reports 12 sub-stages starting at base_step=3
        metrics = self.calculate_all_metrics(
            voice_p, egg_p, cycle_triggers,
            progress_cb=progress_cb,
            _base_step=3, _total_steps=total)
        # calculate_all_metrics ended at step 15 (= 3 + 12)
        filtered_metrics = self.apply_clarity_filtering(metrics)

        logger.info("Valid data points: %d", len(filtered_metrics['midi']))
        _cb(16, "写 CSV" + (" + PNG" if plot_mode != "none" else ""))
        csv_result = self.output_vrp_csv(filtered_metrics,
                                          return_df=return_df,
                                          plot_mode=plot_mode,
                                          export_plots=export_plots)
        if return_df:
            out_file, grouped_df = csv_result
        else:
            out_file = csv_result

        logger.info("Total wall time: %.2fs  (audio: %.1fs  ratio: %.1fx)",
                         time.perf_counter() - t0, duration,
                         duration / max(time.perf_counter() - t0, 1e-9))
        if return_df:
            return filtered_metrics, out_file, grouped_df
        return filtered_metrics, out_file


def main():
    setup_logger("voicemap", level=logging.INFO)
    logger = get_logger(__name__)
    logger.info("VoiceMap Analysis — %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    analyzer = VoiceMapAnalyzer()
    data, out = analyzer.analyze_and_output_vrp()
    logger.info("Done. Output: %s", out)


if __name__ == "__main__":
    main()
