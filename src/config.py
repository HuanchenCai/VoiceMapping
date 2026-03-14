#!/usr/bin/env python3
"""
VoiceMap Configuration Module
Centralized configuration for all VoiceMap analysis parameters
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class VoiceMapConfig:
    """Configuration class for VoiceMap analysis parameters"""
    
    # Audio parameters
    sample_rate: int = 44100
    
    # Cycle detection parameters
    min_samples: int = 20
    min_frequency: int = 50
    max_period_samples: Optional[int] = None
    
    # Phase Portrait cycle detection (current SC method)
    # Integrator: y[n] = phase_integr_coeff * y[n-1] + x[n]
    # HPF on integrator output at phase_hpf_hz Hz
    # Dolansky on atan2(EGG, HPF_integral): decay=phase_tau, coeff=phase_dolansky_coeff
    phase_integr_coeff: float = 0.999
    phase_hpf_hz: float = 50.0
    phase_tau: float = 0.95        # VRPSettingsCSDFT default tau
    phase_dolansky_coeff: float = 0.99

    # Legacy PeakFollower parameters (deprecated in SC, kept for reference)
    dolansky_decay: float = 0.99
    dolansky_coeff: float = 0.995

    # Clarity / pitch detection window (Tartini-style autocorrelation)
    clarity_fft_size: int = 2048
    clarity_overlap: int = 1024    # hop = fft_size - overlap
    
    # SPL sliding window parameters
    spl_window_size: Optional[int] = None  # 100ms window
    spl_hop_size: Optional[int] = None     # 10ms step
    
    # CPP parameters
    cpp_fft_size: int = 2048
    cpp_ceps_size: int = 1024
    cpp_low_bin: int = 25
    cpp_high_bin: int = 367
    cpp_dither_amp: float = 1e-6
    
    # SpecBal parameters
    specbal_cutoff_low: int = 1500
    specbal_cutoff_high: int = 2000
    specbal_rms_window: int = 50

    # EGG DFT / HRFegg parameters
    n_harmonics: int = 10              # Harmonics 1..N per cycle (MetricHRFegg default)

    # SampEn (CSE) parameters — from GUI defaults in VRPViewPlots.sc
    sampen_amplitude_window_size: int   = 10
    sampen_amplitude_harmonics: int     = 4
    sampen_amplitude_seq_length: int    = 1
    sampen_amplitude_tolerance: float   = 0.2
    sampen_phase_window_size: int       = 10
    sampen_phase_harmonics: int         = 4
    sampen_phase_seq_length: int        = 1
    sampen_phase_tolerance: float       = 0.4

    # VoiceMap standard ranges
    n_min_midi: int = 30
    n_max_midi: int = 96
    n_min_spl: int = 40
    n_max_spl: int = 120
    
    # Analysis parameters
    clarity_threshold: float = 0.96
    spl_correction_db: float = 120.0
    
    # File paths
    audio_file: str = "audio/test_Voice_EGG.wav"
    output_dir: str = "result"
    
    def __post_init__(self):
        """Initialize computed parameters"""
        if self.max_period_samples is None:
            self.max_period_samples = int(self.sample_rate / self.min_frequency)
        
        if self.spl_window_size is None:
            self.spl_window_size = int(0.1 * self.sample_rate)  # 100ms window
        
        if self.spl_hop_size is None:
            self.spl_hop_size = int(0.01 * self.sample_rate)   # 10ms step


# Default configuration instance
DEFAULT_CONFIG = VoiceMapConfig()
