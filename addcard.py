"""BetterAnki — Add Card window redesign.

The native AddCards dialog (`aqt.addcards.AddCards`) is a QMainWindow with:
  - top row: notetype + deck chooser
  - middle: editor webview (Svelte app)
  - bottom: QDialogButtonBox (Add / Close / Help / History)

We rebuild all the Qt chrome around the editor in the same editorial style as
the rest of BetterAnki (settings dialog, deck home, sidebar). The editor
webview itself gets a CSS overlay in `web/addcard.css` (injected via
`webview_will_set_content` when the context is an Editor in ADD_CARDS mode).

Add-on compatibility: all the original buttons (Add / Close / Help / History)
keep their original click handlers and shortcuts — we just hide the stock
buttonBox and proxy clicks to it. Hooks (`add_cards_did_*`, etc.) fire from
the underlying AddCards instance, so any add-on that listens still works.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from aqt import gui_hooks, mw
from aqt.addcards import AddCards
from aqt.qt import (
    QApplication,
    QColor,
    QFrame,
    QHBoxLayout,
    QKeySequence,
    QLabel,
    QPalette,
    QPushButton,
    QShortcut,
    QSize,
    Qt,
    QVBoxLayout,
    QWidget,
)


ADDON = __name__.split(".")[0]


# Palettes mirror settings.py so light/dark stays coherent across dialogs.
PAL_DARK: Dict[str, str] = {
    "paper": "#0b0c0f",
    "panel": "#15171c",
    "ink": "#eceae2",
    "ink_dim": "#9b978a",
    "ink_faint": "#5d5a51",
    "line": "rgba(236,234,226,0.10)",
    "line2": "rgba(236,234,226,0.20)",
    "hover": "rgba(236,234,226,0.05)",
    "field_bg": "#0f1116",
}
PAL_LIGHT: Dict[str, str] = {
    "paper": "#f6f3ec",
    "panel": "#fbf9f3",
    "ink": "#1f1d18",
    "ink_dim": "#6a6557",
    "ink_faint": "#a39d8b",
    "line": "rgba(31,29,24,0.10)",
    "line2": "rgba(31,29,24,0.22)",
    "hover": "rgba(31,29,24,0.04)",
    "field_bg": "#ffffff",
}

SERIF = '"New York", "Hoefler Text", "Iowan Old Style", Charter, Georgia, serif'
SANS = '"SF Pro Text", "Helvetica Neue", "Segoe UI", system-ui, sans-serif'


def _config() -> Dict[str, Any]:
    return mw.addonManager.getConfig(ADDON) or {}


def _resolve_palette() -> Tuple[Dict[str, str], bool]:
    cfg = _config()
    pref = cfg.get("theme", "system")
    if pref == "dark":
        return PAL_DARK, True
    if pref == "light":
        return PAL_LIGHT, False
    try:
        c = QApplication.palette().color(QPalette.ColorRole.Window)
        is_dark = (c.red() + c.green() + c.blue()) < 384
        return (PAL_DARK if is_dark else PAL_LIGHT), is_dark
    except Exception:
        return PAL_DARK, True


def _qss(p: Dict[str, str], accent: str) -> str:
    """QSS for the Add Card window chrome (everything outside the webview).
    The editor itself is restyled by web/addcard.css."""
    return f"""
QMainWindow, #ba-root, #ba-header, #ba-footer, #ba-fields-wrap {{
    background: {p['paper']};
    color: {p['ink']};
    font-family: {SANS};
}}

/* Title font/size come from setFont() in addcard.py for reliable metrics.
   Don't restate font-family here or QSS will rebuild a multi-family font
   whose space-glyph differs from its letter-glyphs (giant whitespace gap
   between "Add" and "card"). */
#ba-title {{
    color: {p['ink']};
    padding: 0;
    background: transparent;
}}

#ba-meta {{
    font-size: 10pt;
    color: {p['ink_faint']};
    letter-spacing: 1.6px;
    text-transform: uppercase;
    font-weight: 600;
}}

