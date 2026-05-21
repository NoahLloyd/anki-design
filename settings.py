"""BetterAnki — settings dialog.

A native Qt dialog dressed in the same editorial system the rest of the
add-on uses. Sections in a scrollable column (no tabs), serif headers,
refined toggles, and a clean accent swatch. Saves to mw.addonManager
config on every change; CSS/JS updates apply on next render.
"""

from typing import Any, Dict, Optional, Tuple

from aqt import mw
from aqt.qt import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColor,
    QColorDialog,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPalette,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSize,
    QSpinBox,
    Qt,
    QVBoxLayout,
    QWidget,
)


ADDON = __name__.split(".")[0]


# --------------------------------------------------------------------------- #
# Palettes
# --------------------------------------------------------------------------- #
PAL_DARK: Dict[str, str] = {
    "paper": "#0b0c0f",
    "panel": "#15171c",
    "ink": "#eceae2",
    "ink_dim": "#9b978a",
    "ink_faint": "#5d5a51",
    "line": "rgba(236,234,226,0.10)",
    "line2": "rgba(236,234,226,0.20)",
    "hover": "rgba(236,234,226,0.05)",
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
}


def _resolve_palette() -> Tuple[Dict[str, str], bool]:
    """Pick dark or light to match the user's theme preference (which itself
    falls back to the OS appearance when set to "system")."""
    cfg = mw.addonManager.getConfig(ADDON) or {}
    pref = cfg.get("theme", "system")
    if pref == "dark":
        return PAL_DARK, True
    if pref == "light":
        return PAL_LIGHT, False
    # "system" — inspect Qt's palette.
    try:
        c = QApplication.palette().color(QPalette.ColorRole.Window)
        is_dark = (c.red() + c.green() + c.blue()) < 384
        return (PAL_DARK if is_dark else PAL_LIGHT), is_dark
    except Exception:
        return PAL_DARK, True


SERIF = '"New York", "Hoefler Text", "Iowan Old Style", Charter, Georgia, serif'
SANS = '"SF Pro Text", "Helvetica Neue", "Segoe UI", system-ui, sans-serif'


