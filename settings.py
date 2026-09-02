"""Anki Design — settings, embedded as a tab in Anki's native Preferences.

The whole UI lives in ``AnkiDesignSettingsPage`` (a plain ``QWidget``) so it
can be dropped into ``aqt.preferences.Preferences``' ``QTabWidget``. We hook
in via ``Preferences.setupOptions`` — Anki's documented (legacy) extension
point — so every newly-opened Preferences dialog gains an "Anki Design" tab.

Every entry point that used to spawn a standalone dialog (sidebar cog, the
Tools-menu action, Cmd+,, the add-on manager's "Config" button) now opens
Anki Preferences and selects our tab. Config writes happen immediately on
each change, separate from Anki's own Save/Cancel cycle.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from aqt import mw
from aqt.qt import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColor,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFont,
    QFontDatabase,
    QFrame,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPalette,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSize,
    QSpinBox,
    Qt,
    QUrl,
    QVBoxLayout,
    QWidget,
)


HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")

try:
    from . import colors as _colors
except Exception:  # pragma: no cover — standalone import during tooling
    _colors = None


def _icon_url(name: str) -> str:
    """Plain absolute path to an icon in our web/ folder, slash-normalised
    so Qt's QSS ``url(...)`` accepts it on every platform. Qt's QSS URL
    parser silently drops data:image/svg+xml URLs in some builds, and a
    file:// URL gets joined to the CWD when parsed — passing the raw
    absolute path is what actually works."""
    return os.path.join(WEB_DIR, name).replace(os.sep, "/")


ADDON = __name__.split(".")[0]
TAB_TITLE = "Anki Design"
PAGE_OBJECT_NAME = "baSettings"


def _human_version() -> str:
    """Best-effort read of manifest.json's human_version. Falls back to a
    short string so the footer wordmark always renders something."""
    import json
    import os
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "manifest.json")) as fh:
            data = json.load(fh)
        return str(data.get("human_version", "")) or "—"
    except Exception:
        return "—"


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
        is_dark = True
    elif pref == "light":
        is_dark = False
    else:
        try:
            c = QApplication.palette().color(QPalette.ColorRole.Window)
            is_dark = (c.red() + c.green() + c.blue()) < 384
        except Exception:
            is_dark = True
    pal = PAL_DARK if is_dark else PAL_LIGHT
    try:
        from . import colors as _colors
        pal = _colors.apply_background(pal, cfg, is_dark)
    except Exception:
        pass
    return pal, is_dark


# Lead with fonts Qt reliably resolves. macOS-bundled "Iowan Old Style"
# and "New York" trip Qt's missing-family warning even though AppKit
# resolves them; Georgia + Hoefler Text are picked up cleanly, so put
# those first to avoid silently falling through to QFont's last-resort
# (typically a sans-serif), which would defeat the editorial title.
SERIF = 'Georgia, "Hoefler Text", "Times New Roman", serif'
SANS = '"Helvetica Neue", "Segoe UI", system-ui, sans-serif'


# Curated recommendations the font picker shows first. We intersect this
# with the actually-installed fonts on the user's system so we never show
# a font they can't choose. Order is "best aesthetic match" first.
SERIF_RECOMMENDATIONS: List[str] = [
    "Iowan Old Style",
    "New York",
    "Hoefler Text",
    "Charter",
    "Cochin",
    "Baskerville",
    "Garamond",
    "Palatino",
    "Georgia",
    "Cambria",
    "Times New Roman",
    "Times",
]
SANS_RECOMMENDATIONS: List[str] = [
    "Inter",
    "SF Pro Text",
    "SF Pro Display",
    "Helvetica Neue",
    "Helvetica",
    "Avenir Next",
    "Avenir",
    "Lucida Grande",
    "Segoe UI",
    "Verdana",
    "Tahoma",
    "Calibri",
    "Arial",
]


def _installed_fonts() -> List[str]:
    """Family names of every font QFontDatabase reports installed."""
    try:
        return sorted(set(QFontDatabase.families()))
    except Exception:
        return []


def _recommended_available(category: str) -> List[str]:
    """Recommended fonts intersected with what's actually installed,
    preserving the recommendation order."""
    recs = SERIF_RECOMMENDATIONS if category == "serif" else SANS_RECOMMENDATIONS
    installed = set(_installed_fonts())
    return [f for f in recs if f in installed]


# QSS is applied to the page widget itself; Qt scopes the rules to that
# widget + its descendants, so sibling Preferences tabs are not affected.
def _qss(p: Dict[str, str], accent: str) -> str:
    return f"""
QWidget#{PAGE_OBJECT_NAME}, QWidget#{PAGE_OBJECT_NAME} QScrollArea,
QWidget#{PAGE_OBJECT_NAME} QWidget#viewport,
QWidget#{PAGE_OBJECT_NAME} QWidget#content,
QWidget#{PAGE_OBJECT_NAME} QWidget#footer {{
    background: {p['paper']};
    color: {p['ink']};
    font-family: {SANS};
}}
QWidget#{PAGE_OBJECT_NAME} QScrollArea {{ border: 0; }}
QWidget#{PAGE_OBJECT_NAME} QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 0;
}}
QWidget#{PAGE_OBJECT_NAME} QScrollBar::handle:vertical {{
    background: {p['line2']};
    border-radius: 5px;
    min-height: 30px;
}}
QWidget#{PAGE_OBJECT_NAME} QScrollBar::handle:vertical:hover {{
    background: {p['ink_faint']};
}}
QWidget#{PAGE_OBJECT_NAME} QScrollBar::add-line:vertical,
QWidget#{PAGE_OBJECT_NAME} QScrollBar::sub-line:vertical {{ height: 0; }}

