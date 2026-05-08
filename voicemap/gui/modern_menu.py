# -*- coding: utf-8 -*-
"""Custom modern menubar + popup, replacing tk.Menu's classic Win32 chrome.

Why this exists
---------------
``tk.Menu`` on Windows binds to the old USER32 menu API, which paints a 1 px
hard white frame around every dropdown — visually inconsistent with modern
Win11 apps (Explorer, Office, VS Code) that use Fluent / WinUI rendering.
Tk has no binding to the Fluent path, so to get a borderless dark-themed
dropdown we have to build the whole thing ourselves.

What we do
----------
* :class:`ModernMenubar` — a horizontal ``tk.Frame`` of clickable button
  labels. Hover changes background to PANEL_HI; click posts a popup below.
* :class:`ModernPopup` — a borderless ``Toplevel`` (overrideredirect) that
  renders item rows by hand. Supports commands, separators, cascades, and
  radiobutton-style state. Auto-dismiss on Escape / click outside.
* Optional rounded corners via Win32 ``SetWindowRgn``.

Multi-monitor / focus / dismiss issues from the old MetricPopup era are
already fixed here (withdraw → set geometry → deiconify; outside-click via
delayed root binding instead of FocusOut).
"""

from __future__ import annotations

import sys
import tkinter as tk
from typing import Callable, Optional

from voicemap.gui.theme import (
    BG, PANEL, PANEL_HI, BORDER, TEXT, MUTED, ACCENT, ACCENT_HI, BG_APP,
    FONT_UI, FONT_UI_B,
)

_ROUND_RADIUS = 6      # popup corner radius in px


