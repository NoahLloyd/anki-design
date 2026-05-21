"""BetterAnki — Add Card window redesign.

The native AddCards dialog (`aqt.addcards.AddCards`) is a QMainWindow with:
  - top row: notetype + deck chooser
  - middle: editor webview (Svelte app)
  - bottom: QDialogButtonBox (Add / Close / Help / History)

We rebuild all the Qt chrome around the editor in the same editorial style as
the rest of BetterAnki (settings dialog, deck home, sidebar). The editor
webview itself gets a CSS overlay in `web/addcard.css` (injected via
`webview_will_set_content` when the context is an Editor in ADD_CARDS mode).

Layout philosophy:
  - No "Add card" page-title — the window's title bar already says that.
  - Top: inline editorial sentence "New [Basic ▾] card in [Anki ▾]" — the
    chooser values are styled italic-serif links, opening the same picker
    as Anki's native chooser when clicked.
  - Bottom: a single primary Add-card button on the right with a
    hover-revealed shortcut pill; a Recent menu on the left.

Add-on compatibility: the original Add / History buttons keep their
handlers, shortcuts and `gui_hooks.add_cards_*` firing. We hide the stock
QDialogButtonBox and proxy clicks. The history menu is rebuilt under our
own button so it anchors to the visible button (the proxied click would
otherwise open the menu at the hidden button's position).
"""

from __future__ import annotations

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
    QMenu,
    QPalette,
    QPoint,
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
QDialog, QMainWindow, #ba-root, #ba-context, #ba-footer, #ba-fields-wrap {{
    background: {p['paper']};
    color: {p['ink']};
    font-family: {SANS};
}}

QFrame[role="rule"] {{
    background: {p['line']};
    max-height: 1px;
    min-height: 1px;
    border: 0;
}}

/* Inline context: "New  [Basic ▾]  card in  [Anki ▾]"
   Clean sans throughout for readability. Connective text is faint; the
   chooser values are weighted so they read as the clickable parts. */
#ba-context QLabel {{
    color: {p['ink_faint']};
    font-family: {SANS};
    font-size: 11.5pt;
    font-weight: 400;
    background: transparent;
}}
#modelArea QPushButton, #deckArea QPushButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: {p['ink']};
    font-family: {SANS};
    font-size: 11.5pt;
    font-weight: 600;
    padding: 1px 4px;
    min-height: 16px;
    text-decoration: none;
}}
#modelArea QPushButton:hover, #deckArea QPushButton:hover {{
    color: {accent};
    background: transparent;
}}
#modelArea QPushButton:focus, #deckArea QPushButton:focus {{
    outline: none;
    color: {accent};
}}
#modelArea QLabel, #deckArea QLabel {{
    background: transparent;
}}

/* Footer — Recent and other secondary buttons. */
#ba-footer QPushButton {{
    background: transparent;
    color: {p['ink_dim']};
    border: 1px solid {p['line2']};
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 11pt;
    font-weight: 500;
}}
#ba-footer QPushButton:hover {{
    color: {p['ink']};
    background: {p['hover']};
    border-color: {p['ink_faint']};
}}

/* Add card primary button — large pill with hover-revealed shortcut.
   Override the generic #ba-footer QPushButton selector by using both IDs
   so the cascade picks our accent fill. */
#ba-footer QPushButton#ba-add {{
    color: white;
    background: {accent};
    border: 1px solid {accent};
    border-radius: 22px;
    padding: 11px 22px;
    font-size: 12pt;
    font-weight: 600;
    min-height: 22px;
    min-width: 140px;
    text-align: center;
}}
#ba-footer QPushButton#ba-add:hover {{
    background: {accent};
    color: white;
    border-color: {accent};
}}
#ba-footer QPushButton#ba-add:pressed {{
    padding-top: 12px;
    padding-bottom: 10px;
}}

/* The shortcut chip is a child QLabel positioned in Python on hover. */
QLabel#ba-add-chip {{
    background: rgba(255, 255, 255, 0.22);
    color: white;
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 9.5pt;
    font-weight: 600;
    font-family: {SANS};
}}
"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _proxy_click(source: QPushButton, target: QPushButton) -> None:
    """Wire a new button to click the underlying native one (preserves
    shortcuts and gui_hooks)."""
    source.clicked.connect(target.click)


