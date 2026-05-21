"""BetterAnki — embed AddCards inside the main window as a "tab".

Anki opens AddCards as a separate QMainWindow. The user wants it to behave
like a tab in the main window: the sidebar (rendered inside `mw.web` by the
deck browser HTML) stays visible, and the editor occupies the rest.

How this works:
  - We intercept the sidebar's `ba:add` pycmd in `__init__.py` to call
    `open_inline(mw)` instead of `mw.onAddCard()`.
  - `open_inline` constructs an AddCards instance (which fires our normal
    `_redress` via `add_cards_did_init`).
  - We grab its `centralWidget` and reparent it onto a thin overlay frame
    placed on top of `mw.form.centralwidget`, offset by the sidebar's
    width so the sidebar in mw.web stays visible through the gap.
  - The AddCards window itself is hidden (its widgets are alive, so all
    handlers, shortcuts, and add-on hooks continue to fire).
  - A small "← Back to decks" affordance in the top-left of the overlay
    closes AddCards and removes the overlay.
  - The overlay resizes with the main window via an installed event filter.

Caveats:
  - Sidebar width is hard-coded to 250px to match `web/sidebar.css`. If
    the sidebar changes width, this needs to be updated.
  - Qt widgets stacking above QWebEngineView on macOS Qt6 has been stable
    for a long time but is technically a known-fragile combination — if
    rendering glitches appear, fall back to the standard windowed flow.
"""

from __future__ import annotations

from typing import Any, Optional

from aqt import mw
from aqt.qt import (
    QEvent,
    QFrame,
    QHBoxLayout,
    QLabel,
    QObject,
    QPushButton,
    QSize,
    Qt,
    QVBoxLayout,
    QWidget,
)


SIDEBAR_W = 250  # px — matches web/sidebar.css .ba-sidebar width


def _palette_styles() -> str:
    """QSS for the embed wrapper and (importantly) re-applies the AddCards
    chrome QSS so the styles continue to match after we reparent. Without
    this the Add button comes through as a default white QPushButton."""
    from . import addcard as _addcard
    palette, _ = _addcard._resolve_palette()
    cfg = _addcard._config()
    accent = cfg.get("accent", "#6c8cff")
    chrome = _addcard._qss(palette, accent)
    return chrome + """
QFrame#ba-embed {
    background: """ + palette["paper"] + """;
    border-left: 1px solid """ + palette["line"] + """;
}
QPushButton#ba-back {
    background: transparent;
    color: """ + palette["ink_dim"] + """;
    border: 1px solid """ + palette["line2"] + """;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 10.5pt;
    font-weight: 500;
}
QPushButton#ba-back:hover {
    color: """ + palette["ink"] + """;
    background: """ + palette["hover"] + """;
    border-color: """ + palette["ink_faint"] + """;
}
"""


class _EmbedFilter(QObject):
    """Re-positions the embed overlay whenever the main window is resized."""

    def __init__(self, overlay: QFrame) -> None:
        super().__init__(overlay)
        self._overlay = overlay

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            try:
                cw = mw.form.centralwidget
                self._overlay.setGeometry(
                    SIDEBAR_W,
                    0,
                    cw.width() - SIDEBAR_W,
                    cw.height(),
                )
            except Exception:
                pass
        return False


_state: dict = {"addcards": None, "overlay": None, "filter": None}


def close_inline() -> None:
    """Tear down the embedded view and restore the deck browser."""
    overlay = _state.get("overlay")
    ac = _state.get("addcards")
    flt = _state.get("filter")
    if overlay is not None:
        try:
            if flt is not None:
                mw.form.centralwidget.removeEventFilter(flt)
        except Exception:
            pass
        try:
            overlay.deleteLater()
        except Exception:
            pass
    if ac is not None:
        try:
            ac.close()
        except Exception:
            pass
    _state["addcards"] = None
    _state["overlay"] = None
    _state["filter"] = None
    # Restore the sidebar's active tab.
    try:
        w = getattr(mw, "web", None)
        if w is not None:
            w.eval("window.__baSetActive && window.__baSetActive('decks');")
    except Exception:
        pass


def open_inline(parent_mw: Any = None) -> None:
    """Open AddCards embedded in the main window's content area.

    Falls back to the normal AddCards window if the embed setup fails for
    any reason."""
    parent_mw = parent_mw or mw
    if _state.get("overlay") is not None:
        # Already open — bring it forward.
        try:
            _state["overlay"].raise_()
        except Exception:
            pass
        return

    try:
        from aqt.addcards import AddCards
        ac = AddCards(parent_mw)
    except Exception:
        # Anki's normal flow as a last resort.
        try:
            parent_mw.onAddCard()
        except Exception:
            pass
        return

    try:
        central = ac.centralWidget()
        # Build an overlay frame holding the redressed AddCards centralWidget.
        # No back button — the sidebar already has a "Decks" item, and we
        # mark "Add" as active there so the user knows what tab they're on.
        overlay = QFrame(parent_mw.form.centralwidget)
        overlay.setObjectName("ba-embed")
        overlay.setStyleSheet(_palette_styles())

        v = QVBoxLayout(overlay)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Reparent the redressed AddCards centralWidget into the overlay.
        # Use Qt.Widget so it acts like a normal child, not a window.
        central.setParent(overlay)
        central.setWindowFlags(Qt.WindowType.Widget)
        v.addWidget(central, 1)

        # Hide the original AddCards QMainWindow chrome.
        ac.setVisible(False)

        # Position over the right of the central area.
        cw = parent_mw.form.centralwidget
        overlay.setGeometry(
            SIDEBAR_W, 0, cw.width() - SIDEBAR_W, cw.height()
        )
        overlay.show()
        overlay.raise_()

        # Resize the overlay with the main window.
        flt = _EmbedFilter(overlay)
        cw.installEventFilter(flt)

        _state["addcards"] = ac
        _state["overlay"] = overlay
        _state["filter"] = flt

        # Tell the sidebar (rendered inside mw.web) to highlight "Add"
        # instead of "Decks", so the active tab is correct visually.
        try:
            w = getattr(parent_mw, "web", None)
            if w is not None:
                w.eval("window.__baSetActive && window.__baSetActive('add');")
        except Exception:
            pass

        # If AddCards closes from inside (Esc, internal close button), tear
        # down the overlay too. We monkey-patch _close — the legitimate
        # cleanup path — to call our close_inline after.
        try:
            orig_close = ac._close
            def _wrapped_close(orig=orig_close) -> None:
                try:
                    orig()
                finally:
                    if _state.get("addcards") is ac:
                        close_inline()
            ac._close = _wrapped_close  # type: ignore[assignment]
        except Exception:
            pass
    except Exception as e:
        import traceback
        print(
            f"[betteranki.embed] failed: {e}\n{traceback.format_exc()}",
            flush=True,
        )
        # Best-effort cleanup, then fall back to the standalone window.
        try:
            close_inline()
        except Exception:
            pass
        try:
            ac.show()
        except Exception:
            pass
