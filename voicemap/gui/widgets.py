# -*- coding: utf-8 -*-
"""Reusable custom widgets / event-bridge classes for VoiceMap GUI.

Currently:
  * ``MetricPopup``  — borderless Toplevel listbox for picking a metric.
  * ``QueueHandler`` — logging.Handler that pushes records to a tk
                       queue.Queue so the worker thread's logs surface
                       in the GUI log panel.
"""

from __future__ import annotations

import logging
import queue
import sys as _sys
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from voicemap.gui.theme import (
    PANEL, PANEL_HI, BORDER, TEXT, MUTED, ACCENT, BG, FONT_UI, FONT_TOOLTIP,
)

if TYPE_CHECKING:  # avoid runtime circular import
    from voicemap.gui.app import VoiceMapApp


class MetricPopup(tk.Toplevel):
    """Scrollable metric picker, replacing tk.Menu.

    Native tk.Menu doesn't respond to mouse wheel and gets unwieldy with
    80+ items. A Toplevel + Listbox + Scrollbar gives:
      - native mouse wheel scroll
      - Up/Down/PageUp/PageDown keyboard nav
      - section headers as non-selectable accent-coloured rows
      - Esc / focus-out to dismiss
    """

    def __init__(self, app: "VoiceMapApp", sections, current=None, on_select=None):
        super().__init__(app)
        self.app = app
        self.on_select = on_select or (lambda _k: None)
        self._closing = False
        self._outside_binding = None
        # Hide immediately so the user never sees the popup at its
        # default (0, 0) position before we move it. deiconify() at the
        # end after geometry is set.
        self.withdraw()
        self.transient(app)
        # Borderless via overrideredirect — but that combined with eager
        # FocusOut on some Windows versions makes the popup vanish before
        # the user sees it. We keep overrideredirect for the look but
        # detect "click outside" via a root-level ButtonPress binding
        # (set up after 100 ms so the popup has time to appear).
        # IMPORTANT: overrideredirect must be set BEFORE we move the
        # window into position on a non-primary monitor — but on Windows
        # the WM ignores subsequent geometry() calls on a borderless
        # window that has already been mapped. We solve this by keeping
        # the window withdrawn until geometry is final, then deiconify.
        self.overrideredirect(True)
        self.configure(bg=PANEL_HI, bd=1, relief="solid",
                        highlightthickness=1, highlightbackground=BORDER)

        # Build flat list: [(display_text, key_or_None_for_header), ...]
        items = []
        for section_title, metrics in sections:
            items.append((f"  {section_title}", None))
            for m in metrics:
                items.append((f"      {m}", m))
        self._items = items

        # Listbox with conservative max height; scroll for the rest.
        max_visible = min(max(len(items), 6), 22)
        self.lb = tk.Listbox(
            self, height=max_visible, width=28,
            bg=PANEL_HI, fg=TEXT,
            selectbackground=ACCENT, selectforeground=BG,
            activestyle="none",
            font="TkMenuFont",
            bd=0, highlightthickness=0,
            exportselection=False,
        )
        sb = ttk.Scrollbar(self, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True, padx=(2, 0), pady=2)
        sb.pack(side="right", fill="y", pady=2)

        # Populate
        for i, (txt, key) in enumerate(items):
            self.lb.insert("end", txt)
            if key is None:
                # Header row: ACCENT colour, can't be selected (skip in handler)
                self.lb.itemconfigure(i, foreground=ACCENT,
                                       selectbackground=PANEL_HI,
                                       selectforeground=ACCENT)

        # Pre-select current metric if given
        if current is not None:
            for i, (_, key) in enumerate(items):
                if key == current:
                    self.lb.selection_set(i)
                    self.lb.see(i)
                    self.lb.activate(i)
                    break

        # Mouse wheel — needs to scroll OUR listbox even when the cursor
        # is over a different widget below. Use bind_all so events
        # anywhere are caught while the popup is open. Without bind_all,
        # wheel events on the metric button (still under cursor right
        # after popup open) cycle metrics in the main view instead of
        # scrolling our list.
        def on_wheel(e):
            if hasattr(e, "delta") and e.delta:
                self.lb.yview_scroll(-int(e.delta / 120), "units")
            elif getattr(e, "num", 0) == 4:
                self.lb.yview_scroll(-1, "units")
            elif getattr(e, "num", 0) == 5:
                self.lb.yview_scroll(1, "units")
            return "break"
        # Save existing bind_all funcs so we can restore on destroy
        self._prev_wheel    = self.bind_all("<MouseWheel>", on_wheel)
        self._prev_wheel_up = self.bind_all("<Button-4>",   on_wheel)
        self._prev_wheel_dn = self.bind_all("<Button-5>",   on_wheel)

        # Click / Enter to commit
        self.lb.bind("<ButtonRelease-1>", self._on_click)
        self.lb.bind("<Return>",          self._on_click)
        self.lb.bind("<Double-Button-1>", self._on_click)
        # Esc dismisses immediately
        self.bind("<Escape>",  lambda _e: self.destroy())
        # Outside-click dismiss: bind on root after a grace period so the
        # initial focus dance doesn't immediately close us. Don't use
        # FocusOut — Windows fires it during overrideredirect's first
        # mapping and the popup self-destructs before user sees it.
        self.after(150, self._install_outside_click)

        # Position next to the metric button. update_idletasks both on the
        # popup (for own size) AND on the parent toplevel (so winfo_rootx/y
        # on the button is current — without this, on first popup creation
        # winfo_rootx can return 0 because Windows hasn't laid out the
        # parent geometry yet).
        try:
            app.update_idletasks()
        except tk.TclError:
            pass
        self.update_idletasks()
        try:
            ww = max(self.winfo_reqwidth(), 240)
            wh = max(self.winfo_reqheight(), 200)
            bx = app.metric_btn.winfo_rootx()
            by = app.metric_btn.winfo_rooty()
            bh = app.metric_btn.winfo_height()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = bx
            y = by + bh
            # Right-edge clamp (popup wider than what fits to the right).
            if x + ww > sw:
                x = max(0, sw - ww - 8)
            # Bottom-edge: flip above the button if no room below.
            if y + wh > sh:
                y = max(0, by - wh)
            # Sanity: if button rootx/y came back zeroed (rare race on
            # Windows when popup is created before button is mapped),
            # fall back to centring on the parent toplevel rather than
            # silently landing at (0, 0) under the main window.
            if bx <= 0 and by <= 0:
                pw = app.winfo_width()
                ax = app.winfo_rootx()
                ay = app.winfo_rooty()
                x = ax + max(0, (pw - ww) // 2)
                y = ay + 80
            self.geometry(f"{ww}x{wh}+{x}+{y}")
        except tk.TclError as e:
            print(f"[METRIC POPUP] geom EXC: {e}",
                  file=_sys.stderr, flush=True)

        # Now show the popup. Force to front — on Windows, borderless
        # toplevels can spawn under the parent.
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            # Drop topmost after a beat so we don't permanently float
            # above all other apps when the user Alt-Tabs away.
            self.after(200, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass

        self.focus_force()
        self.lb.focus_set()

    def _on_click(self, _e=None):
        sel = self.lb.curselection()
        if not sel:
            return
        idx = sel[0]
        _, key = self._items[idx]
        if key is None:
            # User clicked a header row — keep popup open, do nothing
            return
        self.on_select(key)
        self.destroy()

    def _install_outside_click(self):
        if self._closing or not self.winfo_exists():
            return
        try:
            self._outside_binding = self.app.bind(
                "<ButtonPress>", self._on_root_click, add="+")
        except tk.TclError:
            pass

    def _on_root_click(self, event):
        if self._closing:
            return
        # Walk up event.widget's master chain. If it reaches `self`, the
        # click was inside the popup → keep it open. Otherwise close.
        w = event.widget
        while w is not None:
            if w is self:
                return
            try:
                w = w.master
            except Exception:
                break
        self.destroy()

    def destroy(self):
        self._closing = True
        try:
            if self._outside_binding is not None:
                self.app.unbind("<ButtonPress>", self._outside_binding)
                self._outside_binding = None
        except (tk.TclError, Exception):
            pass
        # Release our bind_all wheel handlers. Widget-level bindings
        # (metric_btn / nav_left / nav_right) live in a separate binding
        # table and are unaffected by unbind_all of the global sequence.
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.unbind_all(seq)
            except (tk.TclError, Exception):
                pass
        try:
            super().destroy()
        except tk.TclError:
            pass


class HoverTooltip:
    """Simple delayed-show tooltip for any tk widget.

    Usage:
        tip = HoverTooltip(widget, lambda: tr("metric.tooltip.OQ"))
        tip.attach()           # binds <Enter> / <Leave> / <Motion>
        tip.set_text_provider(lambda: tr("metric.tooltip.NEW"))  # update later

    Why a class instead of a module-level helper:
      * the text provider is a callback so callers can re-translate
        on the fly (language switch);
      * clean teardown — `detach()` unbinds and kills any pending
        after() callback (avoids leaking timers on widget destroy).

    The tooltip itself is a borderless Toplevel with a small padded
    Label. Same look-and-feel as ModernPopup but stripped down — no
    rounded corners, no click-outside-to-close (it just disappears on
    <Leave>).
    """

    DELAY_MS = 500    # ms to wait before showing (avoids flicker on transit)
    MAX_WIDTH = 440   # wraplength for long descriptions — width chosen so
                      # 中英混排 prose 'CPP = 倒谱在 F0 周期处...' wraps at
                      # fewer awkward English-token boundaries

    def __init__(self, widget, text_provider):
        self._widget = widget
        self._provider = text_provider
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None

    def set_text_provider(self, provider):
        self._provider = provider

    def attach(self):
        self._widget.bind("<Enter>", self._on_enter, add="+")
        self._widget.bind("<Leave>", self._on_leave, add="+")
        self._widget.bind("<ButtonPress>", self._on_leave, add="+")

    def detach(self):
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._hide()

    def _on_enter(self, _event=None):
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self._widget.after(self.DELAY_MS, self._show)

    def _on_leave(self, _event=None):
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._hide()

    def _show(self):
        self._after_id = None
        try:
            text = self._provider()
        except Exception:
            return
        if not text:
            return
        # Position just below + slightly right of the widget
        x = self._widget.winfo_rootx() + 8
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6

        tip = tk.Toplevel(self._widget)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.configure(bg=BORDER)    # 1 px border via outer frame bg
        inner = tk.Frame(tip, bg=PANEL_HI)
        inner.pack(padx=1, pady=1)   # gives the BORDER frame its 1 px ring
        lbl = tk.Label(
            inner,
            text=text,
            bg=PANEL_HI, fg=TEXT,
            font=FONT_TOOLTIP,
            justify="left", anchor="w",
            wraplength=self.MAX_WIDTH,
            padx=12, pady=10,
        )
        lbl.pack()
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def make_focusable_label(parent, text, on_click,
                         *,
                         bg=PANEL, fg=MUTED, font=FONT_UI,
                         cursor="hand2",
                         focus_color=ACCENT,
                         hover_fg=ACCENT):
    """Build a tk.Label that behaves like a button with proper a11y:

      - Tab-reachable (takefocus=1)
      - 2 px focus ring on Tab (highlightcolor=focus_color)
      - <Button-1>, <Return>, <space> all invoke on_click
      - <Enter>/<Leave> swap fg between fg and hover_fg
      - <FocusIn>/<FocusOut> mirror that on keyboard focus

    Used for the metric-bar Prev/Next labels and any other label-as-button
    that needs WCAG 2.1.1 (keyboard) + 2.4.7 (focus visible). Centralised
    here so the ⓘ glyph and other sites share one focus-ring config.
    """
    lbl = tk.Label(parent, text=text,
                   bg=bg, fg=fg, font=font,
                   cursor=cursor,
                   takefocus=1,
                   highlightthickness=2,
                   highlightbackground=bg,
                   highlightcolor=focus_color)
    if on_click is not None:
        lbl.bind("<Button-1>", lambda _e: on_click())
        lbl.bind("<Return>",   lambda _e: on_click())
        lbl.bind("<space>",    lambda _e: on_click())
    lbl.bind("<Enter>",    lambda _e: lbl.configure(fg=hover_fg))
    lbl.bind("<Leave>",
             lambda _e: lbl.configure(
                 fg=hover_fg if lbl.focus_get() is lbl else fg))
    lbl.bind("<FocusIn>",  lambda _e: lbl.configure(fg=hover_fg))
    lbl.bind("<FocusOut>", lambda _e: lbl.configure(fg=fg))
    return lbl


class QueueHandler(logging.Handler):
    """Logging handler that pushes records to a queue.

    The GUI's main thread drains this queue periodically and writes the
    formatted lines into the on-screen log panel — keeping the worker
    thread's loggers thread-safe with regard to tk widgets.
    """

    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record):
        try:
            self.q.put(("log", record.levelname, self.format(record)))
        except Exception:
            pass