def _qss(p: Dict[str, str], accent: str) -> str:
    return f"""
QDialog, QScrollArea, QWidget#root, QWidget#content {{
    background: {p['paper']};
    color: {p['ink']};
    font-family: {SANS};
}}
QScrollArea {{ border: 0; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {p['line2']};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {p['ink_faint']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QLabel {{
    color: {p['ink']};
    font-family: {SANS};
    font-size: 12pt;
    background: transparent;
}}
QLabel[role="title"] {{
    font-family: {SERIF};
    font-size: 22pt;
    font-weight: 500;
    letter-spacing: -0.5px;
    padding: 0 0 4px 0;
    color: {p['ink']};
}}
QLabel[role="subtitle"] {{
    font-size: 10pt;
    color: {p['ink_dim']};
    padding-bottom: 6px;
}}
QLabel[role="section"] {{
    font-family: {SANS};
    font-size: 9pt;
    font-weight: 600;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: {p['ink_faint']};
    padding-top: 22px;
    padding-bottom: 4px;
}}
QLabel[role="field"] {{
    color: {p['ink_dim']};
    font-size: 11pt;
}}
QLabel[role="hint"] {{
    color: {p['ink_faint']};
    font-size: 10pt;
    font-style: italic;
    font-family: {SERIF};
}}
QFrame[role="rule"] {{
    background: {p['line']};
    max-height: 1px;
    min-height: 1px;
    border: 0;
}}

QCheckBox {{
    color: {p['ink']};
    spacing: 12px;
    font-size: 11.5pt;
    padding: 4px 0;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {p['line2']};
    background: {p['panel']};
}}
QCheckBox::indicator:hover {{
    border-color: {p['ink_faint']};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    /* white check via a data: SVG so the indicator is obviously "on" — a
       plain accent fill alone reads as "indeterminate" to many users. */
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='white' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'><polyline points='3,8 7,12 13,4'/></svg>");
}}
QCheckBox::indicator:disabled {{
    background: {p['hover']};
    border-color: {p['line']};
}}

QRadioButton {{
    color: {p['ink']};
    spacing: 10px;
    font-size: 11.5pt;
    padding: 3px 0;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 1px solid {p['line2']};
    background: {p['panel']};
}}
QRadioButton::indicator:hover {{ border-color: {p['ink_faint']}; }}
QRadioButton::indicator:checked {{
    border: 5px solid {accent};
    background: {p['paper']};
}}

QPushButton {{
    background: transparent;
    color: {p['ink_dim']};
    border: 1px solid {p['line2']};
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 11pt;
    font-weight: 500;
}}
QPushButton:hover {{
    color: {p['ink']};
    background: {p['hover']};
    border-color: {p['ink_faint']};
}}
QPushButton#primary {{
    color: white;
    background: {accent};
    border: 1px solid {accent};
}}
QPushButton#primary:hover {{
    /* darken accent a touch on hover so it actually reads as interactive */
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {accent}, stop:1 {accent});
    color: white;
    border-color: {accent};
}}
QPushButton#primary:pressed {{ background: {accent}; }}

QSpinBox, QLineEdit {{
    background: {p['panel']};
    color: {p['ink']};
    border: 1px solid {p['line2']};
    border-radius: 7px;
    padding: 7px 10px;
    font-size: 11.5pt;
    selection-background-color: {accent};
}}
QSpinBox:focus, QLineEdit:focus {{
    border-color: {accent};
    outline: none;
}}
/* Compact, visible spin buttons — were hidden, which made the control feel
   broken. Show small up/down chevrons in the dim ink color. */
QSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border: 0;
    background: transparent;
}}
QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border: 0;
    background: transparent;
}}
QSpinBox::up-arrow {{
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12' fill='none' stroke='%239b978a' stroke-width='1.6' stroke-linecap='round'><polyline points='3,7 6,4 9,7'/></svg>");
    width: 10px; height: 6px;
}}
QSpinBox::down-arrow {{
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12' fill='none' stroke='%239b978a' stroke-width='1.6' stroke-linecap='round'><polyline points='3,5 6,8 9,5'/></svg>");
    width: 10px; height: 6px;
}}

QLineEdit[placeholderText] {{ color: {p['ink_faint']}; }}
"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class ColorSwatch(QPushButton):
    """A 56×30 swatch button that opens the system color picker."""

    def __init__(self, color: str, on_change, parent=None):
        super().__init__(parent)
        self._color = color
        self._on_change = on_change
        self.setFixedSize(QSize(56, 30))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restyle()
        self.clicked.connect(self._pick)

    def value(self) -> str:
        return self._color

    def _restyle(self):
        self.setStyleSheet(
            f"QPushButton {{ background: {self._color};"
            f" border: 1px solid rgba(255,255,255,0.15); border-radius: 7px; }}"
        )

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Choose accent")
        if c.isValid():
            self._color = c.name()
            self._restyle()
            self._on_change(self._color)


def _hrule(palette: Dict[str, str]) -> QFrame:
    f = QFrame()
    f.setProperty("role", "rule")
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"QFrame {{ background: {palette['line']}; }}")
    f.setFixedHeight(1)
    return f


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "section")
    return lbl


def _field_row(label_text: str, widget: QWidget,
               hint: Optional[str] = None) -> QWidget:
    """A `Label  ───  Control` row, vertically aligned, with optional hint."""
    container = QWidget()
    v = QVBoxLayout(container)
    v.setContentsMargins(0, 4, 0, 4)
    v.setSpacing(4)
    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    top.setSpacing(12)
    lbl = QLabel(label_text)
    lbl.setProperty("role", "field")
    lbl.setMinimumWidth(160)
    top.addWidget(lbl)
    top.addStretch(1)
    top.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)
    v.addLayout(top)
    if hint:
        h = QLabel(hint)
        h.setProperty("role", "hint")
        h.setWordWrap(True)
        v.addWidget(h)
    return container


# --------------------------------------------------------------------------- #
# Dialog
# --------------------------------------------------------------------------- #
class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("BetterAnki — Settings")
        self.setMinimumSize(QSize(560, 640))
        self.setObjectName("root")
        self._cfg: Dict[str, Any] = mw.addonManager.getConfig(ADDON) or {}
        self._palette, _ = _resolve_palette()
        self._build()
        self._apply_styles()

    # ----- config helpers ----- #
    def _g(self, key: str, default: Any) -> Any:
        v = self._cfg.get(key)
        return default if v is None else v

    def _set(self, key: str, value: Any) -> None:
        self._cfg[key] = value
        try:
            mw.addonManager.writeConfig(ADDON, self._cfg)
        except Exception:
            pass
        try:
            state = getattr(mw, "state", "")
            if state == "deckBrowser":
                mw.deckBrowser.refresh()
            elif state == "overview":
                mw.overview.refresh()
        except Exception:
            pass

    # ----- styling ----- #
    def _apply_styles(self) -> None:
        accent = self._g("accent", "#6c8cff")
        self.setStyleSheet(_qss(self._palette, accent))

    # ----- ui ----- #
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("content")
        scroll.setWidget(content)

        v = QVBoxLayout(content)
        v.setContentsMargins(36, 30, 36, 22)
        v.setSpacing(6)

        # Title
        title = QLabel("Settings")
        title.setProperty("role", "title")
        v.addWidget(title)
        subtitle = QLabel("BetterAnki preferences — saved as you change them.")
        subtitle.setProperty("role", "subtitle")
        v.addWidget(subtitle)
        v.addSpacing(10)
        v.addWidget(_hrule(self._palette))

        # ----- Appearance ----- #
        v.addWidget(_section_label("Appearance"))

        # Theme radio group
        self._theme_group = QButtonGroup(self)
        theme_box = QWidget()
        tb = QVBoxLayout(theme_box)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(2)
        current = self._g("theme", "system")
        for value, label in [
            ("system", "System (follow OS appearance)"),
            ("light", "Light"),
            ("dark", "Dark"),
        ]:
            rb = QRadioButton(label)
            rb.setChecked(current == value)
            self._theme_group.addButton(rb)
            rb.toggled.connect(
                lambda checked, val=value: checked and self._theme_changed(val)
            )
            tb.addWidget(rb)
        v.addWidget(_field_row("Theme", theme_box))

        # Accent
        self._accent_btn = ColorSwatch(
            self._g("accent", "#6c8cff"),
            lambda c: (self._set("accent", c), self._apply_styles()),
        )
        v.addWidget(_field_row(
            "Accent",
            self._accent_btn,
            "Recolors links, the streak number, current-deck rule, and the "
            "primary Study button.",
        ))

        # ----- Features ----- #
        v.addWidget(_hrule(self._palette))
        v.addWidget(_section_label("Features"))

        for key, label, default, hint in [
            ("sidebar_nav", "Left sidebar navigation", True,
             "Replaces Anki's top toolbar with the BetterAnki rail."),
            ("show_heatmap", "Review-activity heatmap", True,
             "GitHub-style grid of your reviews on the deck homepage."),
            ("show_progress", "Reviewer progress bar", True,
             "Thin progress strip at the top of the reviewer."),
            ("hide_bottom_on_decks", "Hide bottom strip on deck list", True,
             "Frees the homepage from Anki's legacy bottom bar."),
            ("hide_bottom_on_overview", "Hide bottom strip on deck overview",
             True,
             "Removes the Options / Custom Study / Description row."),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(bool(self._g(key, default)))
            cb.toggled.connect(
                lambda checked, k=key: self._set(k, bool(checked))
            )
            row = QVBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            wrap = QWidget()
            wrap.setLayout(row)
            row.addWidget(cb)
            h = QLabel("    " + hint)
            h.setProperty("role", "hint")
            h.setWordWrap(True)
            h.setContentsMargins(28, 0, 0, 6)
            row.addWidget(h)
            v.addWidget(wrap)

        # ----- Heatmap ----- #
        v.addWidget(_hrule(self._palette))
        v.addWidget(_section_label("Heatmap"))

        weeks = QSpinBox()
        weeks.setRange(8, 260)
        weeks.setSingleStep(1)
        weeks.setValue(int(self._g("heatmap_weeks", 53)))
        weeks.setFixedWidth(96)
        weeks.valueChanged.connect(
            lambda val: self._set("heatmap_weeks", int(val))
        )
        v.addWidget(_field_row(
            "Minimum weeks shown",
            weeks,
            "The heatmap always extends back to your first review; never "
            "renders fewer than this many columns.",
        ))

        # ----- Typography ----- #
        v.addWidget(_hrule(self._palette))
        v.addWidget(_section_label("Typography"))

        serif = QLineEdit(self._g("font_serif", ""))
        serif.setPlaceholderText('e.g. "Iowan Old Style", Georgia')
        serif.setMinimumWidth(220)
        serif.editingFinished.connect(
            lambda: self._set("font_serif", serif.text().strip())
        )
        v.addWidget(_field_row(
            "Display serif", serif,
            "Prepended to the existing serif stack. Headings, deck names. "
            "Leave blank for the system default.",
        ))

        sans = QLineEdit(self._g("font_sans", ""))
        sans.setPlaceholderText('e.g. "Inter", "SF Pro Text"')
        sans.setMinimumWidth(220)
        sans.editingFinished.connect(
            lambda: self._set("font_sans", sans.text().strip())
        )
        v.addWidget(_field_row(
            "Body sans", sans,
            "Prepended to the existing sans stack. Labels, counts, UI.",
        ))

        # ----- Anki — surfaces native Anki dialogs we couldn't merge inline ----- #
        v.addWidget(_hrule(self._palette))
        v.addWidget(_section_label("Anki"))

        def _open(fn, *args):
            """Close our dialog then call fn(*args). Anki dialogs can't be
            modal-stacked nicely; close-then-open keeps focus sane."""
            def go():
                try:
                    self.accept()
                except Exception:
                    pass
                try:
                    fn(*args)
                except Exception:
                    pass
            return go

        def native_btn(label: str, hint: str, callback) -> QWidget:
            wrap = QWidget()
            row = QVBoxLayout(wrap)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            b = QPushButton(label + "  →")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(callback)
            b.setStyleSheet("text-align: left;")
            row.addWidget(b)
            h = QLabel("    " + hint)
            h.setProperty("role", "hint")
            h.setWordWrap(True)
            row.addWidget(h)
            return wrap

        v.addWidget(native_btn(
            "Open Anki Preferences",
            "The standard Anki preferences dialog (review settings, sync, "
            "appearance, etc.).",
            _open(mw.onPrefs),
        ))

        def _open_current_deck_opts():
            try:
                from aqt.deckoptions import display_options_for_deck_id
                from anki.decks import DeckId
                did = DeckId(int(mw.col.decks.get_current_id()))
                self.accept()
                display_options_for_deck_id(did)
            except Exception:
                pass

        v.addWidget(native_btn(
            "Open deck options",
            "Configure the current deck's review settings, new-card limits, "
            "FSRS parameters, etc.",
            _open_current_deck_opts,
        ))

        v.addWidget(native_btn(
            "Manage note types",
            "Add, edit, and delete note types (card templates).",
            _open(mw.onNoteTypes),
        ))

        v.addWidget(native_btn(
            "Open add-ons",
            "Manage installed add-ons.",
            _open(mw.addonManager.onAddonsDialog),
        ))

        v.addSpacing(20)
        v.addStretch(1)

        # ----- Footer (sticky) ----- #
        footer = QWidget()
        footer.setObjectName("root")
        f = QHBoxLayout(footer)
        f.setContentsMargins(36, 14, 36, 18)
        f.setSpacing(10)
        restore = QPushButton("Restore defaults")
        restore.clicked.connect(self._restore_defaults)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        f.addWidget(restore)
        f.addStretch(1)
        f.addWidget(close_btn)

        outer.addWidget(_hrule(self._palette))
        outer.addWidget(footer)

    # ----- handlers ----- #
    def _theme_changed(self, value: str) -> None:
        self._set("theme", value)
        # Re-resolve the dialog palette so the dialog itself reflects the
        # new choice immediately (Light ↔ Dark switch is live).
        self._palette, _ = _resolve_palette()
        self._apply_styles()

    def _restore_defaults(self) -> None:
        defaults = {
            "theme": "system",
            "accent": "#6c8cff",
            "sidebar_nav": True,
            "show_heatmap": True,
            "show_progress": True,
            "hide_bottom_on_decks": True,
            "hide_bottom_on_overview": True,
            "heatmap_weeks": 53,
            "font_serif": "",
            "font_sans": "",
        }
        self._cfg = defaults
        try:
            mw.addonManager.writeConfig(ADDON, defaults)
        except Exception:
            pass
        # Re-render the deck browser with defaults; rebuild the dialog so the
        # widgets reflect the new state. The dialog stays open.
        try:
            state = getattr(mw, "state", "")
            if state == "deckBrowser":
                mw.deckBrowser.refresh()
        except Exception:
            pass
        # Rebuild the dialog in-place so radio/checkbox/swatch states reset.
        try:
            # Clear all children from the dialog
            for child in self.findChildren(QWidget):
                child.deleteLater()
            old_layout = self.layout()
            if old_layout is not None:
                QWidget().setLayout(old_layout)
        except Exception:
            pass
        self._palette, _ = _resolve_palette()
        self._build()
        self._apply_styles()


def open_settings(parent: Any = None) -> None:
    dlg = SettingsDialog(parent or mw)
    dlg.exec()
