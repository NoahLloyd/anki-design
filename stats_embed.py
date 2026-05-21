"""Anki Design — embed the Stats (NewDeckStats) dialog inside the main
window as a "tab".

Mirrors `addcard_embed.py` and `browse_embed.py`. Native Anki opens stats
as a separate QDialog window via `aqt.dialogs.open("NewDeckStats", mw)`.
We want it to behave like a tab next to the sidebar.

Stats is a QDialog (not a QMainWindow), so unlike Browser there's no
centralWidget / menubar / dockWidget split: everything the user sees is
attached to the dialog itself. The cleanest reparent is therefore the
whole dialog — set its window flags to `Widget` and add it to our
overlay's layout. All form widgets (the SvelteKit graphs webview, the
deck chooser, the Close / Save-PDF button row) plus anything add-ons
attach via `gui_hooks.stats_dialog_will_show` come along automatically.

Cleanup is one-shot: `NewDeckStats.reject()` does `self.form.web = None`
and double-calling it crashes, so we guard with a `cleaned` flag.

`Shift+T` (legacy `DeckStats`) is not embedded — it falls through to
the standalone window. The sidebar's Stats item always opens the modern
one.
"""

from __future__ import annotations

from typing import Any

from aqt import mw
from aqt.qt import (
    QApplication,
    QColor,
    QEvent,
    QFrame,
    QKeySequence,
    QObject,
    QPalette,
    QShortcut,
    Qt,
    QTimer,
    QVBoxLayout,
)


SIDEBAR_W = 264  # px — matches --rf-side-w in web/theme.css; same as the other embeds


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


_state: dict = {"stats": None, "overlay": None, "filter": None, "cleaned": False}


def drop_curtain() -> None:
    """Tear down the anti-flash curtain. Safe to call multiple times."""
    c = _state.pop("curtain", None)
    if c is not None:
        try:
            c.deleteLater()
        except Exception:
            pass


def _run_stats_cleanup(sd: Any) -> None:
    """Run NewDeckStats.reject() once. The method is not idempotent —
    it sets `self.form.web = None` and the second call would crash on
    NoneType.cleanup(). We track a single `cleaned` flag in `_state`."""
    if _state.get("cleaned"):
        return
    _state["cleaned"] = True
    try:
        sd.reject()
    except Exception:
        try:
            sd.close()
        except Exception:
            pass


def close_inline() -> None:
    """Tear down the embedded Stats dialog and restore the deck browser.

    No-op if there is no embed currently open."""
    overlay = _state.get("overlay")
    sd = _state.get("stats")
    flt = _state.get("filter")
    if overlay is None and sd is None and flt is None:
        return

    _state["stats"] = None
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

    if sd is not None:
        _run_stats_cleanup(sd)

    # Reset the cleaned flag for the next open.
    _state["cleaned"] = False

    # Restore the sidebar's active tab.
    try:
        w = getattr(mw, "web", None)
        if w is not None:
            w.eval("window.__baSetActive && window.__baSetActive('decks');")
    except Exception:
        pass


