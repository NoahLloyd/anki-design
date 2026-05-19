"""BetterAnki — a from-scratch Anki UI redesign.

  * override Anki's design tokens so its own components recolor coherently
  * redesign the deck homepage (card rows, count chips, integrated actions)
  * restyle the top toolbar
  * hide Anki's native bottom strip on the deck list (its actions are moved
    into the page); keep it everywhere else (reviewer answer buttons, etc.)
  * review-activity heatmap on the deck list
  * reviewer progress bar

Everything visible is driven by web/ assets and config so iterating on the
look is just editing CSS / config. In a `make dev` worktree, web/*.css and
web/*.js hot-reload live; Python changes still need an Anki restart.
"""

import datetime
import os
import threading
import time
from typing import Any, Dict, Optional

from aqt import gui_hooks, mw
from aqt.deckbrowser import DeckBrowser, DeckBrowserContent
from aqt.overview import Overview
from aqt.reviewer import Reviewer
from aqt.webview import WebContent

# Optional bits — guarded so a renamed API can never break the whole add-on.
try:
    from aqt.toolbar import Toolbar as _ToolbarCtx
except Exception:
    _ToolbarCtx = None
try:
    from aqt.toolbar import BottomBar as _BottomCtx
except Exception:
    _BottomCtx = None
try:
    from aqt.qt import QTimer
except Exception:
    QTimer = None

ADDON_DIR = os.path.basename(os.path.dirname(__file__))
WEB = f"/_addons/{ADDON_DIR}/web"

# Let Anki serve our static files to the embedded web views.
mw.addonManager.setWebExports(__name__, r"web/.*")


def _config() -> Dict[str, Any]:
    return mw.addonManager.getConfig(__name__) or {}


def _is(context: Any, cls: Any) -> bool:
    return bool(cls) and isinstance(context, cls)


# --------------------------------------------------------------------------- #
# Theme + asset injection
# --------------------------------------------------------------------------- #
def on_webview_will_set_content(web_content: WebContent, context: Optional[Any]) -> None:
    themed = (
        isinstance(context, (DeckBrowser, Overview, Reviewer))
        or _is(context, _ToolbarCtx)
        or _is(context, _BottomCtx)
    )
    if not themed:
        return

    accent = _config().get("accent", "#6c8cff")
    # tokens.css derives --accent from --rf-accent; inject the latter here.
    web_content.head += (
        f"<style>:root,.night-mode,body{{--rf-accent:{accent};}}</style>"
    )
    web_content.css.append(f"{WEB}/tokens.css")

    if isinstance(context, (DeckBrowser, Overview)):
        web_content.css.append(f"{WEB}/theme.css")
    if isinstance(context, DeckBrowser):
        web_content.css.append(f"{WEB}/heatmap.css")
    if _is(context, _ToolbarCtx):
        web_content.css.append(f"{WEB}/toolbar.css")
    if isinstance(context, Reviewer) and _config().get("show_progress", True):
        web_content.css.append(f"{WEB}/reviewer.css")
        web_content.js.append(f"{WEB}/reviewer.js")


# --------------------------------------------------------------------------- #
# Integrated action buttons (replace Anki's native bottom strip on the deck
# list). These pycmds are handled by the deck browser's own link handler.
# --------------------------------------------------------------------------- #
def _actions_html() -> str:
    return (
        '<div class="ba-actions">'
        "<button class=\"primary\" onclick=\"pycmd('create')\">+ New Deck</button>"
        "<button onclick=\"pycmd('shared')\">Get Shared</button>"
        "<button onclick=\"pycmd('import')\">Import File</button>"
        "</div>"
    )


# --------------------------------------------------------------------------- #
# Heatmap
# --------------------------------------------------------------------------- #
def _rollover_hour() -> int:
    try:
        return int(mw.col.get_preferences().scheduling.rollover)
    except Exception:
        try:
            return int(mw.col.conf.get("rollover", 4))
        except Exception:
            return 4


def _day_shift_seconds() -> int:
    """Offset so a `revlog.id` (ms, UTC) divided by a day lands on the
    correct local day, accounting for the user's day rollover hour."""
    if time.localtime().tm_isdst and time.daylight:
        offset = -time.altzone
    else:
        offset = -time.timezone
    return offset - _rollover_hour() * 3600


def _counts_by_day() -> Dict[int, int]:
    shift = _day_shift_seconds()
    rows = mw.col.db.all(
        "select cast((id/1000 + ?) / 86400 as int) as d, count() "
        "from revlog group by d",
        shift,
    )
    return {int(d): int(n) for d, n in rows}


