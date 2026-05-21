"""Anki Design — embed the card Browser inside the main window as a "tab".

Mirrors `addcard_embed.py` exactly. The user wants Browse to behave like a
tab next to the sidebar instead of opening as a separate QMainWindow:

  - The sidebar's `ba:browse` pycmd calls `open_inline(mw)` (see
    `__init__.py`) instead of `mw.onBrowse()`.
  - `open_inline` constructs a Browser instance (we no-op `.show()` on
    a subclass so its standalone window never flashes on screen).
  - We grab its `centralWidget` and reparent it onto an overlay QFrame
    placed on top of `mw.form.centralwidget`, offset by the sidebar width
    so the sidebar rendered inside `mw.web` stays visible to the left.
  - The Browser window itself stays hidden (its widgets remain alive, so
    all menubar actions, shortcuts, and add-on hooks continue to work).
  - The overlay resizes with the main window via an installed event
    filter.
  - We register our instance with `aqt.dialogs` so any other code path
    that does `aqt.dialogs.open("Browser", ...)` finds our existing
    Browser and calls `reopen()` on it instead of opening a second one.

This is a first cut: the chrome is whatever Anki's stock browser uses.
Visual redesign is intentionally deferred — the user wants the layout
moved in as-is first.
"""

from __future__ import annotations

from typing import Any

from aqt import mw
from aqt.qt import (
    QApplication,
    QColor,
    QDockWidget,
    QEvent,
    QFrame,
    QKeySequence,
    QObject,
    QPalette,
    QShortcut,
    QSplitter,
    Qt,
    QTimer,
    QVBoxLayout,
)


SIDEBAR_W = 264  # px — matches --rf-side-w in web/theme.css; same as addcard_embed


def _palette_styles() -> str:
    """QSS for the overlay frame. The Browser's own internals carry their
    Qt-native styles — we just paint the wrapper paper-colored so the gap
    between sidebar and embed reads as one continuous page."""
    from . import addcard as _addcard
    palette, _ = _addcard._resolve_palette()
    return (
        "QFrame#ba-browse-embed { background: " + palette["paper"] + "; "
        "border-left: 1px solid " + palette["line"] + "; }"
    )


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


_state: dict = {"browser": None, "overlay": None, "filter": None}


def drop_curtain() -> None:
    """Tear down the anti-flash curtain. Safe to call multiple times."""
    c = _state.pop("curtain", None)
    if c is not None:
        try:
            c.deleteLater()
        except Exception:
            pass


def close_inline() -> None:
    """Tear down the embedded Browser and restore the deck browser.

    No-op if there is no embed currently open — callers (state-change
    monkey-patches, sidebar `decks` pycmd) can call this cheaply on
    every navigation event."""
    overlay = _state.get("overlay")
    br = _state.get("browser")
    flt = _state.get("filter")
    if overlay is None and br is None and flt is None:
        return

    # Clear state FIRST so anything that re-enters via a close callback
    # returns immediately.
    _state["browser"] = None
    _state["overlay"] = None
    _state["filter"] = None
    cw_palette = _state.pop("cw_palette", None)
    curtain = _state.pop("curtain", None)
    if curtain is not None:
        try:
            curtain.deleteLater()
        except Exception:
            pass

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
    if cw_palette is not None:
        try:
            mw.form.centralwidget.setPalette(cw_palette)
        except Exception:
            pass

    if br is not None:
        # Synchronous cleanup. Browser's `_closeWindow()` is the same
        # path its closeEvent ends up taking after the
        # call_after_note_saved roundtrip — we skip the roundtrip
        # because we don't have a webview-driven submit flow here.
        try:
            br._closeWindow()  # type: ignore[attr-defined]
        except Exception:
            try:
                br.close()
            except Exception:
                pass

    # Restore the sidebar's active tab.
    try:
        w = getattr(mw, "web", None)
        if w is not None:
            w.eval("window.__baSetActive && window.__baSetActive('decks');")
    except Exception:
        pass