def _hrule(palette: Dict[str, str]) -> QFrame:
    f = QFrame()
    f.setProperty("role", "rule")
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"QFrame {{ background: {palette['line']}; }}")
    f.setFixedHeight(1)
    return f


# --------------------------------------------------------------------------- #
# Primary "Add card" button with hover-revealed shortcut pill.
# --------------------------------------------------------------------------- #
class _AddCardButton(QPushButton):
    """QPushButton with a small shortcut chip ("⌘↩") in its right edge that
    fades in on hover. The chip is a child QLabel positioned manually so it
    doesn't interfere with the button's text alignment."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Add card", parent)
        self.setObjectName("ba-add")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip = QLabel("⌘↩", self)
        self.chip.setObjectName("ba-add-chip")
        self.chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.chip.hide()

    def resizeEvent(self, e: Any) -> None:
        super().resizeEvent(e)
        try:
            cw = self.chip.sizeHint().width()
            ch = self.chip.sizeHint().height()
            self.chip.setGeometry(
                self.width() - cw - 12,
                (self.height() - ch) // 2,
                cw,
                ch,
            )
        except Exception:
            pass

    def enterEvent(self, e: Any) -> None:
        super().enterEvent(e)
        self.chip.show()

    def leaveEvent(self, e: Any) -> None:
        super().leaveEvent(e)
        self.chip.hide()


# --------------------------------------------------------------------------- #
# Rebuild AddCards chrome on init
# --------------------------------------------------------------------------- #
def _redress(addcards: AddCards) -> None:
    palette, _ = _resolve_palette()
    cfg = _config()
    accent = cfg.get("accent", "#6c8cff")

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

    # --- Context strip: "New [Basic ▾] card in [Anki ▾]" --- #
    context = QWidget()
    context.setObjectName("ba-context")
    ctx_layout = QHBoxLayout(context)
    ctx_layout.setContentsMargins(28, 14, 28, 12)
    ctx_layout.setSpacing(2)

    nt_area: QWidget = addcards.form.modelArea
    dk_area: QWidget = addcards.form.deckArea
    try:
        nt_area.setMinimumSize(QSize(0, 0))
        dk_area.setMinimumSize(QSize(0, 0))
    except Exception:
        pass

    # NotetypeChooser / DeckChooser auto-add a QLabel ("Type" / "Deck") — hide
    # it so the inline sentence has its own narration.
    def _hide_first_label(host: QWidget) -> None:
        try:
            for child in host.findChildren(QLabel):
                child.hide()
                break
        except Exception:
            pass
    _hide_first_label(nt_area)
    _hide_first_label(dk_area)

    # Style each chooser's QPushButton as an inline text link, and append a
    # tiny ▾ so it reads as openable.
    def _stylize(host: QWidget) -> None:
        try:
            for b in host.findChildren(QPushButton):
                b.setObjectName("ba-chooser")
                b.setFlat(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                # Append the chevron once. Anki later may update the label
                # via the chooser when the user picks a different type/deck
                # — we re-append on a timer so the chevron always tags along.
                txt = b.text()
                if not txt.endswith(" ▾"):
                    b.setText(f"{txt} ▾")
        except Exception:
            pass
    _stylize(nt_area)
    _stylize(dk_area)

    # Build the sentence. Each fragment is a thin QLabel; chooser pushbuttons
    # sit between them.
    pre = QLabel("New ")
    mid = QLabel(" card in ")
    post = QLabel("")

    ctx_layout.addWidget(pre)
    ctx_layout.addWidget(nt_area)
    ctx_layout.addWidget(mid)
    ctx_layout.addWidget(dk_area)
    ctx_layout.addWidget(post)
    ctx_layout.addStretch(1)

    root_layout.addWidget(context)
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
    fl = QHBoxLayout(footer)
    fl.setContentsMargins(28, 14, 28, 16)
    fl.setSpacing(10)

    recent_btn = QPushButton("Recent  ▾")
    recent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    recent_btn.setToolTip("Re-open a recently added note  (⌘⇧H)")
    add_btn = _AddCardButton()

    # Wire Add to the native add button so all Anki logic / shortcuts /
    # hooks still fire.
    try:
        _proxy_click(add_btn, addcards.addButton)
    except Exception:
        pass

    # Recent: we build our own QMenu anchored to OUR button (the proxied
    # click on the hidden historyButton would open the menu at its hidden
    # position). Reuses the same nid -> editHistory logic Anki ships.
    def _show_recent_menu() -> None:
        try:
            from anki.collection import SearchNode
            from anki.utils import html_to_text_line
            from aqt.utils import tr as ttr
            m = QMenu(addcards)
            history = list(getattr(addcards, "history", []))
            if not history:
                a = m.addAction("No recently added notes")
                a.setEnabled(False)
            else:
                for nid in history:
                    try:
                        if addcards.col.find_notes(
                            addcards.col.build_search_string(SearchNode(nid=nid))
                        ):
                            note = addcards.col.get_note(nid)
                            txt = html_to_text_line(", ".join(note.fields))
                            if len(txt) > 40:
                                txt = txt[:40] + "…"
                            try:
                                label = ttr.adding_edit(val=txt)
                            except Exception:
                                label = f"Edit: {txt}"
                            label = gui_hooks.addcards_will_add_history_entry(
                                label, note
                            )
                            label = label.replace("&", "&&")
                            a = m.addAction(label)
                            a.triggered.connect(
                                lambda _, nid=nid: addcards.editHistory(nid)
                            )
                        else:
                            try:
                                label = ttr.adding_note_deleted()
                            except Exception:
                                label = "(deleted)"
                            a = m.addAction(label)
                            a.setEnabled(False)
                    except Exception:
                        continue
            try:
                gui_hooks.add_cards_will_show_history_menu(addcards, m)
            except Exception:
                pass
            # Anchor at the bottom-left of our visible Recent button so the
            # menu drops down from it (not from the hidden native button).
            pos = recent_btn.mapToGlobal(QPoint(0, recent_btn.height()))
            m.exec(pos)
        except Exception as e:
            try:
                from aqt.utils import showWarning
                showWarning(f"Recent menu failed: {e}")
            except Exception:
                pass
    recent_btn.clicked.connect(_show_recent_menu)

    fl.addWidget(recent_btn)
    fl.addStretch(1)
    fl.addWidget(add_btn)
    root_layout.addWidget(footer)

    # Hide the stock buttonBox (its buttons stay alive for proxying).
    try:
        addcards.form.buttonBox.hide()
    except Exception:
        pass

    # Apply QSS and install our root as the central widget.
    try:
        addcards.setStyleSheet(_qss(palette, accent))
    except Exception:
        pass
    try:
        addcards.setCentralWidget(root)
    except Exception:
        pass

    # Mirror Recent's enabled state from the native history button. Cheap
    # 800ms tick (native is enabled after the first note is added).
    try:
        from aqt.qt import QTimer
        recent_btn.setEnabled(addcards.historyButton.isEnabled())
        t = QTimer(addcards)
        t.setInterval(800)
        def _tick() -> None:
            try:
                recent_btn.setEnabled(addcards.historyButton.isEnabled())
            except Exception:
                pass
            # Re-apply chevron in case Anki updated the chooser label text.
            _stylize(nt_area)
            _stylize(dk_area)
        t.timeout.connect(_tick)
        t.start()
        addcards._ba_history_timer = t  # keep ref
    except Exception:
        pass

    # Larger default window.
    try:
        if addcards.width() < 880 or addcards.height() < 720:
            addcards.resize(
                max(addcards.width(), 880), max(addcards.height(), 720)
            )
    except Exception:
        pass


def on_add_cards_did_init(addcards: AddCards) -> None:
    try:
        _redress(addcards)
    except Exception as e:
        import traceback
        try:
            print(
                f"[betteranki.addcard] redress failed: {e}\n"
                f"{traceback.format_exc()}",
                flush=True,
            )
        except Exception:
            pass


def register() -> None:
    gui_hooks.add_cards_did_init.append(on_add_cards_did_init)