QWidget#{PAGE_OBJECT_NAME} QLabel {{
    color: {p['ink']};
    font-family: {SANS};
    font-size: 15pt;
    background: transparent;
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="title"] {{
    font-family: {SERIF};
    font-size: 30pt;
    font-weight: 500;
    letter-spacing: -0.5px;
    padding: 0 0 4px 0;
    color: {p['ink']};
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="page-title"] {{
    font-family: {SERIF};
    font-size: 28pt;
    font-weight: 500;
    letter-spacing: -0.4px;
    padding: 0;
    margin: 0;
    color: {p['ink']};
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="subtitle"] {{
    font-size: 14pt;
    color: {p['ink_dim']};
    padding-bottom: 6px;
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="intro"] {{
    font-size: 14pt;
    color: {p['ink_dim']};
    /* Flush-left so the intro line x-aligns with the serif title above
       (whose left-bearing is reset by margin/padding:0). */
    padding: 0;
    margin: 0;
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="mono"] {{
    font-family: "SF Mono", "Menlo", Consolas, monospace;
    font-size: 14pt;
    color: {p['ink_dim']};
    letter-spacing: 0.2px;
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="section"] {{
    font-family: {SANS};
    font-size: 12pt;
    font-weight: 700;
    letter-spacing: 1.6px;
    text-transform: uppercase;
    color: {p['ink']};
    padding: 0;
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="field"] {{
    color: {p['ink']};
    font-size: 15pt;
    font-weight: 600;
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="hint"] {{
    color: {p['ink_dim']};
    font-size: 13pt;
    font-family: {SANS};
}}
QWidget#{PAGE_OBJECT_NAME} QLabel[role="subgroup"] {{
    color: {p['ink_dim']};
    font-size: 14pt;
    font-weight: 500;
    padding: 4px 0 4px 0;
}}
/* "optional" tag next to optional inputs — a quiet plain word, not a pill,
   so it doesn't compete with the all-caps section labels. */
QWidget#{PAGE_OBJECT_NAME} QLabel[role="tag"] {{
    color: {p['ink_faint']};
    font-size: 13pt;
    font-style: italic;
    background: transparent;
    padding: 0;
}}
/* Footer wordmark — small serif "Anki Design vX.Y.Z" sitting opposite the
   Restore link so the bottom of the page reads as a deliberate close. */
QWidget#{PAGE_OBJECT_NAME} QLabel[role="wordmark"] {{
    color: {p['ink_faint']};
    font-family: {SERIF};
    font-size: 13pt;
    font-style: italic;
}}
QWidget#{PAGE_OBJECT_NAME} QFrame[role="rule"] {{
    background: {p['line']};
    max-height: 1px;
    min-height: 1px;
    border: 0;
}}

QWidget#{PAGE_OBJECT_NAME} QCheckBox {{
    color: {p['ink']};
    spacing: 14px;
    font-size: 14pt;
    padding: 6px 0;
}}
QWidget#{PAGE_OBJECT_NAME} QCheckBox::indicator {{
    width: 22px;
    height: 22px;
    border-radius: 6px;
    border: 1px solid {p['line2']};
    background: {p['panel']};
}}
QWidget#{PAGE_OBJECT_NAME} QCheckBox::indicator:hover {{
    border-color: {p['ink_faint']};
}}
QWidget#{PAGE_OBJECT_NAME} QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    /* White check loaded from an on-disk SVG. Qt6's QSS parser silently
       drops data:image/svg+xml URLs in some builds, leaving the indicator
       as a flat accent square that reads as "indeterminate" — using a
       real file works everywhere. */
    image: url({_icon_url("check.svg")});
}}
QWidget#{PAGE_OBJECT_NAME} QCheckBox::indicator:disabled {{
    background: {p['hover']};
    border-color: {p['line']};
}}

QWidget#{PAGE_OBJECT_NAME} QRadioButton {{
    color: {p['ink_dim']};
    spacing: 12px;
    font-size: 14pt;
    padding: 5px 0;
}}
/* Darken the currently-selected radio's text so the active option reads
   even without the dot being in the user's focus. */
QWidget#{PAGE_OBJECT_NAME} QRadioButton:checked {{
    color: {p['ink']};
}}
QWidget#{PAGE_OBJECT_NAME} QRadioButton::indicator {{
    width: 20px;
    height: 20px;
    border-radius: 10px;
    border: 1px solid {p['line2']};
    background: {p['panel']};
}}
QWidget#{PAGE_OBJECT_NAME} QRadioButton::indicator:hover {{
    border-color: {p['ink_faint']};
}}
/* Radial gradient → proper radio dot (small accent fill on paper ring). */
QWidget#{PAGE_OBJECT_NAME} QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        fx:0.5, fy:0.5, stop:0.32 {accent}, stop:0.38 {p['paper']});
    border: 1px solid {accent};
}}

QWidget#{PAGE_OBJECT_NAME} QPushButton {{
    background: transparent;
    color: {p['ink_dim']};
    border: 1px solid {p['line2']};
    border-radius: 9px;
    padding: 12px 22px;
    font-size: 14pt;
    font-weight: 500;
}}
QWidget#{PAGE_OBJECT_NAME} QPushButton:hover {{
    color: {p['ink']};
    background: {p['hover']};
    border-color: {p['ink_faint']};
}}
/* The page's primary action — "Done" closes the dialog. Filled in the
   accent color so the user can find it instantly at the bottom-right. */
QWidget#{PAGE_OBJECT_NAME} QPushButton#primary {{
    background: {accent};
    color: white;
    border: 1px solid {accent};
    padding: 12px 32px;
    font-size: 14pt;
    font-weight: 600;
}}
QWidget#{PAGE_OBJECT_NAME} QPushButton#primary:hover {{
    background: {accent};
    color: white;
    /* Subtle darken via overlay shadow approximates an active state without
       touching the swatch color the user picked. */
    border-color: rgba(0,0,0,0.18);
}}
/* Jump-to-native-dialog links — read as quiet links, not form fields. */
QWidget#{PAGE_OBJECT_NAME} QPushButton#jump {{
    background: transparent;
    border: 0;
    color: {p['ink']};
    padding: 6px 0;
    text-align: left;
    font-size: 15pt;
    font-weight: 500;
}}
QWidget#{PAGE_OBJECT_NAME} QPushButton#jump:hover {{
    color: {accent};
    background: transparent;
}}
/* The "Restore defaults" rescue path — quiet ghost link; underlines only
   on hover so it doesn't compete for attention. */
