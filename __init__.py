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
import html
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
# NB: the webview's `context` for the bars is the *wrapper* passed to
# stdHtml() — TopToolbar / BottomToolbar — NOT Toolbar / BottomBar. Matching
# the wrong class is why the toolbar was never themed.
try:
    from aqt.toolbar import TopToolbar as _ToolbarCtx
except Exception:
    _ToolbarCtx = None
try:
    from aqt.toolbar import BottomToolbar as _BottomCtx
except Exception:
    _BottomCtx = None
# The reviewer's bottom strip ships as a separate context — `ReviewerBottomBar`,
# NOT the generic `BottomToolbar` used elsewhere (e.g., deck-browser bottom).
# We need both so theme + reviewer-bottom.css both apply.
try:
    from aqt.reviewer import ReviewerBottomBar as _ReviewerBottomCtx
except Exception:
    _ReviewerBottomCtx = None
try:
    from aqt.deckbrowser import DeckBrowserBottomBar as _DeckBrowserBottomCtx
except Exception:
    _DeckBrowserBottomCtx = None
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
        or _is(context, _ReviewerBottomCtx)
        or _is(context, _DeckBrowserBottomCtx)
    )
    if not themed:
        return

    cfg = _config()
    accent = cfg.get("accent", "#6c8cff")
    theme_pref = cfg.get("theme", "system")  # "system" | "light" | "dark"
    # User-supplied display fonts are prepended to the existing stacks.
    serif_user = (cfg.get("font_serif") or "").strip()
    sans_user = (cfg.get("font_sans") or "").strip()
    serif_decl = f"--rf-serif:{serif_user}, ui-serif, 'New York', Georgia, serif;" \
        if serif_user else ""
    sans_decl = f"--rf-sans:{sans_user}, ui-sans-serif, -apple-system, system-ui, sans-serif;" \
        if sans_user else ""
    # tokens.css derives --accent from --rf-accent; inject the latter here.
    # `data-rf-theme` on <html> forces light/dark over the system @media.
    extras = ""
    if theme_pref in ("light", "dark"):
        extras = (
            f"<script>document.documentElement.dataset.rfTheme="
            f"'{theme_pref}';</script>"
        )
    web_content.head += (
        f"<style>:root,.night-mode,body{{"
        f"--rf-accent:{accent};{serif_decl}{sans_decl}}}</style>"
        + extras
    )
    web_content.css.append(f"{WEB}/tokens.css")

    if isinstance(context, (DeckBrowser, Overview, Reviewer)):
        # theme.css defines the --rf-* design tokens used by reviewer.css
        # (back button, answer divider, progress strip), so the reviewer
        # needs it too — otherwise it falls back to hardcoded dark colors
        # even in light mode. The heavy homepage layout in theme.css is
        # scoped to .ba-home / .ba-over and won't touch the reviewer.
        web_content.css.append(f"{WEB}/theme.css")
    if isinstance(context, DeckBrowser):
        web_content.css.append(f"{WEB}/heatmap.css")
        web_content.js.append(f"{WEB}/heatmap.js")
        # Tag the deck browser's <center> so theme.css can scope the heavy
        # homepage layout to it alone — the Overview shares this stylesheet
        # and must keep its own simple layout (just palette + type).
        # Add `ba-single` when there's only one top-level deck so the hero
        # composition can take over from the (now-hidden) table.
        try:
            klass = "ba-home" + (
                " ba-single" if _top_decks_count() == 1 else " ba-multi"
            )
            web_content.body = web_content.body.replace(
                "<center>", f'<center class="{klass}">', 1
            )
        except Exception:
            pass
    if isinstance(context, Overview):
        # Scope Overview's <center> so theme.css can give it its own layout.
        try:
            web_content.body = web_content.body.replace(
                "<center>", '<center class="ba-over">', 1
            )
        except Exception:
            pass
    # Sidebar nav — deck browser + overview only. The reviewer gets full
    # focus (no sidebar) so the card area isn't competing with chrome.
    if cfg.get("sidebar_nav", True) and isinstance(
        context, (DeckBrowser, Overview)
    ):
        web_content.css.append(f"{WEB}/sidebar.css")
        web_content.js.append(f"{WEB}/sidebar.js")
        # Embed the standing data in <head> as a global so sidebar.js reads
        # it synchronously on its first run.
        try:
            import json as _json
            payload = _build_standing_payload()
            web_content.head += (
                "<script>window.__baStandingData = "
                + _json.dumps(payload) + ";</script>"
            )
        except Exception:
            pass
    # Floating Settings cog — only when the sidebar is OFF on the homepage.
    no_side = not cfg.get("sidebar_nav", True)
    if no_side and isinstance(context, (DeckBrowser, Overview)):
        web_content.css.append(f"{WEB}/sidebar.css")  # for .ba-cog
        web_content.body = (
            '<button class="ba-cog" onclick="pycmd(\'ba:settings\')" '
            'title="BetterAnki settings">⚙</button>' + web_content.body
        )
    # Reviewer header — deck name (with built-in back link) on the left,
    # position counter on the right. Replaces the floating "Decks" button.
    # We also append the ease selector so we can drop the bottom-toolbar
    # webview entirely. Idempotent: if the previous webview content
    # already has our header/ease (e.g., Anki recycles the body for the
    # answer-state render), we skip to avoid stacking duplicates.
    if isinstance(context, Reviewer) and "ba-rv-head" not in web_content.body:
        try:
            head_html = _reviewer_header_html()
        except Exception:
            head_html = ""
        try:
            ease_html = _reviewer_ease_html()
        except Exception:
            ease_html = ""
        web_content.body = head_html + web_content.body + ease_html
    if _is(context, _ToolbarCtx):
        web_content.css.append(f"{WEB}/toolbar.css")
    # Reviewer's bottom bar (Show Answer, Edit, More, answer buttons) lives
    # in `ReviewerBottomBar` — NOT the generic BottomToolbar (that's the
    # deck-browser/overview strip we hide). Style only the reviewer bottom.
    if _is(context, _ReviewerBottomCtx):
        web_content.css.append(f"{WEB}/reviewer-bottom.css")
    # reviewer.css always loads on the reviewer — it owns the back button,
    # answer divider, card chrome, AND the progress strip styling. Gating it
    # on show_progress used to break the back button + card colors when the
    # progress bar was off. show_progress only controls the JS that injects
    # the progress bar element.
    if isinstance(context, Reviewer):
        web_content.css.append(f"{WEB}/reviewer.css")
        if cfg.get("show_progress", True):
            web_content.js.append(f"{WEB}/reviewer.js")


