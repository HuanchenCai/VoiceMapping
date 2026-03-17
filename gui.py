#!/usr/bin/env python3
"""
FonaDyn – Batch Voice Range Profile Analyzer
Cross-platform GUI (tkinter) for batch .wav → _VRP.csv analysis.
"""

import sys
import os
import threading
import queue
import logging
from pathlib import Path

# Locate src/ whether running from source or as a frozen bundle
if getattr(sys, 'frozen', False):
    _BASE = Path(sys._MEIPASS)
else:
    _BASE = Path(__file__).parent
sys.path.insert(0, str(_BASE / 'src'))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Logging bridge: worker thread → GUI queue → main-thread text widget
# ---------------------------------------------------------------------------
class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self._q = q

    def emit(self, record):
        self._q.put(('log', self.format(record)))


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------
class FonaDynApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FonaDyn – Voice Range Profile Analyzer")
        self.resizable(True, True)
        self.minsize(700, 520)

        self._files: list[str] = []
        self._running = False
        self._stop_flag = threading.Event()
        self._q: queue.Queue = queue.Queue()

        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = dict(padx=8, pady=4)

        # ── File list frame ─────────────────────────────────────────────
        frm_files = ttk.LabelFrame(self, text="Input Files  (.wav)")
        frm_files.pack(fill='both', expand=True, **pad)

        # Listbox + scrollbar
        frm_list = tk.Frame(frm_files)
        frm_list.pack(fill='both', expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(frm_list, orient='vertical')
        self._lb = tk.Listbox(frm_list, selectmode='extended',
                              yscrollcommand=sb.set, height=8,
                              activestyle='dotbox')
        sb.config(command=self._lb.yview)
        self._lb.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        # Buttons below list
        frm_btns = tk.Frame(frm_files)
        frm_btns.pack(fill='x', padx=4, pady=(0, 4))
        ttk.Button(frm_btns, text="Add Files…",
                   command=self._add_files).pack(side='left', padx=2)
        ttk.Button(frm_btns, text="Add Folder…",
                   command=self._add_folder).pack(side='left', padx=2)
        ttk.Button(frm_btns, text="Remove Selected",
                   command=self._remove_selected).pack(side='left', padx=2)
        ttk.Button(frm_btns, text="Clear All",
                   command=self._clear_files).pack(side='left', padx=2)
        self._lbl_count = ttk.Label(frm_btns, text="0 files")
        self._lbl_count.pack(side='right', padx=6)

        # ── Output directory ────────────────────────────────────────────
        frm_out = ttk.LabelFrame(self, text="Output Folder")
        frm_out.pack(fill='x', **pad)
        self._out_var = tk.StringVar(value=str(Path.home() / "FonaDyn_Results"))
        ttk.Entry(frm_out, textvariable=self._out_var).pack(
            side='left', fill='x', expand=True, padx=4, pady=4)
        ttk.Button(frm_out, text="Browse…",
                   command=self._pick_output).pack(side='right', padx=4, pady=4)

        # ── Settings row ────────────────────────────────────────────────
        frm_cfg = ttk.LabelFrame(self, text="Settings")
        frm_cfg.pack(fill='x', **pad)

        ttk.Label(frm_cfg, text="Clarity threshold:").pack(side='left', padx=(8, 2), pady=4)
        self._clarity_var = tk.DoubleVar(value=0.96)
        ttk.Spinbox(frm_cfg, from_=0.80, to=0.999, increment=0.01,
                    textvariable=self._clarity_var, width=6,
                    format="%.2f").pack(side='left', pady=4)

        ttk.Label(frm_cfg, text="   SPL correction (dB):").pack(side='left', padx=(16, 2))
        self._spl_var = tk.DoubleVar(value=120.0)
        ttk.Spinbox(frm_cfg, from_=0.0, to=200.0, increment=1.0,
                    textvariable=self._spl_var, width=6,
                    format="%.1f").pack(side='left', pady=4)

        # ── Run / Stop ──────────────────────────────────────────────────
        frm_run = tk.Frame(self)
        frm_run.pack(fill='x', **pad)

        self._btn_run = ttk.Button(frm_run, text="▶  Run Analysis",
                                   command=self._start, style='Accent.TButton')
        self._btn_run.pack(side='left', padx=2)
        self._btn_stop = ttk.Button(frm_run, text="■  Stop",
                                    command=self._stop, state='disabled')
        self._btn_stop.pack(side='left', padx=2)

        self._lbl_status = ttk.Label(frm_run, text="")
        self._lbl_status.pack(side='left', padx=12)

        # Progress bar
        self._progress = ttk.Progressbar(frm_run, orient='horizontal',
                                         mode='determinate', length=200)
        self._progress.pack(side='right', padx=8)
        self._lbl_prog = ttk.Label(frm_run, text="")
        self._lbl_prog.pack(side='right')

        # ── Log output ───────────────────────────────────────────────────
        frm_log = ttk.LabelFrame(self, text="Log")
        frm_log.pack(fill='both', expand=True, **pad)

        self._log_text = tk.Text(frm_log, height=10, wrap='word',
                                 state='disabled', font=('Courier', 9))
        sb2 = ttk.Scrollbar(frm_log, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb2.set)
        self._log_text.pack(side='left', fill='both', expand=True, padx=4, pady=4)
        sb2.pack(side='right', fill='y')

        # Color tags
        self._log_text.tag_config('ERROR',   foreground='#cc2200')
        self._log_text.tag_config('WARNING', foreground='#cc7700')
        self._log_text.tag_config('OK',      foreground='#008800')

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select audio files",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")])
        for p in paths:
            if p not in self._files:
                self._files.append(p)
                self._lb.insert('end', Path(p).name)
        self._update_count()

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select folder with .wav files")
        if not folder:
            return
        added = 0
        for p in sorted(Path(folder).rglob("*.wav")):
            s = str(p)
            if s not in self._files:
                self._files.append(s)
                self._lb.insert('end', p.name)
                added += 1
        self._log_append(f"Added {added} .wav files from folder.", 'OK')
        self._update_count()

    def _remove_selected(self):
        sel = list(self._lb.curselection())
        for idx in reversed(sel):
            self._lb.delete(idx)
            self._files.pop(idx)
        self._update_count()

    def _clear_files(self):
        self._lb.delete(0, 'end')
        self._files.clear()
        self._update_count()

    def _update_count(self):
        n = len(self._files)
        self._lbl_count.config(text=f"{n} file{'s' if n != 1 else ''}")

    def _pick_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self._out_var.set(folder)

    # ------------------------------------------------------------------
    # Run / Stop
    # ------------------------------------------------------------------
    def _start(self):
        if not self._files:
            messagebox.showwarning("No files", "Please add at least one .wav file.")
            return
        out_dir = self._out_var.get().strip()
        if not out_dir:
            messagebox.showwarning("No output folder", "Please specify an output folder.")
            return

        self._running = True
        self._stop_flag.clear()
        self._btn_run.config(state='disabled')
        self._btn_stop.config(state='normal')
        self._progress['value'] = 0
        self._progress['maximum'] = len(self._files)

        t = threading.Thread(target=self._worker,
                             args=(list(self._files), out_dir,
                                   self._clarity_var.get(),
                                   self._spl_var.get()),
                             daemon=True)
        t.start()

    def _stop(self):
        self._stop_flag.set()
        self._lbl_status.config(text="Stopping…")

    # ------------------------------------------------------------------
    # Worker (runs in background thread)
    # ------------------------------------------------------------------
    def _worker(self, files: list[str], out_dir: str,
                clarity_thresh: float, spl_correction: float):
        from analyzer import VoiceMapAnalyzer
        from config import VoiceMapConfig

        # Set up logging to pipe into GUI queue
        q_handler = _QueueHandler(self._q)
        q_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.handlers.clear()
        root_logger.addHandler(q_handler)

        cfg = VoiceMapConfig(
            clarity_threshold=clarity_thresh,
            spl_correction_db=spl_correction,
            output_dir=out_dir,
        )

        success, failed = 0, 0
        n = len(files)

        for i, path in enumerate(files, 1):
            if self._stop_flag.is_set():
                self._q.put(('status', f"Stopped at {i-1}/{n}"))
                break

            fname = Path(path).name
            self._q.put(('progress', (i, n, fname)))

            try:
                analyzer = VoiceMapAnalyzer(cfg)
                analyzer.analyze_and_output_vrp(path)
                success += 1
            except Exception as e:
                logging.error("FAILED %s: %s", fname, e)
                failed += 1

        msg = f"Done: {success} succeeded"
        if failed:
            msg += f", {failed} failed"
        self._q.put(('done', msg))

    # ------------------------------------------------------------------
    # Queue polling (main thread)
    # ------------------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                kind, data = self._q.get_nowait()
                if kind == 'log':
                    tag = 'ERROR' if 'ERROR' in data else ('WARNING' if 'WARNING' in data else '')
                    self._log_append(data, tag)
                elif kind == 'progress':
                    i, n, fname = data
                    self._progress['value'] = i - 1
                    self._lbl_prog.config(text=f"{i}/{n}")
                    self._lbl_status.config(text=f"Processing: {fname}")
                elif kind == 'status':
                    self._lbl_status.config(text=data)
                elif kind == 'done':
                    self._progress['value'] = self._progress['maximum']
                    self._lbl_status.config(text=data)
                    self._lbl_prog.config(text="")
                    self._btn_run.config(state='normal')
                    self._btn_stop.config(state='disabled')
                    self._running = False
                    self._log_append(data, 'OK')
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _log_append(self, msg: str, tag: str = ''):
        self._log_text.configure(state='normal')
        self._log_text.insert('end', msg.rstrip() + '\n', tag)
        self._log_text.see('end')
        self._log_text.configure(state='disabled')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = FonaDynApp()
    # Try to apply a modern theme
    style = ttk.Style(app)
    for theme in ('vista', 'aqua', 'clam'):
        if theme in style.theme_names():
            style.theme_use(theme)
            break
    app.mainloop()


if __name__ == '__main__':
    main()