QWidget#{PAGE_OBJECT_NAME} QPushButton#quiet {{
    background: transparent;
    border: 0;
    color: {p['ink_faint']};
    padding: 4px 0;
    font-size: 10.5pt;
    font-weight: 500;
}}
QWidget#{PAGE_OBJECT_NAME} QPushButton#quiet:hover {{
    color: {p['ink']};
    background: transparent;
    text-decoration: underline;
}}

QWidget#{PAGE_OBJECT_NAME} QSpinBox,
QWidget#{PAGE_OBJECT_NAME} QLineEdit,
QWidget#{PAGE_OBJECT_NAME} QComboBox {{
    background: {p['panel']};
    color: {p['ink']};
    border: 1px solid {p['line2']};
    border-radius: 9px;
    padding: 11px 14px;
    font-size: 14pt;
    selection-background-color: {accent};
}}
QWidget#{PAGE_OBJECT_NAME} QSpinBox:focus,
QWidget#{PAGE_OBJECT_NAME} QLineEdit:focus,
QWidget#{PAGE_OBJECT_NAME} QComboBox:focus {{
    border-color: {accent};
    outline: none;
}}

QWidget#{PAGE_OBJECT_NAME} QComboBox {{ padding-right: 28px; }}
QWidget#{PAGE_OBJECT_NAME} QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border: 0;
    background: transparent;
}}
QWidget#{PAGE_OBJECT_NAME} QComboBox::down-arrow {{
    image: url({_icon_url("chevron-down.svg")});
    width: 10px; height: 6px;
}}
/* The popup list — same paper palette, sharp selection in accent. */
QComboBox QAbstractItemView {{
    background: {p['panel']};
    color: {p['ink']};
    border: 1px solid {p['line2']};
    border-radius: 7px;
    padding: 6px 0;
    outline: 0;
    selection-background-color: {accent};
    selection-color: white;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 16px;
    min-height: 26px;
    font-size: 13pt;
    border: 0;
}}
QComboBox QAbstractItemView::separator {{
    height: 1px;
    background: {p['line']};
    margin: 6px 8px;
}}
/* Compact, visible spin buttons — Anki's default Qt theme renders them
   nearly invisible against our panel color. */
QWidget#{PAGE_OBJECT_NAME} QSpinBox {{ padding-right: 22px; }}
QWidget#{PAGE_OBJECT_NAME} QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border: 0;
    background: transparent;
}}
QWidget#{PAGE_OBJECT_NAME} QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border: 0;
    background: transparent;
}}
QWidget#{PAGE_OBJECT_NAME} QSpinBox::up-arrow {{
    image: url({_icon_url("chevron-up.svg")});
    width: 10px; height: 6px;
}}
QWidget#{PAGE_OBJECT_NAME} QSpinBox::down-arrow {{
    image: url({_icon_url("chevron-down.svg")});
    width: 10px; height: 6px;
}}

QWidget#{PAGE_OBJECT_NAME} QLineEdit[placeholderText] {{ color: {p['ink_faint']}; }}
"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class ColorSwatch(QPushButton):
    """A 44×22 swatch button that opens the system color picker. Sized to
    sit comfortably alongside a single line of body text — bigger swatches
    overpower their hex label in a stacked row."""

    def __init__(self, color: str, on_change, parent=None):
        super().__init__(parent)
        self._color = color
        self._on_change = on_change
        self.setFixedSize(QSize(44, 22))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restyle()
        self.clicked.connect(self._pick)

    def value(self) -> str:
        return self._color

    def _restyle(self):
        # Use a low-contrast border that works in both light and dark
        # palettes — the previous fixed rgba(255,255,255,...) only read
        # against dark backgrounds, leaving the swatch edgeless in light.
        self.setStyleSheet(
            "QPushButton {"
            f" background: {self._color};"
            " border: 1px solid rgba(0,0,0,0.18);"
            " border-radius: 6px; }"
        )

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Choose accent")
        if c.isValid():
            self._color = c.name()
            self._restyle()
            self._on_change(self._color)


class PaletteSwatchRow(QWidget):
    """A row of small color swatches the user clicks to choose. The
    currently-selected swatch grows a thin accent ring around it so the
    state is unambiguous against any swatch background.

    ``options`` is a list of ``(value, color_hex, label)`` triples. When
    a swatch is clicked, ``on_change(value)`` fires."""

    def __init__(self, options: List[Tuple[str, str, str]], current: str,
                 ink_faint: str, accent: str, on_change, parent=None) -> None:
        super().__init__(parent)
        self._options = options
        self._on_change = on_change
        self._current = current
        self._ink_faint = ink_faint
        self._accent = accent
        self._buttons: Dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for value, color, label in options:
            btn = QPushButton()
            btn.setFixedSize(QSize(38, 24))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(label)
            btn.clicked.connect(lambda _, v=value: self._select(v))
            self._buttons[value] = btn
            layout.addWidget(btn)
        layout.addStretch(1)
        self._restyle()

    def _select(self, value: str) -> None:
        self._current = value
        self._restyle()
        self._on_change(value)

    def _restyle(self) -> None:
        check_path = os.path.join(WEB_DIR, "check.svg").replace(os.sep, "/")
        check_icon = QIcon(check_path)
        for value, color, _ in self._options:
            btn = self._buttons[value]
            picked = value == self._current
            if picked:
                # Selected swatch wears the same white check the checkboxes
                # use, plus a contrasting white inner ring. Border colour
                # alone is too easy to miss on top of a vivid swatch.
                btn.setIcon(check_icon)
                btn.setIconSize(QSize(14, 14))
                style = (
                    "QPushButton {"
                    f" background: {color};"
                    " border: 2px solid white;"
                    " border-radius: 6px; }"
                )
            else:
                btn.setIcon(QIcon())  # clear
                style = (
                    "QPushButton {"
                    f" background: {color};"
                    " border: 1px solid rgba(0,0,0,0.22);"
                    " border-radius: 6px; }"
                    "QPushButton:hover { border-color: rgba(0,0,0,0.45); }"
                )
            btn.setStyleSheet(style)