# --------------------------------------------------------------------------- #
# Integrated action buttons (replace Anki's native bottom strip on the deck
# list). These pycmds are handled by the deck browser's own link handler.
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Standing computation — used by the sidebar and the single-deck hero.
# --------------------------------------------------------------------------- #


def _standing() -> Dict[str, Any]:
    counts = _counts_by_day()
    shift = _day_shift_seconds()
    today_idx = int((time.time() + shift) // 86400)
    streak = 0
    probe = today_idx if counts.get(today_idx, 0) > 0 else today_idx - 1
    while counts.get(probe, 0) > 0:
        streak += 1
        probe -= 1
    out: Dict[str, Any] = {
        "today": counts.get(today_idx, 0),
        "total": sum(counts.values()),
        "streak": streak,
        "new": None,
        "learn": None,
        "due": None,
    }
    try:
        tree = mw.col.sched.deck_due_tree()
        n = lr = rv = 0
        for c in getattr(tree, "children", []):
            n += int(getattr(c, "new_count", 0) or 0)
            lr += int(getattr(c, "learn_count", 0) or 0)
            rv += int(getattr(c, "review_count", 0) or 0)
        out["new"], out["learn"], out["due"] = n, lr, rv
    except Exception:
        pass
    return out




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


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


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

    # Render the full history so you can scroll back through past years, but
    # never fewer than `weeks` columns so a fresh collection still looks full.
    floor_idx = today_idx - (weeks * 7 - 1)
    earliest = min(counts) if counts else floor_idx
    start_idx = min(earliest, floor_idx)
    grid_start = start_idx - dow(start_idx)  # back up to a Sunday

    nonzero = [c for c in counts.values() if c > 0]
    peak = max(nonzero) if nonzero else 1

    def level(n: int) -> int:
        if n <= 0:
            return 0
        return min(4, 1 + int(n * 4 / (peak + 0.0001)))

    columns = (today_idx - grid_start) // 7 + 1

    cells = []
    month_spans = []  # [label, span_in_columns]
    prev_month = prev_year = None
    for w in range(columns):
        cd = date_for(grid_start + w * 7)  # the column's Sunday
        if cd.month != prev_month:
            year = f" {cd.year}" if cd.year != prev_year else ""
            month_spans.append([_MONTHS[cd.month - 1] + year, 1])
            prev_month, prev_year = cd.month, cd.year
        else:
            month_spans[-1][1] += 1

        col_cells = []
        for r in range(7):
            idx = grid_start + w * 7 + r
            if idx < start_idx or idx > today_idx:
                col_cells.append('<div class="rf-hm-cell rf-hm-empty"></div>')
                continue
            n = counts.get(idx, 0)
            d = date_for(idx)
            human = f"{_WEEKDAYS[dow(idx)]}, {d.day} {_MONTHS[d.month - 1]} {d.year}"
            if idx == today_idx:
                rel = "Today"
            elif idx == today_idx - 1:
                rel = "Yesterday"
            else:
                rel = ""
            is_peak = "1" if (n == peak and peak >= 8) else "0"
            col_cells.append(
                f'<div class="rf-hm-cell rf-hm-l{level(n)}" '
                f'data-count="{n}" data-human="{human}" '
                f'data-rel="{rel}" data-peak="{is_peak}"></div>'
            )
        cells.append('<div class="rf-hm-col">' + "".join(col_cells) + "</div>")

    # Only label months wide enough to fit the text without colliding.
    months_html = "".join(
        f'<span class="rf-hm-mon" style="width:{span * 14}px">'
        f'{label if span >= 4 else ""}</span>'
        for label, span in month_spans
    )
    weekdays_html = "".join(
        f'<span class="rf-hm-wd">{_WEEKDAYS[i] if i in (1, 3, 5) else ""}</span>'
        for i in range(7)
    )

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
      <div class="rf-hm-body">
        <div class="rf-hm-wds">
          <span class="rf-hm-mon-spacer"></span>
          {weekdays_html}
        </div>
        <div class="rf-hm-scroll">
          <div class="rf-hm-months">{months_html}</div>
          <div class="rf-hm-grid">{''.join(cells)}</div>
        </div>
      </div>
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
    # Single-deck hero replaces the table (CSS hides the table in this mode).
    hero = ""
    try:
        if _top_decks_count() == 1:
            hero = _single_deck_hero()
    except Exception:
        pass
    # Wrap the streak / today / all-time stats together with the heatmap so
    # they read as a single integrated "practice record" band on the page.
    try:
        practice_head = _practice_header_html()
    except Exception:
        practice_head = ""
    practice = (
        f'<section class="ba-practice">{practice_head}{heatmap}</section>'
        if heatmap else ""
    )
    content.stats = hero + content.stats + practice


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
    # Anki sets "<profile> - Anki" late in profile load; collapse it to a
    # clean "Anki" (we re-assert it after render so ours wins that race).
    try:
        mw.setWindowTitle("Anki")
    except Exception:
        pass


def _mark_toolbar_state(state: Optional[str] = None) -> None:
    """Tag the toolbar <body> with the current screen so toolbar.css can
    highlight the active section (e.g. Decks on the deck list). The toolbar
    DOM survives state changes — only the content webview swaps — so a single
    eval sticks. Best-effort and fully guarded."""
    tw = getattr(mw, "toolbarWeb", None)
    if tw is None:
        return
    raw = state if state is not None else getattr(mw, "state", "")
    safe = "".join(ch for ch in str(raw) if ch.isalnum())
    try:
        tw.eval(
            "document.body && document.body.setAttribute("
            "'data-rf-state','%s');" % safe
        )
    except Exception:
        pass


def on_state_did_change(new_state: str, old_state: str) -> None:
    cfg = _config()
    hide_decks = cfg.get("hide_bottom_on_decks", True)
    hide_over = cfg.get("hide_bottom_on_overview", True)
    if new_state == "deckBrowser":
        _set_bottom_visible(not hide_decks)
    elif new_state == "overview":
        _set_bottom_visible(not hide_over)
    elif new_state == "review":
        # We render our own ease selector inside the reviewer webview; the
        # native bottom toolbar is just chrome we don't need.
        _set_bottom_visible(False)
    else:
        _set_bottom_visible(True)
    _update_title()
    _mark_toolbar_state(new_state)
    _apply_chrome()
    _mark_sidebar_active(new_state)
    _push_sidebar_standing()


def _post_render_fixups() -> None:
    if _config().get("hide_bottom_on_decks", True):
        _set_bottom_visible(False)
    _update_title()
    _mark_toolbar_state()
    _apply_chrome()
    _push_sidebar_standing()
    _refresh_sync_status()


# --------------------------------------------------------------------------- #
# Sidebar nav — hide Anki's top toolbar webview and route `ba:*` pycmds.
# --------------------------------------------------------------------------- #
def _sidebar_on() -> bool:
    return bool(_config().get("sidebar_nav", True))


def _set_top_toolbar_visible(visible: bool) -> None:
    tw = getattr(mw, "toolbarWeb", None)
    if tw is None:
        return
    try:
        tw.setVisible(visible)
    except Exception:
        pass


def _apply_chrome() -> None:
    """Hide Anki's top toolbar webview when the sidebar is on. Anki re-shows
    it on state transitions, so we re-hide after each render."""
    _set_top_toolbar_visible(not _sidebar_on())


def _mark_sidebar_active(state: Optional[str] = None) -> None:
    """Tell every themed webview's sidebar which item is current. Cheap and
    safe — no-ops if the sidebar JS hasn't initialised yet."""
    raw = state if state is not None else getattr(mw, "state", "")
    cmd = {"deckBrowser": "decks", "overview": "decks",
           "review": "decks"}.get(str(raw), "")
    if not cmd:
        return
    js = "window.__baSetActive && window.__baSetActive('%s');" % cmd
    for attr in ("web",):
        w = getattr(mw, attr, None)
        if w is not None:
            try:
                w.eval(js)
            except Exception:
                pass


def _open_settings() -> None:
    """Open the BetterAnki settings dialog."""
    try:
        from .settings import open_settings
        open_settings(mw)
    except Exception as e:
        try:
            from aqt.utils import showWarning
            showWarning(f"BetterAnki settings: {e}")
        except Exception:
            pass


def _on_js_message(handled, message, context):
    """Dispatch `ba:<cmd>` pycmds from our sidebar/settings. Filter hook:
    return (True, None) when we handle it."""
    if not isinstance(message, str) or not message.startswith("ba:"):
        return handled
    cmd = message[3:]
    try:
        if cmd == "decks":
            mw.moveToState("deckBrowser")
        elif cmd == "add":
            mw.onAddCard()
        elif cmd == "browse":
            mw.onBrowse()
        elif cmd == "stats":
            mw.onStats()
        elif cmd == "sync":
            mw.on_sync_button_clicked()
        elif cmd == "settings":
            _open_settings()
        elif cmd == "undo":
            try:
                mw.undo()
            except Exception:
                return handled
        elif cmd == "flag-cycle":
            # Cycle the current card's flag 0 → 1 → 2 → 3 → 4 → 0.
            try:
                rv = getattr(mw, "reviewer", None)
                if rv is None or getattr(rv, "card", None) is None:
                    return handled
                card = rv.card
                cur = int(card.user_flag())
                nxt = (cur + 1) % 5  # 0..4
                card.set_user_flag(nxt)
                # The card needs to be saved so the flag persists; the
                # reviewer's _showQuestion will re-pull on next render.
                try:
                    mw.col.update_card(card)
                except Exception:
                    pass
                _push_progress()
            except Exception:
                return handled
        elif cmd == "create":
            _open_new_deck()
        elif cmd == "import":
            mw.onImport()
        elif cmd.startswith("study:"):
            tail = cmd.split(":", 1)[1]
            if tail.isdigit():
                _start_studying(int(tail))
            else:
                return handled
        elif cmd == "prefs":
            try:
                mw.onPrefs()
            except Exception:
                return handled
        elif cmd.startswith("deck-opts:"):
            tail = cmd.split(":", 1)[1]
            if tail.isdigit():
                # Use Anki's own _showOptions which puts up the full context
                # menu — Rename, Options, Export, Delete — same as clicking
                # the gear next to a deck row in the deck-list view.
                try:
                    mw.deckBrowser._showOptions(tail)  # type: ignore[attr-defined]
                except Exception:
                    # Fallback: at least open the review-settings dialog.
                    try:
                        from aqt.deckoptions import display_options_for_deck_id
                        from anki.decks import DeckId
                        display_options_for_deck_id(DeckId(int(tail)))
                    except Exception:
                        return handled
            else:
                return handled
        else:
            return handled
    except Exception:
        return handled
    return (True, None)


def _open_new_deck() -> None:
    """Open the standard New Deck dialog (same one Anki uses)."""
    try:
        from aqt.operations.deck import add_deck_dialog
        add_deck_dialog(parent=mw)
    except Exception:
        try:
            # Fallback for older Anki APIs.
            mw.deckBrowser._on_create()  # type: ignore[attr-defined]
        except Exception:
            pass


def _start_studying(did: int) -> None:
    """Select a deck and go straight into the reviewer."""
    try:
        _dev_cmd_log(f"start_studying: did={did}")
        mw.col.decks.select(did)
        try:
            mw.col.startTimebox()
        except Exception:
            pass
        cur_state = getattr(mw, "state", "")
        rv = getattr(mw, "reviewer", None)
        if cur_state == "review" and rv is not None:
            try:
                rv._showQuestion()
            except Exception:
                pass
        else:
            mw.moveToState("review")
        # Log final state for debugging.
        try:
            after = getattr(mw, "state", "")
            _dev_cmd_log(f"start_studying done (state now={after})")
        except Exception:
            _dev_cmd_log("start_studying done")
    except Exception as e:
        _dev_cmd_log(f"start_studying err: {e!r}")
        try:
            mw.moveToState("overview")
        except Exception:
            pass


def _practice_header_html() -> str:
    """Streak + today/minutes/all-time as a header band above the heatmap.
    These stats used to live in the sidebar; they fit better here next to
    the visual record of activity."""
    try:
        s = _standing()
    except Exception:
        return ""
    streak = int(s.get("streak", 0) or 0)
    today_n = int(s.get("today", 0) or 0)
    today_min = _minutes_today()
    total = int(s.get("total", 0) or 0)
    # Phosphor-inspired flame: tall body + a small inner highlight that
    # reads as the cool core of the fire.
    flame = (
        '<svg class="ba-flame" viewBox="0 0 24 24" '
        'fill="currentColor" aria-hidden="true">'
        '<path d="M12 2c.5 3 2 4.5 3.5 6.2C17 10 18.5 12 18.5 14.5'
        '  c0 3.6-2.9 6.5-6.5 6.5s-6.5-2.9-6.5-6.5c0-1.6.6-2.9 1.5-3.8'
        '  C8 11.6 9 12 10 12c0-2 0-4.5 2-10z"/>'
        '<path d="M12.5 17.5c-1.4 0-2.5-1.1-2.5-2.5c0-.9.4-1.6 1.2-2'
        '  c.7-.4 1.6-.8 1.9-1.7c.5 1 1.3 1.7 1.6 2.6c.1.4.2.8.2 1.2'
        '  c0 1.4-1.1 2.4-2.4 2.4z" opacity=".55"/>'
        '</svg>'
    )
    return f"""
    <header class="ba-practice-head">
      <div class="ba-practice-streak" title="Consecutive days reviewed">
        {flame}
        <span class="ba-practice-streak-n">{streak}</span>
        <span class="ba-practice-streak-l">day streak</span>
      </div>
      <div class="ba-practice-meta">
        <div class="ba-practice-stat">
          <span class="n">{today_n:,}</span>
          <span class="l">today</span>
        </div>
        <div class="ba-practice-stat">
          <span class="n">{today_min}</span>
          <span class="l">minutes</span>
        </div>
        <div class="ba-practice-stat">
          <span class="n">{total:,}</span>
          <span class="l">all-time</span>
        </div>
      </div>
    </header>
    """


def _single_deck_hero() -> str:
    """When the user has just one top-level deck, present it as a hero with
    the deck name + actionable stats + a primary Study button instead of a
    one-row table that would feel silly."""
    try:
        tree = mw.col.sched.deck_due_tree()
        kids = getattr(tree, "children", [])
        if len(kids) != 1:
            return ""
        d = kids[0]
        name = html.escape(getattr(d, "name", ""))
        new_n = int(getattr(d, "new_count", 0) or 0)
        learn_n = int(getattr(d, "learn_count", 0) or 0)
        rev_n = int(getattr(d, "review_count", 0) or 0)
        did = int(getattr(d, "deck_id", 0))
        total = new_n + learn_n + rev_n
        # The whole card IS the action — no button. Click anywhere on it to
        # start studying. Big numbers carry the visual weight; deck title is
        # small because it's incidental once the user knows which deck.
        click = "" if not total else f"pycmd('ba:study:{did}')"
        tabindex = "-1" if not total else "0"
        disabled = "ba-hero--done" if not total else ""
        # Deck name lives ABOVE the card now (a quiet header). The card is
        # focused on the numbers + the click-anywhere action. The small gear
        # next to the name opens this deck's options dialog (otherwise hard
        # to reach in single-deck mode since the deck row is hidden).
        return f"""
        <header class="ba-deck-head ba-rise">
          <h1 class="ba-deck-name">{name}</h1>
          <button class="ba-deck-opts"
                  onclick="event.stopPropagation();pycmd('ba:deck-opts:{did}')"
                  title="Deck options" aria-label="Deck options">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5h0a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3h0a1.6 1.6 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 1 1.5h0a1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v0a1.6 1.6 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>
            </svg>
          </button>
        </header>
        <button class="ba-hero ba-rise {disabled}" tabindex="{tabindex}"
                onclick="{click}" aria-label="Study {name}">
          <div class="ba-hero-stats">
            <div class="ba-hero-stat ba-due">
              <span class="ba-hero-n">{rev_n}</span>
              <span class="ba-hero-l">Due</span>
            </div>
            <div class="ba-hero-stat ba-new">
              <span class="ba-hero-n">{new_n}</span>
              <span class="ba-hero-l">New</span>
            </div>
            <div class="ba-hero-stat ba-learn">
              <span class="ba-hero-n">{learn_n}</span>
              <span class="ba-hero-l">Learn</span>
            </div>
          </div>
        </button>
        <script>
          (function() {{
            var card = document.querySelector('.ba-hero');
            if (!card || card.classList.contains('ba-hero--done')) return;
            document.addEventListener('keydown', function(e) {{
              if ((e.key === 'Enter' || e.key === ' ')
                  && !e.target.closest('input, textarea, [contenteditable]')) {{
                e.preventDefault();
                card.click();
              }}
            }});
          }})();
        </script>
        """
    except Exception:
        return ""


def _minutes_today() -> int:
    """Total minutes reviewed today, from the revlog. 0 on any error."""
    try:
        shift = _day_shift_seconds()
        today_idx = int((time.time() + shift) // 86400)
        row = mw.col.db.first(
            "select sum(time) from revlog where "
            "cast((id/1000 + ?) / 86400 as int) = ?",
            shift, today_idx,
        )
        if row and row[0]:
            return int(float(row[0]) / 60000.0)
    except Exception:
        pass
    return 0


def _top_decks_count() -> int:
    try:
        tree = mw.col.sched.deck_due_tree()
        return len(getattr(tree, "children", []))
    except Exception:
        return 0


def _last_7_days_active() -> list:
    """A 7-bool list, oldest → today, for the sidebar mini-grid."""
    try:
        counts = _counts_by_day()
        shift = _day_shift_seconds()
        today_idx = int((time.time() + shift) // 86400)
        return [bool(counts.get(today_idx - i, 0) > 0) for i in range(6, -1, -1)]
    except Exception:
        return [False] * 7


def _build_standing_payload() -> Dict[str, Any]:
    s = _standing()
    return {
        "streak": s.get("streak", 0),
        "due": s.get("due"),
        "new": s.get("new"),
        "learn": s.get("learn"),
        "today": s.get("today", 0),
        "todayMin": _minutes_today(),
        "total": s.get("total", 0),
        "singleDeck": _top_decks_count() == 1,
        "last7": _last_7_days_active(),
    }


def _push_sidebar_sync(state: str) -> None:
    """Update the sidebar's Sync indicator state. `state` is one of:
    "" (clean), "pending", "full", "active"."""
    safe = "".join(ch for ch in state if ch.isalnum())
    js = "window.__baSetSync && window.__baSetSync('%s');" % safe
    for w in (getattr(mw, "web", None),):
        if w is not None:
            try:
                w.eval(js)
            except Exception:
                pass


def _refresh_sync_status() -> None:
    """Ask Anki for the current sync status and push it to the sidebar."""
    try:
        from aqt.sync import get_sync_status
        from anki.sync_pb2 import SyncStatusResponse

        def on_status(status):
            req = getattr(status, "required", 0)
            if req == SyncStatusResponse.NORMAL_SYNC:
                _push_sidebar_sync("pending")
            elif req == SyncStatusResponse.FULL_SYNC:
                _push_sidebar_sync("full")
            else:
                _push_sidebar_sync("")
        get_sync_status(mw, on_status)
    except Exception:
        # Older Anki / API change: fall back to silently clearing.
        _push_sidebar_sync("")


def _push_sidebar_standing() -> None:
    """Push the day's standing into every webview's sidebar for live updates
    (state changes, post-render). The initial render is bootstrapped via a
    <head> global; this is for changes after that."""
    try:
        payload = _build_standing_payload()
    except Exception:
        return
    import json as _json
    js = f"window.__baSetStanding && window.__baSetStanding({_json.dumps(payload)});"
    for attr in ("web",):
        w = getattr(mw, attr, None)
        if w is not None:
            try:
                w.eval(js)
            except Exception:
                pass
    # Reviewer has its own webview.
    rv = getattr(mw, "reviewer", None)
    if rv is not None and getattr(rv, "web", None) is not None:
        try:
            rv.web.eval(js)
        except Exception:
            pass


def on_deck_browser_did_render(deck_browser: DeckBrowser) -> None:
    # The deck browser re-shows the bottom strip and Anki (re)sets the window
    # title around render; re-assert our state on the next event-loop tick so
    # our in-page actions stand alone and the title/active-section stick.
    if QTimer is not None:
        QTimer.singleShot(0, _post_render_fixups)
    else:
        _post_render_fixups()


# --------------------------------------------------------------------------- #
# Reviewer progress bar
# --------------------------------------------------------------------------- #
_session = {"total": 0}


def _remaining() -> int:
    try:
        return int(sum(mw.col.sched.counts()))
    except Exception:
        return 0


def _current_deck_name() -> str:
    try:
        did = mw.col.decks.get_current_id()
        return mw.col.decks.name(did) or ""
    except Exception:
        try:
            return mw.col.decks.current()["name"]
        except Exception:
            return ""


def _reviewer_ease_html() -> str:
    """Four interval chips that appear under the answer. Text only —
    no numbers, no labels, no bar. They're hidden by CSS until the
    answer is revealed. We render four slots even for shorter button
    counts (Anki may show 2/3/4 buttons); JS hides extras."""
    return (
        '<div class="ba-rv-ease" aria-label="Rate this card" hidden>'
        '<button class="ba-rv-ease-key ba-rv-ease-1" type="button"'
        '        onclick="pycmd(\'ease1\')" data-ease="1">'
        '<span class="ba-rv-ease-int" data-ease-slot="1"></span></button>'
        '<button class="ba-rv-ease-key ba-rv-ease-2" type="button"'
        '        onclick="pycmd(\'ease2\')" data-ease="2">'
        '<span class="ba-rv-ease-int" data-ease-slot="2"></span></button>'
        '<button class="ba-rv-ease-key ba-rv-ease-3" type="button"'
        '        onclick="pycmd(\'ease3\')" data-ease="3">'
        '<span class="ba-rv-ease-int" data-ease-slot="3"></span></button>'
        '<button class="ba-rv-ease-key ba-rv-ease-4" type="button"'
        '        onclick="pycmd(\'ease4\')" data-ease="4">'
        '<span class="ba-rv-ease-int" data-ease-slot="4"></span></button>'
        '</div>'
    )


def _current_card_type() -> str:
    """A short label for the current card's note type (e.g., "Basic",
    "Cloze"). Empty when no card. Trimmed to fit the header."""
    try:
        c = mw.reviewer.card
        if c is None:
            return ""
        nt = c.note_type() or c.note().model()
        name = (nt.get("name") or "") if isinstance(nt, dict) else getattr(nt, "name", "")
        return str(name)
    except Exception:
        return ""


def _reviewer_header_html() -> str:
    """Header above the card: back chevron + deck name on the left, the
    count breakdown + position on the right, and Edit + More icon buttons
    next to them (Anki's More menu already covers flag/mark/undo)."""
    name = html.escape(_current_deck_name() or "Studying")
    rem = _remaining()
    total = _session["total"] or rem or 1
    done = max(0, total - rem)
    pos = min(done + 1, total)
    new_n = learn_n = rev_n = 0
    try:
        c = mw.col.sched.counts()
        new_n, learn_n, rev_n = int(c[0]), int(c[1]), int(c[2])
    except Exception:
        pass
    edit_svg = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<path d="M12 20h9"/>'
        '<path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4Z"/></svg>'
    )
    more_svg = (
        '<svg viewBox="0 0 24 24" fill="currentColor" '
        'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<circle cx="5" cy="12" r="1.6"/>'
        '<circle cx="12" cy="12" r="1.6"/>'
        '<circle cx="19" cy="12" r="1.6"/></svg>'
    )
    return f"""
    <header class="ba-rv-head">
      <div class="ba-rv-head-left">
        <button class="ba-rv-back" type="button"
                onclick="pycmd('ba:decks')"
                title="Back to decks (Esc)"
                aria-label="Back to decks">‹</button>
        <span class="ba-rv-deck" title="{name}">{name}</span>
      </div>
      <div class="ba-rv-head-right">
        <span class="ba-rv-counts">
          <span class="ba-rv-count ba-rv-c-new"
                title="New cards still to study"><b id="ba-rv-c-new">{new_n}</b><i>new</i></span>
          <span class="ba-rv-count ba-rv-c-learn"
                title="Cards in learning"><b id="ba-rv-c-learn">{learn_n}</b><i>learn</i></span>
          <span class="ba-rv-count ba-rv-c-due"
                title="Review cards due today"><b id="ba-rv-c-due">{rev_n}</b><i>due</i></span>
        </span>
        <span class="ba-rv-sep" aria-hidden="true"></span>
        <span class="ba-rv-pos">
          <b id="ba-rv-pos-now">{pos}</b>
          <span>of</span>
          <b id="ba-rv-pos-total">{total}</b>
        </span>
        <button class="ba-rv-icon-btn" type="button"
                onclick="pycmd('edit')" title="Edit card (E)"
                aria-label="Edit card">{edit_svg}</button>
        <button class="ba-rv-icon-btn" type="button"
                onclick="pycmd('more')" title="More options (M)"
                aria-label="More options">{more_svg}</button>
      </div>
    </header>
    """


def _ease_intervals() -> Optional[Dict[int, str]]:
    """Return {ease: interval_str} for the current card's next-state
    intervals (e.g., {1: "<1m", 2: "<10m", 3: "6d", 4: "13d"}). Returns
    None if anything goes wrong — caller hides the chips in that case."""
    try:
        rv = mw.reviewer
        if rv is None or rv.card is None:
            return None
        labels = mw.col.sched.describe_next_states(rv._v3.states)
        # `labels` order matches Anki's _answerButtonList: Again, [Hard,]
        # Good, [Easy]. Map back to ease number via the button list.
        buttons = rv._answerButtonList()
        out: Dict[int, str] = {}
        for (ease, _name), interval in zip(buttons, labels):
            out[int(ease)] = str(interval)
        return out
    except Exception:
        return None


def _push_progress() -> None:
    if not _config().get("show_progress", True):
        return
    rem = _remaining()
    if rem > _session["total"]:
        _session["total"] = rem
    total = _session["total"] or 1
    done = max(0, total - rem)
    pct = min(100, int(done * 100 / total))
    pos = min(done + 1, total)
    new_n = learn_n = rev_n = 0
    try:
        c = mw.col.sched.counts()
        new_n, learn_n, rev_n = int(c[0]), int(c[1]), int(c[2])
    except Exception:
        pass
    intervals = _ease_intervals() or {}
    default_ease = 3
    try:
        default_ease = int(mw.reviewer._defaultEase())
    except Exception:
        pass
    import json as _json
    intervals_js = _json.dumps(intervals)
    try:
        mw.reviewer.web.eval(
            f"window.__reforgeProgress && window.__reforgeProgress({pct},{done},{rem});"
            f"var $=function(id){{return document.getElementById(id);}};"
            f"var n=$('ba-rv-pos-now'),t=$('ba-rv-pos-total');"
            f"if(n)n.textContent={pos};if(t)t.textContent={total};"
            f"var cn=$('ba-rv-c-new'),cl=$('ba-rv-c-learn'),cd=$('ba-rv-c-due');"
            f"if(cn)cn.textContent={new_n};if(cl)cl.textContent={learn_n};"
            f"if(cd)cd.textContent={rev_n};"
            f"window.__baSetEase && window.__baSetEase({intervals_js}, {default_ease});"
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

# Sidebar nav: route `ba:*` pycmds to the right mw methods + settings dialog.
gui_hooks.webview_did_receive_js_message.append(_on_js_message)

# Sync status indicator — show pending/full when there are changes to push,
# and a soft pulse while a sync is in progress.
try:
    gui_hooks.sync_will_start.append(lambda *a: _push_sidebar_sync("active"))
    gui_hooks.sync_did_finish.append(lambda *a: _refresh_sync_status())
except Exception:
    pass

# Hide Anki's top toolbar webview as soon as the main window / profile is up.
gui_hooks.main_window_did_init.append(_apply_chrome)
gui_hooks.profile_did_open.append(_apply_chrome)

# Re-tag the toolbar after Anki rebuilds it (e.g. sync-status redraw), so the
# active-section highlight isn't lost. Optional — guarded per add-on policy.
try:
    gui_hooks.top_toolbar_did_redraw.append(lambda tb: _mark_toolbar_state())
except Exception:
    pass

# Anki add-on dialog "Config" → open our settings UI instead of raw JSON.
try:
    mw.addonManager.setConfigAction(__name__, _open_settings)
except Exception:
    pass


def _add_tools_menu_action() -> None:
    try:
        from aqt.qt import QAction, QKeySequence, QShortcut, Qt
        act = QAction("BetterAnki Settings…", mw)
        # Cmd+, on macOS / Ctrl+, elsewhere — the canonical "preferences" key.
        act.setShortcut(QKeySequence("Ctrl+,"))
        # Use the enum (NOT a literal int — the values differ between Qt5/6).
        act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        act.triggered.connect(_open_settings)
        mw.form.menuTools.addAction(act)
        # Belt-and-braces: also register a global QShortcut on the main
        # window so the key fires regardless of focus.
        sc = QShortcut(QKeySequence("Ctrl+,"), mw)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc.activated.connect(_open_settings)
        # And a macOS Cmd+, equivalent (some Qt builds need it explicitly).
        sc2 = QShortcut(QKeySequence("Meta+,"), mw)
        sc2.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc2.activated.connect(_open_settings)
    except Exception as e:
        try:
            from aqt.utils import showWarning
            showWarning(f"BetterAnki: failed to register settings shortcut: {e}")
        except Exception:
            pass


gui_hooks.main_window_did_init.append(_add_tools_menu_action)


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
# Dev: a heartbeat file so we can verify the addon module imported (and at
# what time) without scraping stdout. Truncate-on-import so each Anki start
# produces a fresh entry.
try:
    _ctx = os.path.join(ADDON_SRC, ".context")
    if os.path.isdir(_ctx):
        with open(os.path.join(_ctx, "addon.log"), "w") as _fh:
            _fh.write(f"imported {time.time():.0f}\n")
except Exception:
    pass

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


# Dev-only side channel: write a single line to .context/cmd to drive the UI
# from outside the GUI process (used by the screenshot/iteration workflow).
# Commands:
#   review:<did>      - enter review mode for that deck id
#   decks             - return to deck list
#   overview:<did>    - select deck and open overview
#   show              - flip the current card (Show Answer)
#   ease:<1..4>       - rate the current card
#   eval:<js>         - run JS in the reviewer webview (debug)
_dev_cmd_seen_mtime = {"v": 0.0}


def _dev_run_cmd(raw: str) -> None:
    try:
        cmd = raw.strip()
        if not cmd:
            return
        state = getattr(mw, "state", "")
        _dev_cmd_log(f"run: {cmd!r} (state={state})")
        if cmd.startswith("review:"):
            _start_studying(int(cmd.split(":", 1)[1]))
        elif cmd == "decks":
            mw.moveToState("deckBrowser")
        elif cmd.startswith("overview:"):
            did = int(cmd.split(":", 1)[1])
            mw.col.decks.select(did)
            mw.moveToState("overview")
        elif cmd == "show":
            # Only valid when actively reviewing a card.
            if state != "review":
                _dev_cmd_log("show: not in review, ignored")
                return
            rv = getattr(mw, "reviewer", None)
            card = getattr(rv, "card", None) if rv else None
            if rv and card and getattr(rv, "state", "") == "question":
                try:
                    rv._showAnswer()
                except Exception as e:
                    _dev_cmd_log(f"show err: {e!r}")
                    if rv.web:
                        rv.web.eval("pycmd('ans')")
        elif cmd.startswith("ease:"):
            if state != "review":
                _dev_cmd_log("ease: not in review, ignored")
                return
            n = int(cmd.split(":", 1)[1])
            rv = getattr(mw, "reviewer", None)
            rv_state = getattr(rv, "state", "") if rv else ""
            _dev_cmd_log(f"ease: rv.state={rv_state}")
            if rv and getattr(rv, "card", None) and rv_state == "answer":
                rv._answerCard(n)
                _dev_cmd_log("ease: _answerCard ok")
        elif cmd.startswith("eval:"):
            js = cmd[5:]
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "web", None):
                rv.web.eval(js)
            elif getattr(mw, "web", None):
                mw.web.eval(js)
        elif cmd.startswith("beval:"):
            # Eval JS in the reviewer's bottom toolbar webview.
            js = cmd[6:]
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "bottom", None) and getattr(rv.bottom, "web", None):
                rv.bottom.web.eval(js)
        elif cmd.startswith("state_info"):
            try:
                st = getattr(mw, "state", "")
                rv = getattr(mw, "reviewer", None)
                rvs = getattr(rv, "state", "") if rv else "no-rv"
                card = getattr(rv, "card", None) if rv else None
                cardid = card.id if card else "no-card"
                web = getattr(mw, "web", None)
                _dev_cmd_log(
                    f"state={st} rv.state={rvs} card={cardid} "
                    f"web={web!r} bottomWeb={getattr(mw, 'bottomWeb', None)!r}"
                )
                if web:
                    _dev_cmd_log(
                        f"web visible={web.isVisible()} size={web.size().width()}x{web.size().height()}"
                    )
                bw = getattr(mw, "bottomWeb", None)
                if bw:
                    _dev_cmd_log(
                        f"bottomWeb visible={bw.isVisible()} size={bw.size().width()}x{bw.size().height()}"
                    )
            except Exception as e:
                _dev_cmd_log(f"state_info err: {e!r}")
        elif cmd.startswith("dump_ease_main"):
            out = os.path.join(ADDON_SRC, ".context", "ease_main.txt")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "web", None):
                js = (
                    "(function(){"
                    "var btns=document.querySelectorAll('.ba-rv-ease-key');"
                    "var out=[];"
                    "btns.forEach(function(b){"
                    "var cs=getComputedStyle(b);"
                    "var ca=getComputedStyle(b,'::after');"
                    "var cb=getComputedStyle(b,'::before');"
                    "out.push({text:b.textContent.trim(),"
                    "td:cs.textDecoration,tdl:cs.textDecorationLine,"
                    "outline:cs.outline,bs:cs.boxShadow,bb:cs.borderBottom,"
                    "after:{content:ca.content,bs:ca.boxShadow,bb:ca.borderBottom},"
                    "before:{content:cb.content,bs:cb.boxShadow}"
                    "});});"
                    "return JSON.stringify(out);})()"
                )
                def _cb(r, _p=out):
                    try: open(_p,"w").write(str(r))
                    except Exception: pass
                rv.web.evalWithCallback(js, _cb)
        elif cmd.startswith("dump_ease"):
            out = os.path.join(ADDON_SRC, ".context", "ease.txt")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "bottom", None) and getattr(rv.bottom, "web", None):
                js = (
                    "(function(){"
                    "var btns=document.querySelectorAll('#middle button');"
                    "var out=[];"
                    "btns.forEach(function(b){"
                    "var bb=b.getBoundingClientRect();"
                    "var bcs=getComputedStyle(b,'::before');"
                    "out.push({"
                    "btn:{rect:[bb.x,bb.y,bb.width,bb.height]},"
                    "before:{content:bcs.content,fs:bcs.fontSize,"
                    "w:bcs.width,h:bcs.height,bg:bcs.backgroundColor}"
                    "});});"
                    "return JSON.stringify(out);})()"
                )
                def _cb(r, _p=out):
                    try: open(_p,"w").write(str(r))
                    except Exception: pass
                rv.bottom.web.evalWithCallback(js, _cb)
        elif cmd.startswith("dump_bottom_compute"):
            out = os.path.join(ADDON_SRC, ".context", "bottom_compute.txt")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "bottom", None) and getattr(rv.bottom, "web", None):
                js = (
                    "(function(){"
                    "var b=document.body,h=document.documentElement;"
                    "var cs=function(el){return el?getComputedStyle(el):null;};"
                    "return JSON.stringify({"
                    "html:{theme:h.dataset.rfTheme,cls:h.className,"
                    "rfpaper:getComputedStyle(h).getPropertyValue('--rf-paper').trim()},"
                    "body:{bg:cs(b).backgroundColor,fg:cs(b).color}});"
                    "})()"
                )
                def _cb(r, _p=out):
                    try: open(_p,"w").write(str(r))
                    except Exception: pass
                rv.bottom.web.evalWithCallback(js, _cb)
        elif cmd.startswith("dump_compute"):
            out = os.path.join(ADDON_SRC, ".context", "compute.txt")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "web", None):
                js = (
                    "(function(){"
                    "var b=document.body,q=document.getElementById('qa');"
                    "var cs=function(el){return el?getComputedStyle(el):null;};"
                    "return JSON.stringify({"
                    "body:{fs:cs(b).fontSize,ff:cs(b).fontFamily},"
                    "qa:{fs:cs(q).fontSize,ff:cs(q).fontFamily}"
                    "});})()"
                )
                def _cb(r, _p=out):
                    try: open(_p,"w").write(str(r))
                    except Exception: pass
                rv.web.evalWithCallback(js, _cb)
        elif cmd.startswith("dump_card"):
            out = os.path.join(ADDON_SRC, ".context", "card.html")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "web", None):
                js = (
                    "JSON.stringify({"
                    "html: document.documentElement.outerHTML,"
                    "card: (document.querySelector('.card')||document.body).outerHTML"
                    "})"
                )
                def _cb(result, _path=out):
                    try:
                        with open(_path, "w") as fh:
                            fh.write(str(result))
                    except Exception:
                        pass
                rv.web.evalWithCallback(js, _cb)
        elif cmd.startswith("dump_bottom"):
            # Print the bottom bar's outerHTML to stdout (via a tempfile).
            import json as _json
            out = os.path.join(ADDON_SRC, ".context", "bottom.html")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "bottom", None) and getattr(rv.bottom, "web", None):
                js = (
                    "(function(){var x={html:document.documentElement.outerHTML,"
                    "links:Array.from(document.querySelectorAll('link')).map(l=>l.href)};"
                    "var b=document.querySelector('button');"
                    "if(b){var cs=getComputedStyle(b);"
                    "x.btn={border:cs.border,bg:cs.backgroundColor,br:cs.borderRadius,"
                    "appearance:cs.appearance,wkApp:cs.webkitAppearance};}"
                    "return JSON.stringify(x);})()"
                )
                def _cb(result, _path=out):
                    try:
                        with open(_path, "w") as fh:
                            fh.write(str(result))
                    except Exception:
                        pass
                rv.bottom.web.evalWithCallback(js, _cb)
    except Exception as e:
        try:
            print("[ba-dev-cmd]", repr(e))
        except Exception:
            pass