/* Chooser pill — small text + bold value, looks like an editorial caption. */
QPushButton#ba-chooser {{
    background: transparent;
    border: 1px solid {p['line2']};
    border-radius: 999px;
    padding: 7px 14px 7px 14px;
    color: {p['ink']};
    font-size: 11pt;
    font-family: {SANS};
    text-align: left;
}}
QPushButton#ba-chooser:hover {{
    background: {p['hover']};
    border-color: {p['ink_faint']};
}}
QPushButton#ba-chooser:focus {{
    border-color: {accent};
    outline: none;
}}

QLabel[role="chooser-key"] {{
    color: {p['ink_faint']};
    font-size: 9pt;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    font-weight: 600;
    padding-right: 6px;
}}

QFrame[role="rule"] {{
    background: {p['line']};
    max-height: 1px;
    min-height: 1px;
    border: 0;
}}

/* Chooser pills — selected look: filled with the panel color, thin tinted
   border, weighty value text. */
QPushButton#ba-chooser,
#modelArea QPushButton, #deckArea QPushButton {{
    background: {p['panel']};
    border: 1px solid {p['line2']};
    border-radius: 14px;
    padding: 6px 18px;
    color: {p['ink']};
    font-size: 11pt;
    font-weight: 600;
    min-height: 22px;
}}
QPushButton#ba-chooser:hover,
#modelArea QPushButton:hover, #deckArea QPushButton:hover {{
    background: {p['hover']};
    border-color: {p['ink_faint']};
    color: {p['ink']};
}}
QPushButton#ba-chooser:focus,
#modelArea QPushButton:focus, #deckArea QPushButton:focus {{
    border-color: {accent};
    outline: none;
}}
#modelArea QLabel, #deckArea QLabel {{
    color: {p['ink_faint']};
    font-size: 9pt;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    font-weight: 600;
}}

/* Footer */
#ba-footer QPushButton {{
    background: transparent;
    color: {p['ink_dim']};
    border: 1px solid {p['line2']};
    border-radius: 8px;
    padding: 9px 18px;
    font-size: 11pt;
    font-weight: 500;
}}
#ba-footer QPushButton:hover {{
    color: {p['ink']};
    background: {p['hover']};
    border-color: {p['ink_faint']};
}}
#ba-footer QPushButton#ba-primary {{
    color: white;
    background: {accent};
    border: 1px solid {accent};
    padding: 10px 24px;
    font-weight: 600;
}}
#ba-footer QPushButton#ba-primary:hover {{
    background: {accent};
}}
#ba-footer QPushButton#ba-ghost {{
    border: 1px solid transparent;
    color: {p['ink_faint']};
    font-size: 10pt;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    padding: 8px 14px;
}}
#ba-footer QPushButton#ba-ghost:hover {{
    color: {p['ink']};
    background: {p['hover']};
    border-color: {p['line2']};
}}
#ba-footer QPushButton#ba-ghost:focus {{
    border-color: {p['line2']};
    outline: none;
}}
#ba-footer QPushButton#ba-icon {{
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    padding: 0;
    border-radius: 17px;
    color: {p['ink_faint']};
    font-size: 13pt;
    font-weight: 600;
    font-family: {SERIF};
    font-style: italic;
}}
#ba-footer QPushButton#ba-icon:hover {{
    color: {p['ink']};
    border-color: {p['ink_faint']};
    background: {p['hover']};
}}