class FontPicker(QComboBox):
    """Editable combo of recommended + installed fonts for a category.

    Layout: a blank "(use default)" item first, then the recommended list
    filtered to what's installed, then a separator, then every other
    family QFontDatabase reports. Each item is rendered in its own font
    so users can see what they're picking. The combo is editable so a
    user can still type a font Anki itself will pick up later, even if
    Qt's database doesn't list it."""

    DEFAULT_LABEL = "(use default)"

    def __init__(self, category: str, current: str = "", parent=None) -> None:
        super().__init__(parent)
        self._category = category
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaximumWidth(280)
        self.setMinimumWidth(220)

        # Blank → "use default fallback stack".
        self.addItem(self.DEFAULT_LABEL, userData="")

        recommended = _recommended_available(category)
        self._fill(recommended)

        # All-other-installed below a separator so the recommended block
        # always stays at the top.
        remaining = [
            f for f in _installed_fonts()
            if f not in recommended and not f.startswith(".")
        ]
        if remaining:
            self.insertSeparator(self.count())
            self._fill(remaining)

        # Match the saved value to the corresponding combo entry; if no
        # exact match, drop the literal text into the editable field so
        # the user keeps their unknown-to-Qt choice.
        self.set_value(current)

    def _fill(self, fonts: List[str]) -> None:
        for name in fonts:
            self.addItem(name, userData=name)
            self.setItemData(
                self.count() - 1, QFont(name, 11), Qt.ItemDataRole.FontRole
            )

    def set_value(self, value: str) -> None:
        value = (value or "").strip()
        if not value:
            self.setCurrentIndex(0)
            self.setEditText("")
            return
        for i in range(self.count()):
            if self.itemData(i) == value:
                self.setCurrentIndex(i)
                return
        # Unknown — keep it in the editable text so the user can see
        # and edit their custom choice.
        self.setEditText(value)

    def value(self) -> str:
        """Current value with blank meaning "use default"."""
        text = (self.currentText() or "").strip()
        if text == self.DEFAULT_LABEL:
            return ""
        return text


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


def _section_block(palette: Dict[str, str], text: str) -> QWidget:
    """Section label preceded by a thin rule, so the page has a clear visual
    rhythm — title, rule, sections-with-rules. A wall of section labels
    alone blurs together as the eye scans down."""
    wrap = QWidget()
    box = QVBoxLayout(wrap)
    box.setContentsMargins(0, 26, 0, 0)
    box.setSpacing(12)
    rule = QFrame()
    rule.setProperty("role", "rule")
    rule.setFrameShape(QFrame.Shape.HLine)
    rule.setStyleSheet(f"QFrame {{ background: {palette['line']}; }}")
    rule.setFixedHeight(1)
    box.addWidget(rule)
    lbl = QLabel(text)
    lbl.setProperty("role", "section")
    box.addWidget(lbl)
    return wrap


def _field_row(label_text: str, widget: QWidget,
               hint: Optional[str] = None) -> QWidget:
    """Stacked field: label above, control below, optional hint under the
    control. Stacked layout means every row in the page shares the same
    horizontal rhythm — left-aligned at the page margin — instead of the
    two-column "label / value" split, which left a wasteland of empty
    pixels to the right of every short control."""
    container = QWidget()
    v = QVBoxLayout(container)
    v.setContentsMargins(0, 6, 0, 8)
    v.setSpacing(4)
    if label_text:
        lbl = QLabel(label_text)
        lbl.setProperty("role", "field")
        v.addWidget(lbl)
    v.addWidget(widget)
    if hint:
        h = QLabel(hint)
        h.setProperty("role", "hint")
        h.setWordWrap(True)
        v.addWidget(h)
    return container


# --------------------------------------------------------------------------- #
# Tab page
# --------------------------------------------------------------------------- #
def _config_defaults() -> Dict[str, Any]:
    """The shipped config.json — single source of truth for defaults."""
    try:
        d = mw.addonManager.addonConfigDefaults(ADDON)
        if isinstance(d, dict) and d:
            return dict(d)
    except Exception:
        pass
    try:
        import json
        with open(os.path.join(HERE, "config.json")) as fh:
            return dict(json.load(fh))
    except Exception:
        return {}


def _refresh_views() -> None:
    """Re-render whatever is on screen so a changed setting shows up at
    once, and re-assert the chrome (top toolbar / bottom strip) which is
    driven by the same config."""
    try:
        state = getattr(mw, "state", "")
        if state == "deckBrowser":
            mw.deckBrowser.refresh()
        elif state == "overview":
            mw.overview.refresh()
    except Exception:
        pass
    try:
        from importlib import import_module
        pkg = import_module(ADDON)
        state = getattr(mw, "state", "")
        if state in ("deckBrowser", "overview", "review"):
            pkg.on_state_did_change(state, state)
    except Exception:
        pass