def _dev_cmd_log(msg: str) -> None:
    try:
        with open(os.path.join(ADDON_SRC, ".context", "addon.log"), "a") as fh:
            fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _dev_cmd_watch() -> None:
    cmd_file = os.path.join(ADDON_SRC, ".context", "cmd")
    _dev_cmd_log("dev_cmd_watch started")
    while not _dev_stop.is_set() and _dev_active():
        try:
            if os.path.exists(cmd_file):
                mtime = os.path.getmtime(cmd_file)
                if mtime != _dev_cmd_seen_mtime["v"]:
                    _dev_cmd_seen_mtime["v"] = mtime
                    try:
                        with open(cmd_file, "r") as fh:
                            data = fh.read()
                    except Exception as e:
                        _dev_cmd_log(f"read err: {e!r}")
                        data = ""
                    for line in data.splitlines():
                        if line.strip():
                            _dev_cmd_log(f"cmd: {line!r}")
                            try:
                                mw.taskman.run_on_main(
                                    lambda l=line: _dev_run_cmd(l)
                                )
                            except Exception as e:
                                _dev_cmd_log(f"dispatch err: {e!r}")
        except Exception as e:
            _dev_cmd_log(f"loop err: {e!r}")
        _dev_stop.wait(0.2)
    _dev_cmd_log("dev_cmd_watch exited")


_dev_cmd_started = {"v": False}


def _dev_cmd_start() -> None:
    if not _dev_active():
        return
    if _dev_cmd_started["v"]:
        return
    _dev_cmd_started["v"] = True
    # Drain any stale cmd file from a prior session so we don't auto-fire
    # a command (like `show`) against the homepage state on startup.
    try:
        stale = os.path.join(ADDON_SRC, ".context", "cmd")
        if os.path.exists(stale):
            _dev_cmd_seen_mtime["v"] = os.path.getmtime(stale)
    except Exception:
        pass
    t = threading.Thread(
        target=_dev_cmd_watch, name="betteranki-dev-cmd", daemon=True
    )
    t.start()


gui_hooks.profile_did_open.append(_dev_start)
gui_hooks.profile_did_open.append(_dev_cmd_start)
gui_hooks.main_window_did_init.append(_dev_start)
gui_hooks.main_window_did_init.append(_dev_cmd_start)
gui_hooks.profile_will_close.append(_dev_shutdown)