# ─── helper: round corners on a Toplevel via Win32 SetWindowRgn ───────────
def _apply_rounded(toplevel: tk.Toplevel, radius: int = _ROUND_RADIUS) -> None:
    """Cut a rounded clip region on ``toplevel`` so corners look modern.

    Win-only; silently no-ops elsewhere or if anything ctypes-related fails.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        from ctypes import windll
        toplevel.update_idletasks()
        w = toplevel.winfo_width()
        h = toplevel.winfo_height()
        if w < 4 or h < 4:
            return
        # tk's frame() returns the HWND as a hex string like "0x12345"
        hwnd = int(toplevel.frame(), 16)
        # CreateRoundRectRgn + SetWindowRgn — Tk owns the HWND; clipping
        # only affects what's visible on screen, not the widget tree.
        hrgn = windll.gdi32.CreateRoundRectRgn(
            0, 0, w + 1, h + 1, radius * 2, radius * 2)
        windll.user32.SetWindowRgn(hwnd, hrgn, True)
    except Exception:
        pass


# ─── ModernMenubar ────────────────────────────────────────────────────────
class ModernMenubar(tk.Frame):
    """Horizontal menu bar, packed at the top of a window's content area.

    Each entry is a label + dropdown factory. Click the label → call
    factory() to build a fresh ModernPopup, then show it below the label.
    """

    def __init__(self, parent: tk.Misc, *, bg: str = PANEL, height: int = 32):
        super().__init__(parent, bg=bg, height=height)
        self.pack_propagate(False)
        self._buttons: list[tk.Label] = []
        self._open_popup: Optional[ModernPopup] = None
        self._open_popup_btn: Optional[tk.Label] = None

    def _close_open_popup(self) -> None:
        if self._open_popup is None:
            return
        try:
            if self._open_popup.winfo_exists():
                self._open_popup.destroy()
        except tk.TclError:
            pass
        self._open_popup = None
        if self._open_popup_btn is not None:
            try:
                self._open_popup_btn.configure(bg=PANEL)
            except tk.TclError:
                pass
        self._open_popup_btn = None

    def add_menu(self, label: str, popup_factory: Callable[[], "ModernPopup"]) -> tk.Label:
        """Add a top-level menu. ``popup_factory`` builds and returns the
        ModernPopup instance every time the menu is opened (rebuilt fresh
        so radiobutton state and dynamic items reflect current data)."""
        btn = tk.Label(self, text=label,
                       bg=PANEL, fg=TEXT,
                       font=FONT_UI,
                       padx=14, pady=6,
                       cursor="hand2")
        btn.pack(side="left")

        def _open():
            popup = popup_factory()
            popup.show_below(btn)
            # When popup destroys (Esc / outside click / item picked),
            # clear our state so the next click reopens cleanly.
            popup.bind("<Destroy>", lambda _e: self._on_popup_destroyed(btn),
                       add="+")
            self._open_popup = popup
            self._open_popup_btn = btn
            btn.configure(bg=ACCENT, fg=BG)

        def _on_enter(_e=None):
            # Auto-switch behavior: if a popup is already open and the
            # cursor moved onto a DIFFERENT menu's button, close the
            # current popup and open this one. Standard desktop-menu UX.
            if self._open_popup is not None:
                if self._open_popup_btn is btn:
                    return   # hovering own active button — leave alone
                self._close_open_popup()
                _open()
            else:
                btn.configure(bg=PANEL_HI)

        def _on_leave(_e=None):
            if self._open_popup is None:
                btn.configure(bg=PANEL)

        def _on_click(_e=None):
            # Toggle: clicking active menu closes it; clicking a
            # different menu (same row) closes current + opens new.
            if self._open_popup is not None and self._open_popup_btn is btn:
                self._close_open_popup()
                return
            self._close_open_popup()
            _open()

        btn.bind("<Enter>", _on_enter)
        btn.bind("<Leave>", _on_leave)
        btn.bind("<Button-1>", _on_click)
        self._buttons.append(btn)
        return btn

    def _on_popup_destroyed(self, btn: tk.Label) -> None:
        """Reset our reference when the popup self-destroys (e.g.
        outside click, Esc, or item picked).

        Tk fires <Destroy> for every descendant before the toplevel
        itself; only react when the active popup is gone."""
        if self._open_popup is not None and not self._open_popup.winfo_exists():
            self._open_popup = None
            self._open_popup_btn = None
            try:
                btn.configure(bg=PANEL, fg=TEXT)
            except tk.TclError:
                pass


# ─── ModernPopup ──────────────────────────────────────────────────────────
class ModernPopup(tk.Toplevel):
    """Borderless dark-themed popup, replacing tk.Menu cascades.

    Items are added via :meth:`add_command`, :meth:`add_separator`,
    :meth:`add_cascade`, :meth:`add_radiobutton`. After all items are added,
    the caller (or ModernMenubar) invokes :meth:`show_below` /
    :meth:`show_at` to position and reveal the popup.
    """

    # Layout dimensions (8 px grid). Same for all popups.
    ROW_PADX  = 14
    ROW_PADY  = 6
    SEP_PAD   = 0   # was 4 — user reported the 4 px PANEL_HI gap above
                    # and below the separator looked like "黑条纹 在每个
                    # 格子的正中间". Zero pad makes the sep a 1 px line
                    # flush against the row, no extra dead space.

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.overrideredirect(True)
        self.configure(bg=PANEL_HI, bd=0, highlightthickness=0)
        self._closing = False
        self._outside_binding = None
        # winfo_toplevel() on a Toplevel returns *itself*, which would
        # bind the outside-click handler to the popup instead of the
        # main window. Walk up via .master to escape the Toplevel.
        try:
            self._app_root: Optional[tk.Misc] = parent.winfo_toplevel()
        except tk.TclError:
            self._app_root = None

        # Inner frame so we have control over border padding (faked
        # 1 px BORDER colour line all around for separation from window).
        self._frame = tk.Frame(self, bg=PANEL_HI)
        self._frame.pack(padx=1, pady=1, fill="both", expand=True)

        self._sub_popup: Optional[ModernPopup] = None
        self._items: list[dict] = []   # bookkeeping: rows, types, callbacks

        self.bind("<Escape>", lambda _e: self.destroy())

    # ── adders ────────────────────────────────────────────────────────
    def add_command(self, label: str,
                    command: Optional[Callable] = None,
                    accelerator: str = "",
                    foreground: str = TEXT) -> None:
        row = self._make_row(label, foreground=foreground,
                             accelerator=accelerator,
                             on_click=lambda: (command and command(), self.destroy()))
        # Hovering a non-cascade row → close any cascade sub-popup that
        # may have been opened by hovering a cascade earlier. Otherwise
        # a stale submenu lingers while the cursor is on a different item.
        row.bind("<Enter>", self._close_sub_popup, add="+")
        for child in row.winfo_children():
            child.bind("<Enter>", self._close_sub_popup, add="+")
        self._items.append({"type": "command", "row": row})

    def add_separator(self) -> None:
        # No-op. Earlier versions drew a 1 px BORDER hairline + 4 px
        # PANEL_HI surround that the user repeatedly judged a "黑横线
        # / design issue". Even after dropping to a 1 px PANEL_HI
        # frame (bg = row bg, supposedly invisible), users still saw
        # a faint band — likely subpixel rounding on the 1 px Frame's
        # geometry. Truly removing the widget removes the artifact.
        # The call stays here so existing code can keep using it as
        # a semantic anchor for future grouping work.
        self._items.append({"type": "separator", "row": None})

    def add_cascade(self, label: str,
                    popup_factory: Callable[[], "ModernPopup"]) -> None:
        row = self._make_row(label, foreground=TEXT,
                             cascade_arrow=True,
                             on_click=lambda r=None: self._open_cascade(r, popup_factory))
        # Click-to-open binding (kept for accessibility / touchscreens).
        def _click_with_row(_e=None, _row=row, _factory=popup_factory):
            self._open_cascade(_row, _factory)
        row.bind("<Button-1>", _click_with_row)
        for child in row.winfo_children():
            child.bind("<Button-1>", _click_with_row)

        # Hover-to-open: schedule _open_cascade after 200 ms so a quick
        # mouse traverse over the cascade row doesn't trigger. Cancelling
        # the after-id on Leave avoids spurious opens. Standard Win32
        # / GTK menu UX, the user pointed out we were missing it.
        cascade_state: dict = {"after_id": None}
        def _hover_open(_e=None, _row=row, _factory=popup_factory):
            if cascade_state["after_id"] is not None:
                try: row.after_cancel(cascade_state["after_id"])
                except Exception: pass
            cascade_state["after_id"] = row.after(
                200, lambda: self._open_cascade(_row, _factory))

        def _hover_cancel(_e=None):
            if cascade_state["after_id"] is not None:
                try: row.after_cancel(cascade_state["after_id"])
                except Exception: pass
                cascade_state["after_id"] = None

        row.bind("<Enter>", _hover_open, add="+")
        row.bind("<Leave>", _hover_cancel, add="+")
        for child in row.winfo_children():
            child.bind("<Enter>", _hover_open, add="+")
            child.bind("<Leave>", _hover_cancel, add="+")
        self._items.append({"type": "cascade", "row": row})

    def _close_sub_popup(self, _e=None) -> None:
        """Close any currently-open cascade submenu. Called by sibling
        rows' <Enter> so navigating away from a cascade auto-closes its
        submenu — no leftover popup hanging out while the cursor is
        clearly on a different item."""
        if self._sub_popup is None:
            return
        try:
            if self._sub_popup.winfo_exists():
                self._sub_popup.destroy()
        except tk.TclError:
            pass
        self._sub_popup = None

    def add_radiobutton(self, label: str, variable: tk.StringVar, value: str,
                        foreground: str = TEXT) -> None:
        is_selected = (variable.get() == value)
        marker = "●" if is_selected else " "
        def _click(v=variable, val=value):
            v.set(val)
            self.destroy()
        row = self._make_row(label, foreground=foreground,
                             prefix=marker, on_click=_click)
        # Same hover-close-sub-popup behavior as add_command.
        row.bind("<Enter>", self._close_sub_popup, add="+")
        for child in row.winfo_children():
            child.bind("<Enter>", self._close_sub_popup, add="+")
        self._items.append({"type": "radio", "row": row,
                             "variable": variable, "value": value})

    # ── row factory ───────────────────────────────────────────────────
    def _make_row(self, label: str, *,
                  foreground: str = TEXT,
                  accelerator: str = "",
                  prefix: str = "",
                  cascade_arrow: bool = False,
                  on_click: Optional[Callable] = None) -> tk.Frame:
        row = tk.Frame(self._frame, bg=PANEL_HI)
        row.pack(fill="x")

        # Optional radio-style marker (●) on the left
        if prefix:
            tk.Label(row, text=prefix, bg=PANEL_HI, fg=ACCENT,
                     font=FONT_UI_B, padx=6).pack(side="left")
        else:
            tk.Frame(row, bg=PANEL_HI, width=18).pack(side="left")

        lbl = tk.Label(row, text=label, bg=PANEL_HI, fg=foreground,
                       font=FONT_UI, anchor="w",
                       padx=self.ROW_PADX, pady=self.ROW_PADY)
        lbl.pack(side="left", fill="x", expand=True)

        if accelerator:
            tk.Label(row, text=accelerator, bg=PANEL_HI, fg=MUTED,
                     font=FONT_UI, padx=12).pack(side="right")
        if cascade_arrow:
            tk.Label(row, text="▸", bg=PANEL_HI, fg=MUTED,
                     font=FONT_UI, padx=8).pack(side="right")

        # Hover/click handling. Bind on row + every child so movement
        # between sub-widgets stays "inside the row".
        children = (row, lbl) + tuple(c for c in row.winfo_children() if c is not lbl)

        def _set_bg(c, color):
            # Frame widgets don't accept fg= — combining bg+fg in one
            # configure call raises TclError on Frames, so the bg
            # never gets applied either. Symptom: 18 px placeholder
            # Frame on the left edge of a hovered (ACCENT) row stayed
            # at PANEL_HI — looked like "item 左边一条黑线".
            # Set bg first (works for everyone), fg afterwards (only
            # widgets that support it).
            try:
                c.configure(bg=color)
            except tk.TclError:
                pass

        def _set_fg(c, color):
            try:
                c.configure(fg=color)
            except tk.TclError:
                pass

        def _hover_in(_e=None):
            _set_bg(row, ACCENT)
            for c in row.winfo_children():
                _set_bg(c, ACCENT)
                _set_fg(c, BG_APP)

        def _hover_out(_e=None):
            _set_bg(row, PANEL_HI)
            for c in row.winfo_children():
                _set_bg(c, PANEL_HI)
                # Restore prefix marker as ACCENT, others as their fg.
                # Placeholder Frames have no `text` so cget raises;
                # _set_fg already swallows that.
                try:
                    is_marker = c.cget("text") in ("▸", "●")
                except tk.TclError:
                    is_marker = False
                _set_fg(c, ACCENT if is_marker else foreground)

        for w in children:
            w.bind("<Enter>", _hover_in, add="+")
            w.bind("<Leave>", _hover_out, add="+")
            if on_click is not None:
                w.bind("<Button-1>",
                       lambda _e, cb=on_click: cb(),
                       add="+")
        return row

    # ── cascade handling ───────────────────────────────────────────────
    def _open_cascade(self, row: tk.Frame,
                      popup_factory: Callable[[], "ModernPopup"]) -> None:
        # Close any prior sub-popup
        if self._sub_popup is not None:
            try:
                if self._sub_popup.winfo_exists():
                    self._sub_popup.destroy()
            except tk.TclError:
                pass
            self._sub_popup = None
        sub = popup_factory()
        # Anchor: top-right of the row
        try:
            row.update_idletasks()
            x = row.winfo_rootx() + row.winfo_width() - 4
            y = row.winfo_rooty()
            sub.show_at(x, y, parent_popup=self)
            self._sub_popup = sub
        except tk.TclError:
            pass

    # ── show / dismiss ─────────────────────────────────────────────────
    def show_below(self, anchor_widget: tk.Widget) -> None:
        try:
            anchor_widget.update_idletasks()
            x = anchor_widget.winfo_rootx()
            y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
            self.show_at(x, y)
        except tk.TclError:
            pass

    def show_at(self, x: int, y: int, parent_popup: Optional["ModernPopup"] = None) -> None:
        try:
            # Re-derive _app_root: for a sub-cascade, share the root with
            # the owner popup so a single outside-click handler covers both.
            if parent_popup is not None:
                self._app_root = parent_popup._app_root
            self.update_idletasks()
            ww = max(self.winfo_reqwidth(), 200)
            wh = max(self.winfo_reqheight(), 40)
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            if x + ww > sw:
                x = max(0, sw - ww - 8)
            if y + wh > sh:
                y = max(0, y - wh)
            self.geometry(f"{ww}x{wh}+{x}+{y}")
            self.deiconify()
            self.lift()
            try:
                self.attributes("-topmost", True)
                self.after(200, lambda: self.attributes("-topmost", False))
            except tk.TclError:
                pass
            _apply_rounded(self, _ROUND_RADIUS)
            # Outside-click dismiss after a short grace period (Tk fires
            # spurious focus-out events during the initial mapping).
            self.after(150, self._install_outside_click)
        except tk.TclError:
            pass

    def _install_outside_click(self) -> None:
        if self._closing or not self.winfo_exists():
            return
        try:
            if self._app_root is not None:
                self._outside_binding = self._app_root.bind(
                    "<ButtonPress>", self._on_root_click, add="+")
        except tk.TclError:
            pass

    def _on_root_click(self, event) -> None:
        if self._closing:
            return
        # Walk widget master chain. Inside self OR inside any sub_popup →
        # don't close. Otherwise close everything.
        w = event.widget
        while w is not None:
            if w is self:
                return
            if self._sub_popup is not None and w is self._sub_popup:
                return
            try:
                w = w.master
            except Exception:
                break
        # Click was outside: close sub first then self
        if self._sub_popup is not None:
            try:
                self._sub_popup.destroy()
            except tk.TclError:
                pass
            self._sub_popup = None
        self.destroy()

    def destroy(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            if self._outside_binding is not None and self._app_root is not None:
                self._app_root.unbind("<ButtonPress>", self._outside_binding)
                self._outside_binding = None
        except (tk.TclError, Exception):
            pass
        if self._sub_popup is not None:
            try:
                self._sub_popup.destroy()
            except tk.TclError:
                pass
            self._sub_popup = None
        try:
            super().destroy()
        except tk.TclError:
            pass
