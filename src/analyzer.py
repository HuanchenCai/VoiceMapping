#!/usr/bin/env python3
"""
VoiceMap Voice Range Profile Analyzer
Complete implementation of VoiceMap algorithms for VRP analysis
"""

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import butter, filtfilt, lfilter
import os
from datetime import datetime
from typing import Dict, Optional, Tuple
import logging

from config import VoiceMapConfig, DEFAULT_CONFIG
from logger import setup_logger, get_logger
from metrics import (
    SPLCalculator, ClarityCalculator, CPPCalculator, SpecBalCalculator,
    CrestCalculator, QcontactCalculator, EntropyCalculator, HRFCalculator
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
        self.logger = get_logger(__name__)

        self.spl_calculator      = SPLCalculator(self.config)
        self.clarity_calculator  = ClarityCalculator(self.config)
        self.cpp_calculator      = CPPCalculator(self.config)
        self.specbal_calculator  = SpecBalCalculator(self.config)
        self.crest_calculator    = CrestCalculator(self.config)
        self.qcontact_calculator = QcontactCalculator(self.config)
        self.entropy_calculator  = EntropyCalculator(self.config)
        self.hrf_calculator      = HRFCalculator(self.config)

        self.logger.info("VoiceMap analyzer initialized (numba=%s)", _NUMBA)

    # ------------------------------------------------------------------
    # Audio I/O
    # ------------------------------------------------------------------
    def load_audio(self, file_path: str) -> Tuple[np.ndarray, np.ndarray, int, float]:
        self.logger.info("Loading audio file: %s", file_path)
        signal, sr = sf.read(file_path)
        if signal.ndim == 2:
            voice, egg = signal[:, 0], signal[:, 1]
        else:
            voice, egg = signal, None
        duration = len(signal) / sr
        self.logger.info("Duration %.1fs  SR=%dHz  Samples=%d", duration, sr, len(signal))
        return voice, egg, sr, duration

    # ------------------------------------------------------------------
    # Pre-processing
    # ------------------------------------------------------------------
    def preprocess_voice(self, voice_signal: np.ndarray) -> np.ndarray:
        nyquist = self.config.sample_rate / 2
        b, a = butter(2, 30 / nyquist, btype='high')
        return filtfilt(b, a, voice_signal)

    def preprocess_egg(self, egg_signal: np.ndarray) -> np.ndarray:
        nyquist = self.config.sample_rate / 2
        b, a = butter(2, 100 / nyquist,   btype='high')
        egg = filtfilt(b, a, egg_signal)
        b, a = butter(2, 10000 / nyquist, btype='low')
        return filtfilt(b, a, egg)

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
        self.logger.info("Using Phase Portrait method for cycle detection...")
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

    def peak_follower_cycle_detection(self, egg_signal: np.ndarray) -> np.ndarray:
        """Deprecated PeakFollower method — kept for reference only.
        SC has this commented out in favour of Phase Portrait.
        """
        self.logger.info("Using PeakFollower method for cycle detection (deprecated)...")
        degg = np.diff(egg_signal).astype(np.float64)
        cycle_triggers = self.dolansky_algorithm(
            degg, self.config.dolansky_decay, self.config.dolansky_coeff
        )
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
        self.logger.info("  Filtering cycles...")
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
        self.logger.info("  Cycles: %d → %d  (%.1f%%)",
                         len(trigger_indices), len(keep),
                         100 * len(keep) / len(trigger_indices))
        return filtered

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def calculate_all_metrics(self, voice_signal, egg_signal,
                               cycle_triggers) -> Dict[str, np.ndarray]:
        self.logger.info("Calculating all metrics...")
        spl_values                           = self.spl_calculator.calculate(voice_signal, cycle_triggers)
        midi_values, clarity_values          = self.clarity_calculator.calculate(voice_signal, cycle_triggers)
        cpp_values                           = self.cpp_calculator.calculate(voice_signal, cycle_triggers)
        specbal_values                       = self.specbal_calculator.calculate(voice_signal, cycle_triggers)
        crest_values                         = self.crest_calculator.calculate(voice_signal, cycle_triggers)
        qcontact_values, deggmax_v, ic_v     = self.qcontact_calculator.calculate(egg_signal, cycle_triggers)
        entropy_values                       = self.entropy_calculator.calculate(egg_signal, cycle_triggers)
        hrf_values                           = self.hrf_calculator.calculate(egg_signal, cycle_triggers)
        return {
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
        }

    def apply_clarity_filtering(self, metrics: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        self.logger.info("Applying Clarity threshold (%.2f)...", self.config.clarity_threshold)
        clarity_mask   = metrics['clarity'] >= self.config.clarity_threshold
        total          = len(metrics['midi'])
        kept           = int(np.sum(clarity_mask))
        self.logger.info("  %d / %d points pass clarity (%.1f%%)",
                         kept, total, 100 * kept / total if total else 0)

        out = {}
        for key, vals in metrics.items():
            if key == 'midi':
                valid = ~np.isnan(vals)
                out[key] = vals[valid][clarity_mask[valid]]
            else:
                n = min(len(clarity_mask), len(vals))
                out[key] = vals[:n][clarity_mask[:n]]
        return out

    # ------------------------------------------------------------------
    # CSV output
    # ------------------------------------------------------------------
    def output_vrp_csv(self, metrics: Dict[str, np.ndarray],
                       cycle_count: int, duration: float) -> str:
        self.logger.info("Outputting VRP CSV...")
        spl_corr = metrics['spl'] + self.config.spl_correction_db
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
        })
        self.logger.info("  Raw points: %d", len(df))

        range_mask = (
            (df['MIDI'] >= self.config.n_min_midi) & (df['MIDI'] <= self.config.n_max_midi) &
            (df['dB']   >= self.config.n_min_spl)  & (df['dB']   <= self.config.n_max_spl)
        )
        df = df[range_mask].copy()
        self.logger.info("  After range filter: %d", len(df))

        grouped = df.groupby(['MIDI', 'dB']).agg({
            'Clarity': 'mean', 'CPP': 'mean', 'SpecBal': 'mean',
            'Crest': 'mean', 'Entropy': 'mean', 'Qcontact': 'mean',
            'dEGGmax': 'mean', 'Icontact': 'mean', 'HRFegg': 'mean',
            'Total': 'sum',
        }).reset_index()

        standard_columns = [
            'MIDI', 'dB', 'Total', 'Clarity', 'Crest', 'SpecBal', 'CPP', 'Entropy',
            'dEGGmax', 'Qcontact', 'Icontact', 'HRFegg', 'maxCluster',
            'Cluster 1', 'Cluster 2', 'Cluster 3', 'Cluster 4', 'Cluster 5',
            'maxCPhon', 'cPhon 1', 'cPhon 2', 'cPhon 3', 'cPhon 4', 'cPhon 5',
        ]
        for col in standard_columns:
            if col not in grouped.columns:
                grouped[col] = 0
        grouped = grouped[standard_columns]

        os.makedirs(self.config.output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = f"{self.config.output_dir}/complete_vrp_results_{ts}_VRP.csv"
        grouped.to_csv(out_file, index=False, sep=';')

        self.logger.info("=== VRP Statistics ===")
        self.logger.info("Unique (MIDI,dB) pairs: %d  Total cycles: %d",
                         len(grouped), grouped['Total'].sum())
        self.logger.info("MIDI %.1f  SPL %.1f dB  Clarity %.3f",
                         grouped['MIDI'].mean(), grouped['dB'].mean(),
                         grouped['Clarity'].mean())
        self.logger.info("Saved: %s", out_file)
        return out_file

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    def analyze_and_output_vrp(self, file_path: Optional[str] = None
                                ) -> Tuple[Dict[str, np.ndarray], str]:
        import time
        self.logger.info("=" * 60)
        self.logger.info("VoiceMap Complete Analysis")
        self.logger.info("=" * 60)

        audio_file = file_path or self.config.audio_file

        t0 = time.perf_counter()
        voice, egg, sr, duration = self.load_audio(audio_file)

        voice_p = self.preprocess_voice(voice)
        egg_p   = self.preprocess_egg(egg)

        self.logger.info("Cycle detection...")
        cycle_triggers = self.phase_portrait_cycle_detection(egg_p)
        cycle_count = int(np.sum(cycle_triggers > 0.5))
        self.logger.info("Detected cycles: %d", cycle_count)

        metrics          = self.calculate_all_metrics(voice_p, egg_p, cycle_triggers)
        filtered_metrics = self.apply_clarity_filtering(metrics)

        self.logger.info("Valid data points: %d", len(filtered_metrics['midi']))
        out_file = self.output_vrp_csv(filtered_metrics, cycle_count, duration)

        self.logger.info("Total wall time: %.2fs  (audio: %.1fs  ratio: %.1fx)",
                         time.perf_counter() - t0, duration,
                         duration / max(time.perf_counter() - t0, 1e-9))
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
