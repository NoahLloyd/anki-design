"""Anki Design — Add Card window redesign.

The native AddCards dialog (`aqt.addcards.AddCards`) is a QMainWindow with:
  - top row: notetype + deck chooser
  - middle: editor webview (Svelte app)
  - bottom: QDialogButtonBox (Add / Close / Help / History)

We rebuild all the Qt chrome around the editor in the same editorial style as
the rest of Anki Design (settings dialog, deck home, sidebar). The editor
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

/* Add card primary button — solid dark ink with the shortcut shown inline
   at low opacity. No animated chip; the chip overlaid the opaque pill and
   read as broken when it appeared. Compact corner radius (the previous
   pill shape felt out of place next to the rest of the editorial chrome). */
#ba-footer QPushButton#ba-add {{
    color: white;
    background: {p['ink']};
    border: 1px solid {p['ink']};
    border-radius: 8px;
    padding: 10px 18px;
    font-size: 11.5pt;
    font-weight: 600;
    min-height: 22px;
    min-width: 160px;
    text-align: center;
    letter-spacing: 0.2px;
}}
#ba-footer QPushButton#ba-add:hover {{
    background: {accent};
    color: white;
    border-color: {accent};
}}
#ba-footer QPushButton#ba-add:pressed {{
    padding-top: 11px;
    padding-bottom: 9px;
}}

/* Keyboard hint living next to the Add button. Quiet sans, mono-ish. */
QLabel#ba-add-shortcut {{
    color: {p['ink_faint']};
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 11pt;
    background: transparent;
    padding: 0 4px;
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
# Inline pickers for note type / deck (replace the StudyDeck popup window).
# --------------------------------------------------------------------------- #
def _wire_inline_notetype_picker(
    addcards: AddCards, btn: QPushButton
) -> None:
    """Replace the chooser's button click with a dropdown menu listing all
    note types. Picking one calls the chooser's setter — same effect as the
    original popup, no new window."""
    try:
        btn.clicked.disconnect()
    except Exception:
        pass

    def _open_menu() -> None:
        try:
            m = QMenu(addcards)
            current_id = int(addcards.notetype_chooser.selected_notetype_id)
            for nid in sorted(
                addcards.col.models.all_names_and_ids(),
                key=lambda n: n.name.lower(),
            ):
                act = m.addAction(nid.name)
                if int(nid.id) == current_id:
                    f = act.font()
                    f.setBold(True)
                    act.setFont(f)
                act.triggered.connect(
                    lambda _, i=int(nid.id):
                        setattr(addcards.notetype_chooser,
                                "selected_notetype_id", i)
                )
            m.addSeparator()
            edit = m.addAction("Manage note types…")
            edit.triggered.connect(
                lambda _: addcards.notetype_chooser.onEdit()
            )
            pos = btn.mapToGlobal(QPoint(0, btn.height()))
            m.exec(pos)
        except Exception:
            pass
    btn.clicked.connect(_open_menu)


def _wire_inline_deck_picker(addcards: AddCards, btn: QPushButton) -> None:
    """Same as above for decks. all_names_and_ids returns the hierarchical
    names (Parent::Child); show them as-is so the structure is visible."""
    try:
        btn.clicked.disconnect()
    except Exception:
        pass

    def _open_menu() -> None:
        try:
            m = QMenu(addcards)
            current_id = int(addcards.deck_chooser.selected_deck_id)
            decks = sorted(
                addcards.col.decks.all_names_and_ids(skip_empty_default=False),
                key=lambda d: d.name.lower(),
            )
            for dk in decks:
                # Skip filtered decks — the add window can't target them.
                try:
                    dd = addcards.col.decks.get(dk.id, default=False)
                    if dd and dd.get("dyn"):
                        continue
                except Exception:
                    pass
                act = m.addAction(dk.name)
                if int(dk.id) == current_id:
                    f = act.font()
                    f.setBold(True)
                    act.setFont(f)
                act.triggered.connect(
                    lambda _, i=int(dk.id):
                        setattr(addcards.deck_chooser,
                                "selected_deck_id", i)
                )
            m.addSeparator()
            new = m.addAction("New deck…")
            def _new_deck() -> None:
                try:
                    from aqt.operations.deck import add_deck_dialog
                    add_deck_dialog(parent=addcards)
                except Exception:
                    pass
            new.triggered.connect(lambda _: _new_deck())
            pos = btn.mapToGlobal(QPoint(0, btn.height()))
            m.exec(pos)
        except Exception:
            pass
    btn.clicked.connect(_open_menu)


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
    # tiny ▾ so it reads as openable. Also intercept the click to show a
    # dropdown menu in-page instead of opening Anki's StudyDeck popup.
    def _stylize(host: QWidget, kind: str) -> None:
        try:
            for b in host.findChildren(QPushButton):
                b.setObjectName("ba-chooser")
                b.setFlat(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                txt = b.text()
                if not txt.endswith(" ▾"):
                    b.setText(f"{txt} ▾")
                if kind == "notetype":
                    _wire_inline_notetype_picker(addcards, b)
                elif kind == "deck":
                    _wire_inline_deck_picker(addcards, b)
        except Exception:
            pass
    _stylize(nt_area, "notetype")
    _stylize(dk_area, "deck")

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
    # Add card: clean dark button, just "Add card". The keyboard shortcut
    # lives in a small dim label to its right (always visible, no animated
    # chip — the hover chip overlaid the opaque pill which read as broken).
    add_btn = QPushButton("Add card")
    add_btn.setObjectName("ba-add")
    add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    add_btn.setToolTip("Add card  (⌘↩)")
    add_shortcut = QLabel("⌘↩")
    add_shortcut.setObjectName("ba-add-shortcut")
    add_shortcut.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )

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
    fl.addWidget(add_shortcut)
    fl.addSpacing(8)
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
            _stylize(nt_area, "notetype")
            _stylize(dk_area, "deck")
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
                f"[anki-design.addcard] redress failed: {e}\n"
                f"{traceback.format_exc()}",
                flush=True,
            )
        except Exception:
            pass


def register() -> None:
    gui_hooks.add_cards_did_init.append(on_add_cards_did_init)