def open_inline(parent_mw: Any = None) -> None:
    """Open the Browser embedded in the main window's content area.

    Falls back to the standalone Browser window if the embed setup
    fails for any reason."""
    parent_mw = parent_mw or mw
    if _state.get("overlay") is not None:
        # Already open — bring it forward.
        try:
            _state["overlay"].raise_()
        except Exception:
            pass
        return
    if _state.get("curtain") is not None:
        # A curtain is up — we're already mid-open from a previous call.
        return

    # --- Curtain ----------------------------------------------------
    from . import addcard as _addcard
    palette, _ = _addcard._resolve_palette()
    paper_qc = QColor(palette["paper"])
    cw = parent_mw.form.centralwidget

    curtain = QFrame(cw)
    curtain.setObjectName("ba-browse-curtain")
    curtain.setAutoFillBackground(True)
    _cu_pal = curtain.palette()
    _cu_pal.setColor(QPalette.ColorRole.Window, paper_qc)
    curtain.setPalette(_cu_pal)
    curtain.setStyleSheet(
        "QFrame#ba-browse-curtain { background: " + palette["paper"] + "; }"
    )
    curtain.setGeometry(SIDEBAR_W, 0, cw.width() - SIDEBAR_W, cw.height())
    curtain.show()
    curtain.raise_()
    _state["curtain"] = curtain
    try:
        curtain.repaint()
        QApplication.processEvents()
    except Exception:
        pass

    try:
        from aqt.browser import Browser
        # Anki's Browser.__init__ ends with `self.show()`, which would
        # flash the standalone QMainWindow on screen for one paint.
        # Subclassing to no-op `show()` keeps it invisible.
        class _EmbeddedBrowser(Browser):  # type: ignore[misc, valid-type]
            def show(self) -> None:  # noqa: D401 — Qt override
                pass
        br = _EmbeddedBrowser(parent_mw)
    except Exception:
        try:
            curtain.deleteLater()
        except Exception:
            pass
        _state["curtain"] = None
        try:
            parent_mw.onBrowse()
        except Exception:
            pass
        return

    try:
        # Register with the dialog manager so future
        # `aqt.dialogs.open("Browser", ...)` calls reopen() our instance
        # instead of creating a second Browser. _closeWindow() (called
        # from close_inline) calls dialogs.markClosed("Browser") which
        # tears this registration down.
        try:
            import aqt as _aqt
            _aqt.dialogs._dialogs["Browser"][1] = br  # type: ignore[index]
        except Exception:
            pass

        central = br.centralWidget()

        # Browser attaches its sidebar tree (decks / tags / saved searches)
        # as a QDockWidget directly to the QMainWindow, NOT inside
        # centralwidget. Discover every QDockWidget child so add-ons that
        # add their own docks are also brought along, and group them by
        # the dock area Browser placed them in.
        left_docks: list = []
        right_docks: list = []
        for dock in br.findChildren(QDockWidget):
            try:
                area = br.dockWidgetArea(dock)
            except Exception:
                area = Qt.DockWidgetArea.LeftDockWidgetArea
            inner = dock.widget()
            if inner is None:
                continue
            if area == Qt.DockWidgetArea.RightDockWidgetArea:
                right_docks.append(inner)
            else:
                # Treat anything that isn't explicitly right (left, top,
                # bottom, no-area) as left, matching the Browser's stock
                # placement of the sidebar.
                left_docks.append(inner)

        overlay = QFrame(parent_mw.form.centralwidget)
        overlay.setObjectName("ba-browse-embed")
        overlay.setAutoFillBackground(True)
        _ov_pal = overlay.palette()
        _ov_pal.setColor(QPalette.ColorRole.Window, paper_qc)
        overlay.setPalette(_ov_pal)
        overlay.setStyleSheet(_palette_styles())

        v = QVBoxLayout(overlay)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Layout: [left docks] | [centralwidget: search+table | editor] |
        # [right docks], wrapped in a QSplitter so each boundary stays
        # drag-resizable — matching the QDockWidget UX in native Browser.
        central.setParent(None)
        central.setWindowFlags(Qt.WindowType.Widget)

        if left_docks or right_docks:
            splitter = QSplitter(Qt.Orientation.Horizontal, overlay)
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(1)
            for inner in left_docks:
                inner.setParent(None)
                splitter.addWidget(inner)
            splitter.addWidget(central)
            for inner in right_docks:
                inner.setParent(None)
                splitter.addWidget(inner)
            # Stretch only the central pane; docks keep their preferred
            # widths. Initial sizes default to ~240px for each dock and
            # the rest to central.
            sizes: list[int] = []
            for i in range(splitter.count()):
                if splitter.widget(i) is central:
                    splitter.setStretchFactor(i, 1)
                    sizes.append(800)
                else:
                    splitter.setStretchFactor(i, 0)
                    sizes.append(240)
            splitter.setSizes(sizes)
            v.addWidget(splitter, 1)
            _state["splitter"] = splitter
        else:
            central.setParent(overlay)
            v.addWidget(central, 1)

        # Hide the original Browser QMainWindow.
        br.setVisible(False)

        # Tint mw.centralwidget paper so any Qt-painted gap is invisible.
        try:
            _state["cw_palette"] = QPalette(cw.palette())
            _cw_pal = cw.palette()
            _cw_pal.setColor(QPalette.ColorRole.Window, paper_qc)
            cw.setPalette(_cw_pal)
        except Exception:
            pass

        overlay.setGeometry(
            SIDEBAR_W, 0, cw.width() - SIDEBAR_W, cw.height()
        )
        overlay.show()
        overlay.raise_()
        try:
            curtain.raise_()
        except Exception:
            pass

        # Curtain drop: backstop on editor webview load + grace, hard cap.
        try:
            web = getattr(br.editor, "web", None) if br.editor else None
            if web is not None:
                page = web.page()
                if page is not None:
                    def _on_loaded(_ok: bool) -> None:
                        QTimer.singleShot(280, drop_curtain)
                    page.loadFinished.connect(_on_loaded)
        except Exception:
            pass
        QTimer.singleShot(900, drop_curtain)

        flt = _EmbedFilter(overlay)
        cw.installEventFilter(flt)

        # Esc closes the embed. Browser binds its own Esc inside
        # keyPressEvent on the QMainWindow, but our QMainWindow is
        # hidden so it never gets focus events.
        try:
            esc = QShortcut(QKeySequence("Escape"), overlay)
            esc.setAutoRepeat(False)
            esc.setContext(Qt.ShortcutContext.WindowShortcut)
            esc.activated.connect(close_inline)
        except Exception:
            pass

        _state["browser"] = br
        _state["overlay"] = overlay
        _state["filter"] = flt

        # Highlight "Browse" in the sidebar.
        try:
            w = getattr(parent_mw, "web", None)
            if w is not None:
                w.eval(
                    "window.__baSetActive && window.__baSetActive('browse');"
                )
        except Exception:
            pass
    except Exception as e:
        import traceback
        print(
            f"[anki-design.browse_embed] failed: {e}\n"
            f"{traceback.format_exc()}",
            flush=True,
        )
        try:
            close_inline()
        except Exception:
            pass
        try:
            br.show()
        except Exception:
            pass
