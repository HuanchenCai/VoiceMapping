# -*- coding: utf-8 -*-
"""Minimal dict-based i18n for VoiceMap.

Why not gettext
---------------
gettext means .po → .mo compilation, locale dirs, and tooling that
software-copyright reviewers may flag as 'extra dependencies'. We have
~150 strings total; a Python dict is faster to write, faster to read,
and ships as plain UTF-8 source — diff-friendly and one-file-grep-able.

Usage
-----
::

    from voicemap.i18n import tr, set_language, get_language, subscribe

    label = tr("menu.file")           # → "文件" or "File"
    set_language("en")                 # broadcasts to all subscribers
    subscribe(lambda: rebuild_ui())    # called on every language change

A subscriber is a callback with no args. The current language is
persisted to ``~/.voicemap/config.json`` and restored on next start.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

# ── translation table ──────────────────────────────────────────────────
# Keys use dot-separated namespaces ("menu.file", "file.open_wav") so
# greppable scope is obvious.  When the en string is identical to the
# untranslated key (rare), still list it explicitly so a missing entry
# in either language surfaces as a clear gap.
STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        # ── window / status ──
        "app.title":            "嗓音声学品质多维分析图谱",
        "status.ready":         "就绪",
        "status.analyzing":     "分析中…",
        "status.done":          "完成 · {n} 点",
        "status.failed":        "失败",
        "status.tip":           "立体声 WAV · 通道 1 = 麦克风   通道 2 = EGG",

        # ── menubar top labels ──
        "menu.file":            "文件",
        "menu.edit":            "编辑",
        "menu.metric":          "参数",
        "menu.view":            "视图",
        "menu.help":            "帮助",

        # ── file menu ──
        "file.open_wav":        "打开 WAV...",
        "file.open_outdir":     "打开输出目录",
        "file.export_excel":    "导出 Excel",
        "file.gen_report":      "生成报告",
        "file.compare":         "对比 2 段录音…",
        "file.settings":        "设置...",
        "file.quit":            "退出",

        # ── edit menu ──
        "edit.annotate":        "标注",
        "edit.annotate_active": "标注 ●",
        "edit.reset_annotate":  "复位标注",
        "edit.copy_image":      "复制图片",
        "edit.save_image":      "保存图片…",

        # ── metric menu ──
        "metric.prev":          "上一个 metric  ←",
        "metric.next":          "下一个 metric  →",
        "metric.acoustic":      "声学",
        "metric.egg":           "EGG",
        "metric.singing":       "唱歌特异性",
        "metric.cluster":       "聚类",
        "metric.density":       "密度",
        "metric.centroid":      "聚类中心 (Centroid)",
        "metric.centroid.load": "加载 centroid CSV...",
        "metric.centroid.save": "保存当前 centroids",
        "metric.centroid.train":"多 wav 联合训练...",

        # ── view menu ──
        "view.fit":             "拟合曲线…",

        # ── help menu ──
        "help.about":           "关于...",
        "help.language":        "语言",
        "lang.zh":              "中文",
        "lang.en":              "English",

        # ── drop zone ──
        "drop.title":           "拖入 .wav 文件  /  点击浏览",
        "drop.placeholder":     "拖入 .wav 文件开始",
    },
    "en": {
        # ── window / status ──
        "app.title":            "VoiceMap",
        "status.ready":         "Ready",
        "status.analyzing":     "Analyzing…",
        "status.done":          "Done · {n} points",
        "status.failed":        "Failed",
        "status.tip":           "Stereo WAV · Ch 1 = Microphone   Ch 2 = EGG",

        # ── menubar top labels ──
        "menu.file":            "File",
        "menu.edit":            "Edit",
        "menu.metric":          "Metric",
        "menu.view":            "View",
        "menu.help":            "Help",

        # ── file menu ──
        "file.open_wav":        "Open WAV...",
        "file.open_outdir":     "Open Output Folder",
        "file.export_excel":    "Export Excel",
        "file.gen_report":      "Generate Report",
        "file.compare":         "Compare Two Recordings…",
        "file.settings":        "Settings...",
        "file.quit":            "Quit",

        # ── edit menu ──
        "edit.annotate":        "Annotate",
        "edit.annotate_active": "Annotate ●",
        "edit.reset_annotate":  "Clear Annotations",
        "edit.copy_image":      "Copy Image",
        "edit.save_image":      "Save Image…",

        # ── metric menu ──
        "metric.prev":          "Previous metric  ←",
        "metric.next":          "Next metric  →",
        "metric.acoustic":      "Acoustic",
        "metric.egg":           "EGG",
        "metric.singing":       "Singing-specific",
        "metric.cluster":       "Cluster",
        "metric.density":       "Density",
        "metric.centroid":      "Centroid",
        "metric.centroid.load": "Load centroid CSV...",
        "metric.centroid.save": "Save current centroids",
        "metric.centroid.train":"Joint-train across WAVs...",

        # ── view menu ──
        "view.fit":             "Fit curves…",

        # ── help menu ──
        "help.about":           "About...",
        "help.language":        "Language",
        "lang.zh":              "中文",
        "lang.en":              "English",

        # ── drop zone ──
        "drop.title":           "Drop a .wav file  /  click to browse",
        "drop.placeholder":     "Drop a .wav file to begin",
    },
}

# ── runtime state ──────────────────────────────────────────────────────
_current_lang: str = "zh"
_subscribers: list[Callable[[], None]] = []

_CONFIG_PATH = Path.home() / ".voicemap" / "config.json"


# ── public API ─────────────────────────────────────────────────────────
def tr(key: str, **kwargs) -> str:
    """Look up ``key`` in the current language. Returns the key itself
    if not found (so a missing translation surfaces visibly rather than
    silently falling back to "" or English). ``**kwargs`` are passed to
    ``str.format`` so callers can do ``tr("status.done", n=12525)``."""
    s = STRINGS.get(_current_lang, {}).get(key)
    if s is None:
        # Last-resort fallback: try the other language so partial coverage
        # (e.g. an untranslated en string) doesn't show as the bare key.
        for lang, table in STRINGS.items():
            if lang != _current_lang and key in table:
                s = table[key]
                break
        if s is None:
            s = key
    return s.format(**kwargs) if kwargs else s


def get_language() -> str:
    return _current_lang


def set_language(lang: str) -> None:
    """Switch the current language and broadcast to all subscribers.
    Persists the choice to ~/.voicemap/config.json."""
    global _current_lang
    if lang not in STRINGS or lang == _current_lang:
        return
    _current_lang = lang
    _save_to_config(lang)
    for cb in list(_subscribers):
        try:
            cb()
        except Exception:
            # A bad subscriber shouldn't take down language switching.
            pass


def subscribe(callback: Callable[[], None]) -> None:
    """Register ``callback`` to be invoked every time the language
    changes. The callback receives no args; it should re-read ``tr()``
    for the strings it cares about and update its widgets."""
    if callback not in _subscribers:
        _subscribers.append(callback)


def unsubscribe(callback: Callable[[], None]) -> None:
    """Drop a callback. Safe to call with a callback that wasn't
    subscribed (no-op)."""
    try:
        _subscribers.remove(callback)
    except ValueError:
        pass


# ── persistence ────────────────────────────────────────────────────────
def _save_to_config(lang: str) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg = {}
        if _CONFIG_PATH.exists():
            try:
                cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        cfg["language"] = lang
        _CONFIG_PATH.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        # Persistence is best-effort. If ~/.voicemap is unwritable for
        # any reason, the in-memory choice still applies for this session.
        pass


def _load_from_config() -> str:
    try:
        if _CONFIG_PATH.exists():
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            lang = cfg.get("language")
            if lang in STRINGS:
                return lang
    except Exception:
        pass
    return "zh"


# Initialize current language from disk on module load.
_current_lang = _load_from_config()