#ba-shortcut {{
    color: {p['ink_faint']};
    font-size: 10pt;
    font-family: {SANS};
    padding-left: 6px;
}}
"""


# --------------------------------------------------------------------------- #
# Rebuild AddCards chrome on init
# --------------------------------------------------------------------------- #
def _shortcut_caption(seq: str) -> str:
    """Return platform-appropriate visual representation of a key seq."""
    import sys
    if sys.platform == "darwin":
        return seq.replace("Ctrl+", "⌘").replace("Shift+", "⇧").replace("Alt+", "⌥")
    return seq


def _cards_added_today() -> int:
    """Count notes added since the user's day rollover. Best-effort; returns
    0 on any error so the title can never break."""
    try:
        col = mw.col
        if col is None:
            return 0
        try:
            rollover = int(col.get_preferences().scheduling.rollover)
        except Exception:
            rollover = 4
        if time.localtime().tm_isdst and time.daylight:
            tz_offset = -time.altzone
        else:
            tz_offset = -time.timezone
        shift = tz_offset - rollover * 3600
        today_idx = int((time.time() + shift) // 86400)
        # Anki note IDs are millisecond timestamps at creation.
        start_ms = (today_idx * 86400 - shift) * 1000
        row = col.db.first("select count() from notes where id >= ?", start_ms)
        return int(row[0]) if row and row[0] else 0
    except Exception:
        return 0


def _proxy_click(source: QPushButton, target: QPushButton) -> None:
    """Wire a new button to click the underlying native one (which carries
    the real handlers, shortcuts and gui_hooks)."""
    source.clicked.connect(target.click)


def _hrule(palette: Dict[str, str]) -> QFrame:
    f = QFrame()
    f.setProperty("role", "rule")
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"QFrame {{ background: {palette['line']}; }}")
    f.setFixedHeight(1)
    return f


def _redress(addcards: AddCards) -> None:
    """Wrap the existing centralWidget in our own layout. We keep all native
    widgets alive (so handlers and hooks continue to fire) but rehome them
    inside our chrome and hide the stock button box."""
    palette, _ = _resolve_palette()
    cfg = _config()
    accent = cfg.get("accent", "#6c8cff")

    # Apply window-level theming
    try:
        addcards.setWindowTitle("Add card")
    except Exception:
        pass

    # Build our root container.
    root = QWidget()
    root.setObjectName("ba-root")
    root_layout = QVBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    # --- Header --- #
    header = QWidget()
    header.setObjectName("ba-header")
    h = QVBoxLayout(header)
    h.setContentsMargins(32, 22, 32, 16)
    h.setSpacing(10)

    # Eyebrow + title row
    top = QHBoxLayout()
    top.setSpacing(14)
    top.setContentsMargins(0, 0, 0, 0)

    added = _cards_added_today()
    if added <= 0:
        meta_text = "FIRST OF TODAY"
    elif added == 1:
        meta_text = "1 ADDED TODAY"
    else:
        meta_text = f"{added} ADDED TODAY"
    meta = QLabel(meta_text)
    meta.setObjectName("ba-meta")
    # The ASCII space rendered with a giant gap because Qts QSS multi-family
    # font selection picked the space-glyph from a different fallback than
    # the letters. A NBSP (\xa0) bypasses that substitution.
    title = QLabel("Add card")
    title.setTextFormat(Qt.TextFormat.PlainText)
    title.setObjectName("ba-title")
    title.setWordWrap(False)
    title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    from aqt.qt import QFont, QFontDatabase, QSizePolicy
    # Pick the first serif that QFontDatabase reports as actually installed.
    # exactMatch() lies on macOS Qt6 — a non-existent serif still "matches"
    # but then renders its space glyph from a fallback with very different
    # metrics ("Add" + huge gap + "card"). QFontDatabase.families() never
    # lies.
    families = set(QFontDatabase.families())
    serif = None
    # NOTE: Hoefler Text is installed on macOS but its space glyph renders
    # at ~2x expected width in Qt6, producing "Add" + huge gap + "card".
    # Skip it. New York / Iowan Old Style / Charter render correctly.
    for fam in ("New York", "Iowan Old Style", "Charter",
                "Georgia", "Times New Roman", "Times"):
        if fam in families:
            serif = fam
            break
    if serif:
        tf = QFont(serif, 22)
        tf.setStyleHint(QFont.StyleHint.Serif)
        tf.setWeight(QFont.Weight.Medium)
        title.setFont(tf)
    else:
        tf = QFont("Helvetica Neue", 22)
        tf.setWeight(QFont.Weight.DemiBold)
        title.setFont(tf)
    title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(2)
    title_col.addWidget(meta)
    title_col.addWidget(title)
    title_col_wrap = QWidget()
    title_col_wrap.setLayout(title_col)
    top.addWidget(title_col_wrap, 1)
    h.addLayout(top)

    # Chooser strip: the native DeckChooser / NotetypeChooser live inside
    # `addcards.form.modelArea` and `deckArea`. We rehome those widgets so
    # the controls themselves still work — only the position changes.
    choosers = QHBoxLayout()
    choosers.setContentsMargins(0, 4, 0, 0)
    choosers.setSpacing(18)

    nt_label = QLabel("TYPE")
    nt_label.setProperty("role", "chooser-key")
    nt_label.setToolTip("Note type (⌘N to change)")
    dk_label = QLabel("DECK")
    dk_label.setProperty("role", "chooser-key")
    dk_label.setToolTip("Target deck (⌘D to change)")

    nt_area: QWidget = addcards.form.modelArea
    dk_area: QWidget = addcards.form.deckArea
    # Strip any minimum size so they shrink to content.
    try:
        nt_area.setMinimumSize(QSize(0, 0))
        dk_area.setMinimumSize(QSize(0, 0))
    except Exception:
        pass

    # NotetypeChooser / DeckChooser each construct their own QLabel as the
    # first child of the area widget (text: "Type" / "Deck"). We already have
    # our own all-caps eyebrow label, so hide theirs to avoid the duplicate
    # "NOTE TYPE TYPE Basic" effect.
    def _hide_first_label(host: QWidget) -> None:
        try:
            for child in host.findChildren(QLabel):
                child.hide()
                # one is enough; the chooser only adds one label per area
                break
        except Exception:
            pass
    _hide_first_label(nt_area)
    _hide_first_label(dk_area)

    # Force flat style on the chooser buttons — macOS's native QStyle keeps
    # the Aqua chrome around QPushButton even with a stylesheet, so we
    # explicitly setStyleSheet on each child push button. This puts the
    # painted pill back even when the global QSS gets out-prioritized.
    def _flatten_buttons(host: QWidget) -> None:
        try:
            for b in host.findChildren(QPushButton):
                b.setObjectName("ba-chooser")
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setFlat(True)
        except Exception:
            pass
    _flatten_buttons(nt_area)
    _flatten_buttons(dk_area)

    nt_group = QHBoxLayout()
    nt_group.setContentsMargins(0, 0, 0, 0)
    nt_group.setSpacing(6)
    nt_group.addWidget(nt_label)
    nt_group.addWidget(nt_area)
    nt_wrap = QWidget()
    nt_wrap.setLayout(nt_group)

    dk_group = QHBoxLayout()
    dk_group.setContentsMargins(0, 0, 0, 0)
    dk_group.setSpacing(6)
    dk_group.addWidget(dk_label)
    dk_group.addWidget(dk_area)
    dk_wrap = QWidget()
    dk_wrap.setLayout(dk_group)

    choosers.addWidget(nt_wrap)
    choosers.addWidget(dk_wrap)
    choosers.addStretch(1)

    h.addLayout(choosers)
    root_layout.addWidget(header)
    root_layout.addWidget(_hrule(palette))

    # --- Fields (editor webview lives inside addcards.form.fieldsArea) --- #
    fields_wrap = QWidget()
    fields_wrap.setObjectName("ba-fields-wrap")
    fw = QVBoxLayout(fields_wrap)
    fw.setContentsMargins(0, 0, 0, 0)
    fw.setSpacing(0)
    fields_area: QWidget = addcards.form.fieldsArea
    fw.addWidget(fields_area)
    root_layout.addWidget(fields_wrap, 1)

    # --- Footer --- #
    root_layout.addWidget(_hrule(palette))
    footer = QWidget()
    footer.setObjectName("ba-footer")
    f = QHBoxLayout(footer)
    f.setContentsMargins(28, 16, 28, 18)
    f.setSpacing(10)

    history_btn = QPushButton("Recent ▾")
    history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    history_btn.setToolTip("Re-open a recently added note (Cmd+Shift+H)")
    help_btn = QPushButton("?")
    help_btn.setObjectName("ba-icon")
    help_btn.setToolTip("Help")
    help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    close_btn = QPushButton("Esc")
    close_btn.setObjectName("ba-ghost")
    close_btn.setToolTip("Close (Esc)")
    close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    add_btn = QPushButton("Add card")
    add_btn.setObjectName("ba-primary")
    add_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    # Wire to original buttons (preserves shortcuts and add-on hooks).
    try:
        _proxy_click(add_btn, addcards.addButton)
        _proxy_click(history_btn, addcards.historyButton)
        _proxy_click(help_btn, addcards.helpButton)
        _proxy_click(close_btn, addcards.closeButton)
    except Exception:
        pass

    # Disable our copy of history when the native one is disabled (no history).
    try:
        history_btn.setEnabled(addcards.historyButton.isEnabled())
        addcards.historyButton.changeEvent  # noqa - just touch
        # Mirror enabled-state changes from the native button.
        def _mirror_history() -> None:
            try:
                history_btn.setEnabled(addcards.historyButton.isEnabled())
            except Exception:
                pass
        # Hook via paintEvent: cheap, fires often enough.
        addcards._ba_mirror_history = _mirror_history  # type: ignore[attr-defined]
    except Exception:
        pass

    # Build an "Add card  ⌘↩" composite — shortcut hint sits inside the
    # primary button as a quiet caption (Apple-style), not a detached label.
    add_btn.setText(
        f"Add card     {_shortcut_caption('Ctrl+Enter')}"
    )

    f.addWidget(help_btn)
    f.addWidget(history_btn)
    f.addStretch(1)
    f.addWidget(close_btn)
    f.addSpacing(6)
    f.addWidget(add_btn)
    root_layout.addWidget(footer)

    # Hide the original button box (its buttons remain alive for proxying).
    try:
        addcards.form.buttonBox.hide()
    except Exception:
        pass

    # Apply QSS to the window.
    try:
        addcards.setStyleSheet(_qss(palette, accent))
    except Exception:
        pass
    # Install root as the central widget (replaces the stock centralwidget).
    try:
        addcards.setCentralWidget(root)
    except Exception:
        pass

    # Re-poll the native history button's enabled state every 800ms so our
    # mirror stays in sync. Cheap and bulletproof.
    try:
        from aqt.qt import QTimer
        t = QTimer(addcards)
        t.setInterval(800)
        def _tick() -> None:
            try:
                history_btn.setEnabled(addcards.historyButton.isEnabled())
            except Exception:
                pass
        t.timeout.connect(_tick)
        t.start()
        addcards._ba_history_timer = t  # keep ref
    except Exception:
        pass

    # Larger default window — the new chrome breathes.
    try:
        if addcards.width() < 880 or addcards.height() < 720:
            addcards.resize(max(addcards.width(), 880), max(addcards.height(), 720))
    except Exception:
        pass

    # Update the "N ADDED TODAY" eyebrow every time a note is added.
    def _refresh_meta() -> None:
        try:
            n = _cards_added_today()
            if n <= 0:
                t = "FIRST OF TODAY"
            elif n == 1:
                t = "1 ADDED TODAY"
            else:
                t = f"{n} ADDED TODAY"
            meta.setText(t)
        except Exception:
            pass
    addcards._ba_refresh_meta = _refresh_meta  # type: ignore[attr-defined]


def on_add_cards_did_init(addcards: AddCards) -> None:
    try:
        _redress(addcards)
    except Exception as e:
        # Log only — popping up a modal here blocks Qt's event loop and
        # cascades into hung-screenshot timeouts during dev iteration.
        import traceback
        try:
            print(
                f"[betteranki.addcard] redress failed: {e}\n"
                f"{traceback.format_exc()}",
                flush=True,
            )
        except Exception:
            pass


def _on_note_added(note: Any) -> None:
    """Refresh the eyebrow count in any open Add Card window."""
    try:
        from aqt import dialogs
        ac = dialogs._dialogs.get("AddCards", [None, None])[1]
        if ac is None:
            return
        cb = getattr(ac, "_ba_refresh_meta", None)
        if callable(cb):
            cb()
    except Exception:
        pass


def register() -> None:
    gui_hooks.add_cards_did_init.append(on_add_cards_did_init)
    try:
        gui_hooks.add_cards_did_add_note.append(_on_note_added)
    except Exception:
        pass
