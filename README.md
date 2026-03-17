# Voice Mapping

Python implementation of Voice Range Profile (VRP) analysis for voice mapping research.

## Quick Start

```bash
pip install -r requirements.txt
python main.py path/to/audio.wav
```

The audio file must be a stereo WAV: **channel 1 = voice microphone, channel 2 = EGG**.

## Usage

```python
from analyzer import VoiceMapAnalyzer
from config import VoiceMapConfig

analyzer = VoiceMapAnalyzer()
data, output_file = analyzer.analyze_and_output_vrp("audio.wav")

# Custom settings
config = VoiceMapConfig(clarity_threshold=0.96, output_dir="results")
analyzer = VoiceMapAnalyzer(config)
```

## Analysis Pipeline

### 1. Audio Loading
- Stereo WAV → voice (ch 1) + EGG (ch 2) via `soundfile`

### 2. Signal Preprocessing
- **Voice**: 2nd-order Butterworth HPF at 30 Hz (`filtfilt`)
- **EGG**: FIR bandpass + PV_Compander downward expander

### 3. Cycle Detection — Phase Portrait method
1. Leaky integrator: `y[n] = 0.999·y[n-1] + x[n]`
2. HPF at 50 Hz on integrator output
3. Phase: `atan2(EGG, HPF_integral)`
4. Dolansky algorithm → cycle triggers

### 4. Metric Calculation (per cycle)

| Metric | Method |
|--------|--------|
| MIDI, Clarity | McLeod-Wyvill NSDF autocorrelation |
| SPL | Sliding-window RMS → dBFS |
| CPP | 1024-pt real cepstrum, peak prominence |
| SpecBal | Single-pass energy ratio below/above 1500 Hz |
| Crest | Peak-to-RMS ratio |
| Qcontact, dEGGmax, Icontact | EGG contact quotient metrics |
| Entropy (CSE) | Sample Entropy on EGG amplitude/phase |
| HRFegg | Per-cycle EGG DFT harmonic richness |

### 5. Clarity Filtering
Cycles with clarity < 0.96 are discarded.

### 6. VRP Aggregation & Output
- MIDI and dB rounded to integers
- Grouped by (MIDI, dB) cell
- **Clarity**: MAX per cell
- Other metrics: mean per cell
- Range: MIDI 30–96, SPL 40–120 dB
- Output: semicolon-delimited CSV to `result/`

## Output Format

`result/complete_vrp_results_YYYYMMDD_HHMMSS_VRP.csv` — 25-column VRP format.

## Requirements

- Python 3.8+
- numpy, scipy, pandas, soundfile
- numba (optional — accelerates cycle detection; falls back to pure Python automatically)