def open_inline(parent_mw: Any = None) -> None:
    """Open NewDeckStats embedded in the main window's content area.

    Falls back to the standalone window if anything goes wrong."""
    parent_mw = parent_mw or mw
    if _state.get("overlay") is not None:
        try:
            _state["overlay"].raise_()
        except Exception:
            pass
        return
    if _state.get("curtain") is not None:
        return

    # --- Curtain ----------------------------------------------------
    from . import addcard as _addcard
    palette, _ = _addcard._resolve_palette()
    paper_qc = QColor(palette["paper"])
    cw = parent_mw.form.centralwidget

    curtain = QFrame(cw)
    curtain.setObjectName("ba-stats-curtain")
    curtain.setAutoFillBackground(True)
    _cu_pal = curtain.palette()
    _cu_pal.setColor(QPalette.ColorRole.Window, paper_qc)
    curtain.setPalette(_cu_pal)
    curtain.setStyleSheet(
        "QFrame#ba-stats-curtain { background: " + palette["paper"] + "; }"
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
        from aqt.stats import NewDeckStats
        # NewDeckStats.__init__ ends with self.show() + self.activateWindow().
        # Subclass to no-op both so the standalone dialog never flashes.
        class _EmbeddedStats(NewDeckStats):  # type: ignore[misc, valid-type]
            def show(self) -> None:  # noqa: D401 — Qt override
                pass

            def activateWindow(self) -> None:  # noqa: D401 — Qt override
                pass

        sd = _EmbeddedStats(parent_mw)
    except Exception:
        try:
            curtain.deleteLater()
        except Exception:
            pass
        _state["curtain"] = None
        try:
            parent_mw.onStats()
        except Exception:
            pass
        return

    try:
        # Register with the dialog manager so other code paths that do
        # `aqt.dialogs.open("NewDeckStats", ...)` find our instance
        # instead of opening a second one. `reject()` (run on close)
        # calls `aqt.dialogs.markClosed("NewDeckStats")` which clears
        # the registration.
        try:
            import aqt as _aqt
            _aqt.dialogs._dialogs["NewDeckStats"][1] = sd  # type: ignore[index]
        except Exception:
            pass

        overlay = QFrame(parent_mw.form.centralwidget)
        overlay.setObjectName("ba-stats-embed")
        overlay.setAutoFillBackground(True)
        _ov_pal = overlay.palette()
        _ov_pal.setColor(QPalette.ColorRole.Window, paper_qc)
        overlay.setPalette(_ov_pal)
        overlay.setStyleSheet(
            "QFrame#ba-stats-embed { background: " + palette["paper"] + "; "
            "border-left: 1px solid " + palette["line"] + "; }"
        )

        v = QVBoxLayout(overlay)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Reparent the WHOLE dialog as an embedded widget. Everything the
        # form put on it (web, deck chooser, button box) and anything
        # add-ons attached via stats_dialog_will_show comes along — no
        # need to walk children individually.
        sd.setParent(overlay)
        sd.setWindowFlags(Qt.WindowType.Widget)
        sd.setVisible(True)
        v.addWidget(sd, 1)

        # Hijack the Close button (buttonBox.rejected normally routes to
        # NewDeckStats.reject) so clicking Close tears the embed down
        # rather than just closing the inner widget. `close_inline`
        # itself calls reject() during teardown so the cleanup chain
        # still runs.
        try:
            bb = sd.form.buttonBox
            try:
                bb.rejected.disconnect()
            except Exception:
                pass
            bb.rejected.connect(close_inline)
        except Exception:
            pass

        # Tint mw.centralwidget paper so any first-frame Qt gap is invisible.
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

        # Curtain drop: hook the stats webview's loadFinished + grace,
        # with a hard cap. NewDeckStats also calls
        # `web.hide_while_preserving_layout()` in __init__ which keeps
        # the web blank until the SvelteKit graphs page is ready, so the
        # curtain just covers the very first paint.
        try:
            web = getattr(sd.form, "web", None) if sd.form else None
            if web is not None:
                page = web.page()
                if page is not None:
                    def _on_loaded(_ok: bool) -> None:
                        QTimer.singleShot(280, drop_curtain)
                    page.loadFinished.connect(_on_loaded)
        except Exception:
            pass
        QTimer.singleShot(1500, drop_curtain)

        flt = _EmbedFilter(overlay)
        cw.installEventFilter(flt)

        # Esc closes the embed (NewDeckStats's add_close_shortcut(self)
        # binds Esc to self.close() inside the dialog, but the dialog as
        # an embedded widget no longer receives the same focus chain).
        try:
            esc = QShortcut(QKeySequence("Escape"), overlay)
            esc.setAutoRepeat(False)
            esc.setContext(Qt.ShortcutContext.WindowShortcut)
            esc.activated.connect(close_inline)
        except Exception:
            pass

        _state["stats"] = sd
        _state["overlay"] = overlay
        _state["filter"] = flt
        _state["cleaned"] = False

        # Highlight "Stats" in the sidebar.
        try:
            w = getattr(parent_mw, "web", None)
            if w is not None:
                w.eval(
                    "window.__baSetActive && window.__baSetActive('stats');"
                )
        except Exception:
            pass
    except Exception as e:
        import traceback
        print(
            f"[anki-design.stats_embed] failed: {e}\n"
            f"{traceback.format_exc()}",
            flush=True,
        )
        try:
            close_inline()
        except Exception:
            pass
        try:
            sd.show()
        except Exception:
            pass