class AnkiDesignSettingsPage(QWidget):
    """The Anki Design settings UI, packaged as a tab for Anki's Preferences."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(PAGE_OBJECT_NAME)
        self._cfg: Dict[str, Any] = mw.addonManager.getConfig(ADDON) or {}
        self._palette, _ = _resolve_palette()
        # Strong refs to button groups created in _build; Qt will drop
        # exclusivity if the group goes out of scope.
        self._radio_groups: List[QButtonGroup] = []
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
        _refresh_views()

    # ----- styling ----- #
    def _apply_styles(self) -> None:
        accent = self._g("accent", "#6c8cff")
        self.setStyleSheet(_qss(self._palette, accent))

    # Close the enclosing Preferences dialog so a follow-on native dialog can
    # open without modal stacking. Walks up the parent chain because the tab
    # is several layers deep inside a QTabWidget → QStackedWidget → QDialog.
    def _close_enclosing_dialog(self) -> None:
        w: Optional[QWidget] = self.parentWidget()
        while w is not None:
            if isinstance(w, QDialog):
                try:
                    w.accept()
                except Exception:
                    pass
                return
            w = w.parentWidget()

    # ----- ui ----- #
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)

        # Inside the scroll viewport: the content widget fills the full
        # width of the dialog tab. We use generous internal padding to
        # keep text from running right to the edge, but skip the previous
        # centered narrow-column approach — the user wanted the page to
        # actually use the dialog's horizontal space.
        viewport = QWidget()
        viewport.setObjectName("viewport")
        scroll.setWidget(viewport)

        vp = QHBoxLayout(viewport)
        vp.setContentsMargins(0, 0, 0, 0)
        vp.setSpacing(0)

        content = QWidget()
        content.setObjectName("content")
        vp.addWidget(content, 1)

        v = QVBoxLayout(content)
        # Wide internal padding so controls breathe but the column still
        # spans the dialog width. (44px left/right matches the footer
        # padding so the columns visually line up.)
        v.setContentsMargins(44, 36, 44, 36)
        v.setSpacing(6)

        # Header — a small "Settings" wordmark so the column has a clear
        # start. The tab itself says "Anki Design", so the header doesn't
        # need to repeat that.
        header = QLabel("Settings")
        header.setProperty("role", "page-title")
        v.addWidget(header)
        intro = QLabel(
            "Most changes apply immediately. Reviewer changes take effect "
            "from the next study session."
        )
        intro.setProperty("role", "intro")
        intro.setWordWrap(True)
        v.addWidget(intro)

        # ----- Appearance ----- #
        v.addWidget(_section_block(self._palette, "Appearance"))

        self._theme_group = QButtonGroup(self)
        # Strong ref so QButtonGroup isn't dropped on the next event loop tick.
        self._radio_groups.append(self._theme_group)
        theme_box = QWidget()
        tb = QHBoxLayout(theme_box)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(14)
        current = self._g("theme", "system")
        for value, label in [
            ("system", "System"),
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
        tb.addStretch(1)
        # Theme is self-explanatory — three labels named for what they do.
        # A hint just restating "System follows the OS" adds noise.
        v.addWidget(_field_row("Theme", theme_box))

        accent_box = QWidget()
        ab = QHBoxLayout(accent_box)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(12)
        self._accent_btn = ColorSwatch(
            self._g("accent", "#6c8cff"),
            self._on_accent_changed,
        )
        self._accent_value = QLabel(self._g("accent", "#6c8cff").upper())
        self._accent_value.setProperty("role", "mono")
        # Vertically center the hex label against the 30px swatch so the
        # text baseline doesn't sit awkwardly low.
        ab.addWidget(self._accent_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        ab.addWidget(self._accent_value, 0, Qt.AlignmentFlag.AlignVCenter)
        ab.addStretch(1)
        v.addWidget(_field_row(
            "Accent", accent_box,
            "Used for links and the primary Study button.",
        ))

        v.addWidget(self._radio_row(
            "density", "comfortable",
            [("compact", "Compact"),
             ("cozy", "Cozy"),
             ("comfortable", "Comfortable")],
            "Density",
            "Compact fits more on screen; Comfortable gives each row more air.",
        ))

        # Backgrounds — a preset pair per theme plus a custom swatch. Blank
        # config = the theme's own paper; a hex = override.
        v.addWidget(self._bg_row(
            "background_light", "Background (light)",
            [("", "Paper"), ("#ffffff", "White")], "#f3f3f3",
            "Page colour in light mode. Paper is the default warm tone.",
        ))
        v.addWidget(self._bg_row(
            "background_dark", "Background (dark)",
            [("", "Ink"), ("#000000", "Black")], "#15161a",
            "Page colour in dark mode.",
        ))

        def feature_row(key: str, label: str, default: bool, hint: str) -> QWidget:
            cb = QCheckBox(label)
            cb.setChecked(bool(self._g(key, default)))
            cb.toggled.connect(
                lambda checked, k=key: self._set(k, bool(checked))
            )
            wrap = QWidget()
            row = QVBoxLayout(wrap)
            row.setContentsMargins(0, 2, 0, 4)
            row.setSpacing(2)
            row.addWidget(cb)
            h = QLabel(hint)
            h.setProperty("role", "hint")
            h.setWordWrap(True)
            h.setContentsMargins(30, 0, 0, 0)
            row.addWidget(h)
            return wrap

        # ----- Home page ----- #
        v.addWidget(_section_block(self._palette, "Home page"))
        v.addSpacing(2)
        v.addWidget(feature_row(
            "sidebar_nav", "Left sidebar navigation", True,
            "Replaces Anki's top toolbar with the Anki Design rail. The "
            "inline windows below need it.",
        ))
        v.addWidget(feature_row(
            "show_today", "Today panel", True,
            "Cards and minutes studied today, with a per-hour histogram.",
        ))
        v.addWidget(feature_row(
            "show_streak", "Streak counter", True,
            "Flame + day count above the heatmap.",
        ))
        v.addWidget(feature_row(
            "hide_bottom_on_decks",
            "Hide Anki's bottom strip on the deck list", True,
            "Those actions live in the sidebar and the deck menus instead.",
        ))
        v.addWidget(feature_row(
            "hide_bottom_on_overview",
            "Hide Anki's bottom strip on the deck overview", True,
            "Removes the Options / Custom Study / Description row.",
        ))

        # ----- Deck list ----- #
        v.addWidget(_section_block(self._palette, "Deck list"))
        v.addWidget(self._radio_row(
            "deck_tree_startup", "remember",
            [("remember", "Remember"),
             ("expanded", "Expanded"),
             ("collapsed", "Collapsed")],
            "Sub-decks on startup",
            "Remember keeps each deck's own open/closed state, synced like "
            "Anki does. Expanded or Collapsed start every launch the same "
            "way.",
        ))
        v.addSpacing(2)
        v.addWidget(feature_row(
            "deck_drag_move", "Drag decks to move them", True,
            "Drop a deck onto another to nest it, or onto the top-level "
            "zone to un-nest it. “Move to…” in the deck menu does the same.",
        ))
        v.addWidget(feature_row(
            "single_deck_hero", "Single-deck hero", True,
            "With one top-level deck, show it as a big card with its "
            "sub-decks listed beneath.",
        ))
        v.addWidget(feature_row(
            "skip_overview", "Click a deck to start studying", True,
            "Off: clicking a deck opens Anki's overview page first.",
        ))

        # ----- Reviewer ----- #
        v.addWidget(_section_block(self._palette, "Reviewer"))

        v.addWidget(self._radio_row(
            "reviewer_card_width", "medium",
            [("narrow", "Narrow"),
             ("medium", "Medium"),
             ("wide", "Wide"),
             ("full", "Full")],
            "Card width",
            "Maximum width of the card body during review.",
        ))

        v.addWidget(self._radio_row(
            "reviewer_font_size", "medium",
            [("small", "Small"),
             ("medium", "Medium"),
             ("large", "Large"),
             ("x-large", "XL")],
            "Font size",
            "Base size used to render the card front and back.",
        ))

        v.addWidget(self._radio_row(
            "reviewer_answer_buttons", "intervals",
            [("intervals", "Interval chips"),
             ("native", "Anki's buttons")],
            "Answer buttons",
            "Interval chips show just the next interval under the answer. "
            "Anki's buttons restore the labelled Again / Hard / Good / Easy "
            "bar.",
        ))
        v.addSpacing(2)
        v.addWidget(feature_row(
            "reviewer_card_styling", "Style card content", True,
            "Apply Anki Design typography and colours to the card itself. "
            "Off keeps your note type's own styling; the header and answer "
            "keys stay.",
        ))
        v.addWidget(feature_row(
            "show_progress", "Progress bar", True,
            "Thin progress strip across the top of the reviewer.",
        ))
        v.addWidget(feature_row(
            "click_to_reveal", "Click the card to show the answer", True,
            "Anywhere on the card works like Space.",
        ))
        v.addWidget(feature_row(
            "press_feedback", "Press feedback", True,
            "A soft bloom from the key you graded with.",
        ))
        v.addWidget(feature_row(
            "inline_edit", "Edit cards in place", True,
            "E edits the fields right on the card. Off opens Anki's edit "
            "window.",
        ))

        # ----- Windows ----- #
        v.addWidget(_section_block(self._palette, "Windows"))
        v.addSpacing(2)
        v.addWidget(feature_row(
            "cmdk", "Command palette (⌘K / Ctrl+K)", True,
            "Search decks, cards, tags and actions from anywhere.",
        ))
        v.addWidget(feature_row(
            "embed_add", "Add cards inside the main window", True,
            "Off opens Anki's separate Add window.",
        ))
        v.addWidget(feature_row(
            "embed_browse", "Browse inside the main window", True,
            "Off opens Anki's separate Browse window.",
        ))
        v.addWidget(feature_row(
            "embed_stats", "Stats inside the main window", True,
            "Off opens Anki's separate Stats window.",
        ))
        v.addWidget(feature_row(
            "embed_settings", "Preferences inside the main window", True,
            "Off opens Anki's Preferences dialog.",
        ))
        v.addWidget(feature_row(
            "restyle_addcard", "Redesigned Add window", True,
            "The editorial Add card layout. Off restores Anki's stock Add "
            "window (and opens it as a separate window).",
        ))
        v.addWidget(feature_row(
            "congrats_redesign", "Redesigned finished-deck page", True,
            "Session summary and a Keep going list when a deck is done.",
        ))
        v.addWidget(feature_row(
            "silent_sync", "Quiet sync", True,
            "Progress shows in the sidebar instead of a dialog. Off restores "
            "Anki's sync progress window.",
        ))

        # ----- Heatmap ----- #
        # Heatmap-related settings live together: the toggle to enable it,
        # plus the minimum-weeks slider that controls its width. Used to be
        # split across Features + its own one-field section, which felt
        # arbitrary.
        v.addWidget(_section_block(self._palette, "Heatmap"))
        v.addSpacing(2)

        # Track the heatmap toggle so we can gray out the minimum-weeks
        # field when the heatmap is off — leaving it active suggests the
        # value still matters, which it doesn't.
        heatmap_cb = QCheckBox("Show review-activity heatmap")
        heatmap_cb.setChecked(bool(self._g("show_heatmap", True)))
        weeks = QSpinBox()
        weeks.setRange(8, 260)
        weeks.setSingleStep(1)
        weeks.setValue(int(self._g("heatmap_weeks", 53)))
        weeks.setFixedWidth(96)
        weeks.valueChanged.connect(
            lambda val: self._set("heatmap_weeks", int(val))
        )
        weeks_wrap = QWidget()
        ww = QHBoxLayout(weeks_wrap)
        ww.setContentsMargins(0, 0, 0, 0)
        ww.addWidget(weeks)
        ww.addStretch(1)
        weeks_row = _field_row(
            "Minimum weeks shown", weeks_wrap,
            "For new collections; older ones extend back to your first review.",
        )

        def _toggle_heatmap(checked: bool) -> None:
            self._set("show_heatmap", bool(checked))
            weeks_row.setEnabled(bool(checked))

        heatmap_cb.toggled.connect(_toggle_heatmap)
        weeks_row.setEnabled(heatmap_cb.isChecked())

        heatmap_wrap = QWidget()
        hrow = QVBoxLayout(heatmap_wrap)
        hrow.setContentsMargins(0, 2, 0, 4)
        hrow.setSpacing(2)
        hrow.addWidget(heatmap_cb)
        hint = QLabel("A daily-review grid on the deck homepage.")
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        hint.setContentsMargins(30, 0, 0, 0)
        hrow.addWidget(hint)
        v.addWidget(heatmap_wrap)
        # Indent the weeks row so it visually nests under the toggle —
        # the spinbox is meaningful only when the toggle above is on.
        weeks_indent = QWidget()
        wi = QHBoxLayout(weeks_indent)
        wi.setContentsMargins(30, 0, 0, 0)
        wi.addWidget(weeks_row)
        v.addWidget(weeks_indent)

        # Heatmap palette swatches.
        current_accent = self._g("accent", "#6c8cff")
        palette_options: List[Tuple[str, str, str]] = [
            ("accent", current_accent, "Match the accent color"),
            ("green", "#2ea043", "GitHub green"),
            ("teal", "#14b8a6", "Teal"),
            ("violet", "#8b5cf6", "Violet"),
            ("rose", "#f43f5e", "Rose"),
            ("amber", "#f59e0b", "Amber"),
        ]
        palette_widget = PaletteSwatchRow(
            palette_options,
            current=self._g("heatmap_palette", "accent"),
            ink_faint=self._palette["ink_faint"],
            accent=current_accent,
            on_change=lambda v: self._set("heatmap_palette", v),
        )
        self._heatmap_palette_widget = palette_widget
        palette_indent = QWidget()
        pi = QHBoxLayout(palette_indent)
        pi.setContentsMargins(30, 4, 0, 0)
        pi.addWidget(_field_row(
            "Palette", palette_widget,
            "Color used for the heatmap cells. “Accent” follows your accent above.",
        ))
        v.addWidget(palette_indent)

        # ----- Typography ----- #
        v.addWidget(_section_block(self._palette, "Typography"))

        # Cap font-name inputs at a comfortable single-line width so they
        # don't stretch into a 700px form field on a wide page.
        serif = FontPicker("serif", self._g("font_serif", ""))
        serif.currentTextChanged.connect(
            lambda _t: self._set("font_serif", serif.value())
        )
        v.addWidget(_field_row(
            "Display serif",
            self._font_wrap(serif),
            "Used for headings and deck names. Falls back to Georgia.",
        ))

        sans = FontPicker("sans", self._g("font_sans", ""))
        sans.currentTextChanged.connect(
            lambda _t: self._set("font_sans", sans.value())
        )
        v.addWidget(_field_row(
            "Body sans",
            self._font_wrap(sans),
            "Used for labels, counts, and UI text. Falls back to the system "
            "sans.",
        ))

        # ----- Open in Anki ----- #
        # Quick jumps to native Anki dialogs the standard Preferences tabs
        # don't surface. "Open Anki Preferences" is absent — the user is
        # already inside it.
        v.addWidget(_section_block(self._palette, "Open in Anki"))

        def _jump(fn, *args):
            def go():
                self._close_enclosing_dialog()
                try:
                    fn(*args)
                except Exception:
                    pass
            return go

        def _open_current_deck_opts():
            try:
                from aqt.deckoptions import display_options_for_deck_id
                from anki.decks import DeckId
                did = DeckId(int(mw.col.decks.get_current_id()))
                self._close_enclosing_dialog()
                display_options_for_deck_id(did)
            except Exception:
                pass

        def jump_item(label: str, hint: str, callback) -> QWidget:
            wrap = QWidget()
            box = QVBoxLayout(wrap)
            box.setContentsMargins(0, 4, 0, 6)
            box.setSpacing(2)
            btn = QPushButton(label + "  ↗")
            btn.setObjectName("jump")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(callback)
            box.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
            h = QLabel(hint)
            h.setProperty("role", "hint")
            h.setWordWrap(True)
            box.addWidget(h)
            return wrap

        v.addWidget(jump_item(
            "Open deck options",
            "Review settings, new-card limits, FSRS parameters for the "
            "current deck.",
            _open_current_deck_opts,
        ))
        v.addWidget(jump_item(
            "Manage note types",
            "Add, edit, and delete note types and card templates.",
            _jump(mw.onNoteTypes),
        ))
        v.addWidget(jump_item(
            "Open add-ons",
            "Manage installed add-ons.",
            _jump(mw.addonManager.onAddonsDialog),
        ))

        # The footer used to live inside the scrollable column, which meant
        # it floated wherever the content ended. Now it's a sibling of the
        # scroll area in the outer layout — pinned to the bottom of the
        # dialog, always visible, always reachable.
        v.addStretch(1)

        footer = QWidget()
        footer.setObjectName("footer")
        f = QVBoxLayout(footer)
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(0)
        rule = QFrame()
        rule.setProperty("role", "rule")
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet(f"QFrame {{ background: {self._palette['line']}; }}")
        rule.setFixedHeight(1)
        f.addWidget(rule)

        footer_inner = QWidget()
        fi = QHBoxLayout(footer_inner)
        fi.setContentsMargins(44, 16, 44, 16)
        fi.setSpacing(16)
        restore = QPushButton("Restore Anki Design defaults")
        restore.setObjectName("quiet")
        restore.setCursor(Qt.CursorShape.PointingHandCursor)
        restore.clicked.connect(self._restore_defaults)
        fi.addWidget(restore, 0, Qt.AlignmentFlag.AlignLeft)
        fi.addStretch(1)
        version = QLabel(f"Anki Design v{_human_version()}")
        version.setProperty("role", "wordmark")
        fi.addWidget(version, 0, Qt.AlignmentFlag.AlignVCenter)
        done = QPushButton("Done")
        done.setObjectName("primary")
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.clicked.connect(self._close_enclosing_dialog)
        fi.addWidget(done, 0, Qt.AlignmentFlag.AlignRight)
        f.addWidget(footer_inner)

        outer.addWidget(footer)

    # ----- builders ----- #
    def _radio_row(self, key: str, default: str,
                   options: List[Tuple[str, str]],
                   label: str, hint: Optional[str] = None) -> QWidget:
        """Horizontal radio group as a stacked field row. options is
        ``[(config_value, display_label), …]``."""
        group = QButtonGroup(self)
        # Keep a reference so the group isn't garbage-collected and the
        # exclusivity stops working — Qt notoriously drops un-referenced
        # QButtonGroups created inside methods.
        self._radio_groups.append(group)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(14)
        current = self._g(key, default)
        for value, opt_label in options:
            rb = QRadioButton(opt_label)
            rb.setChecked(current == value)
            group.addButton(rb)
            rb.toggled.connect(
                lambda checked, k=key, v=value: checked and self._set(k, v)
            )
            h.addWidget(rb)
        h.addStretch(1)
        return _field_row(label, box, hint)

    def _bg_row(self, key: str, label: str,
                presets: List[Tuple[str, str]], custom_default: str,
                hint: Optional[str] = None) -> QWidget:
        """Preset radios + a Custom radio with a colour swatch. Config value
        is "" for the theme default or a hex colour."""
        group = QButtonGroup(self)
        self._radio_groups.append(group)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(14)
        raw = self._g(key, "")
        current = (_colors.hex_ok(raw) if _colors else str(raw or "")) or ""
        preset_values = [p[0] for p in presets]
        is_custom = current not in preset_values

        def _choose(value: str) -> None:
            self._set(key, value)
            self._palette, _ = _resolve_palette()
            self._apply_styles()

        for value, opt_label in presets:
            rb = QRadioButton(opt_label)
            rb.setChecked(current == value)
            group.addButton(rb)
            rb.toggled.connect(
                lambda checked, val=value: checked and _choose(val)
            )
            h.addWidget(rb)

        custom_rb = QRadioButton("Custom")
        custom_rb.setChecked(is_custom)
        group.addButton(custom_rb)
        h.addWidget(custom_rb)

        swatch = ColorSwatch(
            current if is_custom else custom_default,
            lambda c: (custom_rb.setChecked(True), _choose(c)),
        )
        swatch.setVisible(is_custom)
        h.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)

        def _custom_toggled(checked: bool) -> None:
            swatch.setVisible(bool(checked))
            if checked:
                _choose(swatch.value())

        custom_rb.toggled.connect(_custom_toggled)
        h.addStretch(1)
        return _field_row(label, box, hint)

    def _font_wrap(self, picker: "FontPicker") -> QWidget:
        """A FontPicker + a quiet italic "optional" to its right; the tag
        hides as soon as the user picks (or types) a real value. Once
        there is a value, "optional" stops being information."""
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        h.addWidget(picker)
        tag = QLabel("optional")
        tag.setProperty("role", "tag")
        tag.setVisible(not picker.value())
        picker.currentTextChanged.connect(
            lambda _t: tag.setVisible(not picker.value())
        )
        h.addWidget(tag, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addStretch(1)
        return wrap

    # ----- handlers ----- #
    def _on_accent_changed(self, color: str) -> None:
        self._set("accent", color)
        try:
            self._accent_value.setText(color.upper())
        except Exception:
            pass
        self._apply_styles()

    def _theme_changed(self, value: str) -> None:
        self._set("theme", value)
        # Re-resolve the page palette so the tab itself reflects the new
        # choice immediately (Light ↔ Dark switch is live).
        self._palette, _ = _resolve_palette()
        self._apply_styles()

    def _restore_defaults(self) -> None:
        defaults = _config_defaults()
        self._cfg = defaults
        try:
            mw.addonManager.writeConfig(ADDON, defaults)
        except Exception:
            pass
        try:
            state = getattr(mw, "state", "")
            if state == "deckBrowser":
                mw.deckBrowser.refresh()
        except Exception:
            pass
        # Rebuild in-place so each widget reflects the reset state.
        try:
            for child in self.findChildren(QWidget):
                child.deleteLater()
            old_layout = self.layout()
            if old_layout is not None:
                QWidget().setLayout(old_layout)
        except Exception:
            pass
        self._palette, _ = _resolve_palette()
        self._radio_groups.clear()
        self._build()
        self._apply_styles()


# --------------------------------------------------------------------------- #
# Integration with Anki's Preferences dialog
# --------------------------------------------------------------------------- #
_PATCHED = False


def install_into_preferences() -> None:
    """Make every newly-opened Preferences dialog gain an "Anki Design" tab.

    Anki exposes ``Preferences.setupOptions`` as an explicit (legacy)
    extension point: the parent ``__init__`` calls it after ``setupUi`` has
    populated ``self.form.tabWidget``. We wrap it so the original (and any
    other add-on's wrap) still runs. Idempotent across re-imports.

    The wrap also hides Anki's native bottom chrome (the "Some settings
    will take effect…" warning + the Help/Close buttonBox) whenever the
    Anki Design tab is current — those controls don't apply to our settings
    and the page should own the whole dialog.
    """
    global _PATCHED
    if _PATCHED:
        return
    try:
        from aqt.preferences import Preferences
    except Exception:
        return
    original = getattr(Preferences, "setupOptions", None)

    def patched(self) -> None:
        if callable(original):
            try:
                original(self)
            except Exception:
                pass
        try:
            tw = self.form.tabWidget
        except Exception:
            return
        # Guard against being added twice if Anki ever re-runs setupOptions
        # on the same instance (a different add-on doing something odd).
        for i in range(tw.count()):
            if tw.tabText(i) == TAB_TITLE:
                return
        try:
            page = AnkiDesignSettingsPage(parent=tw)
            tw.addTab(page, TAB_TITLE)
        except Exception:
            return

        # Take over the bottom of the dialog when our tab is current.
        # Native widgets: the QDialogButtonBox (Help/Close) and the
        # "Some settings will take effect…" warning label. Stash the
        # references so we can show/hide them per tab.
        chrome: List[QWidget] = []
        for w in self.findChildren(QDialogButtonBox):
            chrome.append(w)
        for w in self.findChildren(QLabel):
            text = (w.text() or "").lower()
            if "take effect" in text or "restart" in text:
                chrome.append(w)

        def update_chrome(idx: int) -> None:
            try:
                is_ours = tw.tabText(idx) == TAB_TITLE
            except Exception:
                is_ours = False
            for cw in chrome:
                try:
                    cw.setVisible(not is_ours)
                except Exception:
                    pass

        try:
            tw.currentChanged.connect(update_chrome)
            update_chrome(tw.currentIndex())
        except Exception:
            pass

    try:
        Preferences.setupOptions = patched  # type: ignore[assignment]
        _PATCHED = True
    except Exception:
        pass


def _select_anki_design_tab(dlg: Any) -> None:
    try:
        tw = dlg.form.tabWidget
    except Exception:
        return
    for i in range(tw.count()):
        if tw.tabText(i) == TAB_TITLE:
            try:
                tw.setCurrentIndex(i)
            except Exception:
                pass
            return


def open_settings(parent: Any = None) -> None:
    """Open Anki's Preferences dialog with the Anki Design tab selected.

    Used by every Anki Design entry point (Cmd+, shortcut, sidebar cog,
    Tools menu, add-on manager Config button)."""
    install_into_preferences()
    dlg = None
    try:
        import aqt
        dlg = aqt.dialogs.open("Preferences", mw)
    except Exception:
        try:
            from aqt.preferences import Preferences
            dlg = Preferences(mw)
        except Exception:
            return
    if dlg is not None:
        _select_anki_design_tab(dlg)