def build_heatmap_html(weeks: int = 53) -> str:
    col = mw.col
    if not col:
        return ""

    counts = _counts_by_day()
    shift = _day_shift_seconds()
    today_idx = int((time.time() + shift) // 86400)
    today_date = datetime.date.today()

    def date_for(idx: int) -> datetime.date:
        return today_date - datetime.timedelta(days=today_idx - idx)

    def dow(idx: int) -> int:  # 0 = Sunday .. 6 = Saturday
        return (idx + 4) % 7

    start_idx = today_idx - (weeks * 7 - 1)
    grid_start = start_idx - dow(start_idx)  # back up to a Sunday

    nonzero = [c for c in counts.values() if c > 0]
    peak = max(nonzero) if nonzero else 1

    def level(n: int) -> int:
        if n <= 0:
            return 0
        return min(4, 1 + int(n * 4 / (peak + 0.0001)))

    cells = []
    columns = (today_idx - grid_start) // 7 + 1
    for w in range(columns):
        col_cells = []
        for r in range(7):
            idx = grid_start + w * 7 + r
            if idx < start_idx or idx > today_idx:
                col_cells.append('<div class="rf-hm-cell rf-hm-empty"></div>')
                continue
            n = counts.get(idx, 0)
            d = date_for(idx)
            tip = f"{d.isoformat()} — {n} review{'s' if n != 1 else ''}"
            col_cells.append(
                f'<div class="rf-hm-cell rf-hm-l{level(n)}" title="{tip}"></div>'
            )
        cells.append('<div class="rf-hm-col">' + "".join(col_cells) + "</div>")

    total = sum(counts.values())
    streak = 0
    probe = today_idx if counts.get(today_idx, 0) > 0 else today_idx - 1
    while counts.get(probe, 0) > 0:
        streak += 1
        probe -= 1
    today_n = counts.get(today_idx, 0)

    legend = "".join(f'<div class="rf-hm-cell rf-hm-l{i}"></div>' for i in range(5))

    return f"""
    <div class="rf-heatmap">
      <div class="rf-hm-head">
        <span class="rf-hm-title">Review activity</span>
        <span class="rf-hm-stats">
          <b>{today_n}</b> today &nbsp;·&nbsp;
          <b>{streak}</b> day streak &nbsp;·&nbsp;
          <b>{total}</b> total
        </span>
      </div>
      <div class="rf-hm-grid">{''.join(cells)}</div>
      <div class="rf-hm-foot">
        <span>Less</span>{legend}<span>More</span>
      </div>
    </div>
    """


def on_deck_browser_will_render_content(
    deck_browser: DeckBrowser, content: DeckBrowserContent
) -> None:
    cfg = _config()
    heatmap = ""
    if cfg.get("show_heatmap", True):
        try:
            heatmap = build_heatmap_html(int(cfg.get("heatmap_weeks", 53)))
        except Exception as e:
            heatmap = f"<!-- betteranki heatmap error: {e} -->"
    # order: integrated actions, then Anki's #studiedToday, then heatmap
    content.stats = _actions_html() + content.stats + heatmap


# --------------------------------------------------------------------------- #
# Native bottom strip: hide on the deck list (actions moved into the page),
# keep it everywhere else so the reviewer answer buttons / overview "Study"
# button are untouched.
# --------------------------------------------------------------------------- #
def _set_bottom_visible(visible: bool) -> None:
    bw = getattr(mw, "bottomWeb", None)
    if bw is None:
        return
    try:
        bw.setVisible(visible)
    except Exception:
        pass


def _update_title() -> None:
    try:
        mw.setWindowTitle("Anki")
    except Exception:
        pass


def on_state_did_change(new_state: str, old_state: str) -> None:
    _set_bottom_visible(new_state != "deckBrowser")
    _update_title()


def on_deck_browser_did_render(deck_browser: DeckBrowser) -> None:
    # The deck browser re-shows the bottom strip when it draws; hide it again
    # on the next event-loop tick so our in-page actions stand alone.
    if QTimer is not None:
        QTimer.singleShot(0, lambda: _set_bottom_visible(False))
    else:
        _set_bottom_visible(False)


# --------------------------------------------------------------------------- #
# Reviewer progress bar
# --------------------------------------------------------------------------- #
_session = {"total": 0}


def _remaining() -> int:
    try:
        return int(sum(mw.col.sched.counts()))
    except Exception:
        return 0


def _push_progress() -> None:
    if not _config().get("show_progress", True):
        return
    rem = _remaining()
    if rem > _session["total"]:
        _session["total"] = rem
    total = _session["total"] or 1
    done = max(0, total - rem)
    pct = min(100, int(done * 100 / total))
    try:
        mw.reviewer.web.eval(
            f"window.__reforgeProgress && window.__reforgeProgress({pct},{done},{rem});"
        )
    except Exception:
        pass


def on_show_question(card) -> None:
    _push_progress()


def on_show_answer(card) -> None:
    _push_progress()


def on_reviewer_will_end() -> None:
    _session["total"] = 0


# --------------------------------------------------------------------------- #
# Register hooks
# --------------------------------------------------------------------------- #
gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
gui_hooks.deck_browser_will_render_content.append(on_deck_browser_will_render_content)
gui_hooks.deck_browser_did_render.append(on_deck_browser_did_render)
gui_hooks.state_did_change.append(on_state_did_change)
gui_hooks.reviewer_did_show_question.append(on_show_question)
gui_hooks.reviewer_did_show_answer.append(on_show_answer)
gui_hooks.reviewer_will_end.append(on_reviewer_will_end)


# --------------------------------------------------------------------------- #
# Dev hot-reload — web/ assets only, enabled by `make dev` (a .devmode file).
#
# Hard rule: the watcher must NEVER touch Anki during shutdown. Refreshing a
# view there fires Anki's own signals after the collection is gone, and those
# errors surface OUTSIDE our try/except (in Anki's slots) -> the "may be
# caused by an add-on" dialog that blocks quitting. So the thread is tied to
# the profile lifecycle: it starts only once the profile is open and is
# stopped on profile_will_close, before any teardown.
#
# Never ships: build.py and .gitignore exclude .devmode, so end users (who
# install the zip, no .devmode) never start the watcher thread.
# --------------------------------------------------------------------------- #
ADDON_SRC = os.path.dirname(os.path.abspath(__file__))

_dev_stop = threading.Event()
_dev_thread: Optional[threading.Thread] = None


def _dev_active() -> bool:
    return os.path.exists(os.path.join(ADDON_SRC, ".devmode"))


def _dev_reload_views() -> None:
    """Runs on the Qt main thread. Bails unless a collection is open and we
    are not shutting down. Cache-busts our stylesheets in every webview
    (instant, no flicker), then re-renders the current screen."""
    if _dev_stop.is_set() or not _dev_active():
        return
    if mw is None or getattr(mw, "col", None) is None:
        return  # no profile / mid-shutdown — never refresh here
    state = getattr(mw, "state", None)
    if state not in ("deckBrowser", "overview", "review"):
        return

    bust = (
        "(function(){var v=Date.now();"
        "var ls=document.getElementsByTagName('link');"
        "for(var i=0;i<ls.length;i++){var l=ls[i];"
        "if(l.rel==='stylesheet'&&l.href.indexOf('/_addons/%s/web/')!==-1)"
        "{l.href=l.href.split('?')[0]+'?v='+v;}}})();" % ADDON_DIR
    )
    views = []
    for attr in ("web", "bottomWeb"):
        w = getattr(mw, attr, None)
        if w is not None:
            views.append(w)
    rv = getattr(mw, "reviewer", None)
    if rv is not None:
        if getattr(rv, "web", None) is not None:
            views.append(rv.web)
        bottom = getattr(rv, "bottom", None)
        if bottom is not None and getattr(bottom, "web", None) is not None:
            views.append(bottom.web)
    for w in views:
        try:
            w.eval(bust)
        except Exception:
            pass

    try:
        if state == "deckBrowser":
            mw.deckBrowser.refresh()
        elif state == "overview":
            mw.overview.refresh()
        elif state == "review":
            try:
                with open(os.path.join(ADDON_SRC, "web", "reviewer.js")) as fh:
                    mw.reviewer.web.eval(fh.read())
            except Exception:
                pass
            _push_progress()
    except Exception:
        pass


def _dev_watch() -> None:
    web_dir = os.path.join(ADDON_SRC, "web")
    seen: Dict[str, float] = {}
    primed = False
    # _dev_stop.wait() doubles as the sleep AND an instant exit signal.
    while not _dev_stop.is_set() and _dev_active():
        changed = False
        try:
            for name in os.listdir(web_dir):
                path = os.path.join(web_dir, name)
                if not os.path.isfile(path):
                    continue
                mtime = os.path.getmtime(path)
                if seen.get(path) != mtime:
                    if primed:
                        changed = True
                    seen[path] = mtime
        except Exception:
            pass
        primed = True
        if changed and not _dev_stop.is_set():
            try:
                mw.taskman.run_on_main(_dev_reload_views)
            except Exception:
                pass
        _dev_stop.wait(0.5)


def _dev_start() -> None:
    """Start the watcher once a profile is open. Idempotent."""
    global _dev_thread
    if not _dev_active():
        return
    if _dev_thread is not None and _dev_thread.is_alive():
        return
    _dev_stop.clear()
    _dev_thread = threading.Thread(
        target=_dev_watch, name="betteranki-devwatch", daemon=True
    )
    _dev_thread.start()


def _dev_shutdown() -> None:
    """Stop the watcher before Anki tears anything down."""
    _dev_stop.set()


gui_hooks.profile_did_open.append(_dev_start)
gui_hooks.main_window_did_init.append(_dev_start)
gui_hooks.profile_will_close.append(_dev_shutdown)
