"""Anki Design — a from-scratch Anki UI redesign.

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
import math
import os
import threading
import time
from typing import Any, Dict, Optional

from aqt import gui_hooks, mw
from aqt.deckbrowser import DeckBrowser, DeckBrowserContent
from aqt.editor import Editor, EditorMode
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


# Fixed-palette heatmaps. Four shades, low intensity → high.
# Dark-mode set: eyeballed against the near-black canvas (#0b0c0f).
# Light-mode set: eyeballed against the cream canvas (#f6f3ec) — the
# dark sets render as harsh blobs in light mode, so each palette gets
# its own light ramp running from pale-tinted to saturated.
_HEATMAP_DARK: Dict[str, list] = {
    "green":  ["#0e4429", "#006d32", "#26a641", "#39d353"],
    "teal":   ["#0c4747", "#0d7d76", "#14b8a6", "#5eead4"],
    "violet": ["#3b1670", "#6b2da3", "#9656ce", "#c896ec"],
    "rose":   ["#5c1024", "#8c1338", "#cf2553", "#f43f5e"],
    "amber":  ["#5a3a06", "#a87212", "#e09524", "#f7c149"],
}
_HEATMAP_LIGHT: Dict[str, list] = {
    "green":  ["#cdebd4", "#84d18b", "#3aa552", "#1a6c2e"],
    "teal":   ["#cdebe7", "#86d3c8", "#22a89a", "#0e6b62"],
    "violet": ["#e5ddf6", "#bba6e2", "#7c52d6", "#3f1f8a"],
    "rose":   ["#fbd9df", "#f29eaa", "#dc3a59", "#7a1230"],
    "amber":  ["#fde6b6", "#f1c46c", "#cf8418", "#7a4708"],
}


def _shades_from_accent(accent: str, bg: tuple) -> list:
    """Blend the accent toward a background color at four ratios.
    Level 4 is the full accent; lower levels are progressively desaturated
    toward the canvas tint."""
    try:
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
    except Exception:
        r, g, b = 108, 140, 255  # default accent
    out = []
    for ratio in (0.22, 0.45, 0.72, 1.0):
        nr = int(bg[0] + (r - bg[0]) * ratio)
        ng = int(bg[1] + (g - bg[1]) * ratio)
        nb = int(bg[2] + (b - bg[2]) * ratio)
        out.append(f"#{nr:02x}{ng:02x}{nb:02x}")
    return out


def _heatmap_palette_decl(choice: str, accent: str) -> str:
    """CSS rule block (not a single declaration list) that paints the
    heatmap cells per palette + theme. Emits two rule blocks — one for
    each of dark and light — plus a @media block so the heatmap follows
    the OS appearance when the theme is set to "system"."""
    if choice in _HEATMAP_DARK:
        dark = _HEATMAP_DARK[choice]
        light = _HEATMAP_LIGHT[choice]
    else:
        dark = _shades_from_accent(accent, bg=(12, 14, 22))
        light = _shades_from_accent(accent, bg=(246, 243, 236))
    d1, d2, d3, d4 = dark
    l1, l2, l3, l4 = light
    # The !important wins over theme.css's per-theme defaults. We emit a
    # CSS rule block here (separate from the page's main injection) so the
    # selectors can target dark/light themes independently.
    return (
        f":root,:root[data-rf-theme=\"dark\"]"
        f"{{--rf-hm-l1:{d1}!important;--rf-hm-l2:{d2}!important;"
        f"--rf-hm-l3:{d3}!important;--rf-hm-l4:{d4}!important;}}"
        f":root[data-rf-theme=\"light\"]"
        f"{{--rf-hm-l1:{l1}!important;--rf-hm-l2:{l2}!important;"
        f"--rf-hm-l3:{l3}!important;--rf-hm-l4:{l4}!important;}}"
        f"@media (prefers-color-scheme:light)"
        f"{{:root:not([data-rf-theme=\"dark\"])"
        f"{{--rf-hm-l1:{l1}!important;--rf-hm-l2:{l2}!important;"
        f"--rf-hm-l3:{l3}!important;--rf-hm-l4:{l4}!important;}}}}"
    )


def _is(context: Any, cls: Any) -> bool:
    return bool(cls) and isinstance(context, cls)


# --------------------------------------------------------------------------- #
# Theme + asset injection
# --------------------------------------------------------------------------- #
def on_webview_will_set_content(web_content: WebContent, context: Optional[Any]) -> None:
    is_editor = isinstance(context, Editor)
    themed = (
        isinstance(context, (DeckBrowser, Overview, Reviewer))
        or _is(context, _ToolbarCtx)
        or _is(context, _BottomCtx)
        or _is(context, _ReviewerBottomCtx)
        or _is(context, _DeckBrowserBottomCtx)
        or is_editor
    )
    if not themed:
        return

    cfg = _config()
    accent = cfg.get("accent", "#6c8cff")
    theme_pref = cfg.get("theme", "system")  # "system" | "light" | "dark"
    density = cfg.get("density", "comfortable")
    palette_choice = cfg.get("heatmap_palette", "accent")
    card_width_choice = cfg.get("reviewer_card_width", "medium")
    font_size_choice = cfg.get("reviewer_font_size", "medium")
    # User-supplied display fonts are prepended to the existing stacks.
    serif_user = (cfg.get("font_serif") or "").strip()
    sans_user = (cfg.get("font_sans") or "").strip()
    serif_decl = f"--rf-serif:{serif_user}, ui-serif, 'New York', Georgia, serif;" \
        if serif_user else ""
    sans_decl = f"--rf-sans:{sans_user}, ui-sans-serif, -apple-system, system-ui, sans-serif;" \
        if sans_user else ""

    # Reviewer geometry — variables surface in reviewer.css.
    width_map = {"narrow": "640px", "medium": "780px", "wide": "920px",
                 "full": "100%"}
    # Sizes tuned for the reviewer rebuild's reading column.
    fontsize_map = {"small": "22px", "medium": "28px", "large": "34px",
                    "x-large": "40px"}
    # Chrome (header + bottom buttons) scales with the same setting so the
    # whole reviewer surface grows together. Multipliers track the card
    # font-size ratios above (22/28/34/40 → 0.85/1.0/1.25/1.5) so chrome
    # grows enough to stay in proportion with the larger card text.
    chrome_scale_map = {"small": "0.85", "medium": "1", "large": "1.25",
                        "x-large": "1.5"}
    card_width = width_map.get(card_width_choice, "780px")
    card_font_size = fontsize_map.get(font_size_choice, "28px")
    chrome_scale = chrome_scale_map.get(font_size_choice, "1")
    reviewer_decl = (
        f"--rf-card-max-width:{card_width};"
        f"--rf-card-font-size:{card_font_size};"
        f"--rf-chrome-scale:{chrome_scale};"
    )

    # Heatmap palette — emits its own rule block (light + dark variants),
    # so its rules can stand outside the single-rule injection below.
    hm_rules = _heatmap_palette_decl(palette_choice, accent)

    # tokens.css derives --accent from --rf-accent; inject the latter here.
    # `data-rf-theme` on <html> forces light/dark over the system @media.
    # `data-rf-density` lets theme.css tighten or loosen spacing.
    extras = "<script>(function(){var d=document.documentElement;"
    if theme_pref in ("light", "dark"):
        extras += f"d.dataset.rfTheme='{theme_pref}';"
    extras += f"d.dataset.rfDensity='{density}';"
    extras += "})();</script>"

    web_content.head += (
        f"<style>:root,.night-mode,body{{"
        f"--rf-accent:{accent};"
        f"{serif_decl}{sans_decl}{reviewer_decl}"
        f"}}{hm_rules}</style>"
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
        # Cmd-K palette is available on every themed surface (deck browser,
        # overview, reviewer). cmdk.js owns the hotkey and the overlay DOM;
        # the matching Python search backend lives in cmdk.py.
        web_content.css.append(f"{WEB}/cmdk.css")
        web_content.js.append(f"{WEB}/cmdk.js")
    if isinstance(context, DeckBrowser):
        web_content.css.append(f"{WEB}/heatmap.css")
        web_content.js.append(f"{WEB}/heatmap.js")
        # Whole-row click → study (skips the Overview page). Loaded
        # unconditionally on the deck browser, independent of sidebar.
        web_content.js.append(f"{WEB}/deckrow.js")
        # Expand/collapse chevron on parent decks. Tree is forced fully
        # expanded server-side (see _patch_deck_tree_always_expanded);
        # this JS folds descendants client-side, session-only.
        web_content.js.append(f"{WEB}/decktree.js")
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
        web_content.css.append(f"{WEB}/logo.css")
        web_content.css.append(f"{WEB}/sidebar.css")
        web_content.css.append(f"{WEB}/deckopts.css")
        web_content.js.append(f"{WEB}/sidebar.js")
        web_content.js.append(f"{WEB}/deckopts.js")
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
            'title="Anki Design settings">⚙</button>' + web_content.body
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
    if is_editor:
        # Only style the editor in ADD_CARDS mode — the same Editor is used
        # by Browser and Edit-Current; we don't want to overwrite their
        # chrome here. Anki's CSP blocks inline <script> in the editor page,
        # so the mode AND theme are communicated via a meta tag in the head
        # that addcard.js reads (avoiding inline-script CSP). Inline <style>
        # IS allowed and runs synchronously before first paint, so we use it
        # to suppress the open-time FOUC: the body starts at opacity 0 on a
        # paper-colored canvas, then addcard.js fades it back in once the
        # toolbar/field/tags settle. Without this, the user sees Anki's
        # default editor briefly, then ours, then JS reshuffling tags and
        # the gear into place — reads as a stack of flashes.
        em = getattr(context, "editorMode", None)
        if em == EditorMode.ADD_CARDS:
            theme_safe = theme_pref if theme_pref in ("light", "dark") else ""
            # Resolve the actual paper color once, in Python — even when
            # theme_pref is "system" — so the inline <style> can emit a
            # single concrete bg color. If we instead used a CSS media
            # query keyed to prefers-color-scheme, the bg would flip
            # mid-load on system=dark + addon=light (because data-rf-theme
            # isn't set until addcard.js runs), which itself reads as a
            # flash. One concrete color = no flip.
            try:
                from . import addcard as _addcard
                _pal, _ = _addcard._resolve_palette()
                paper_color = _pal["paper"]
            except Exception:
                paper_color = "#f6f3ec"
            web_content.head += (
                "<style>"
                # !important: Anki's editor.css loads after our inline
                # style and sets `body { background-color: var(--bs-body-bg) }`
                # which resolves to a near-white in light mode (the default
                # Bootstrap palette). Without !important Anki wins on source
                # order and the page flashes white before our addcard.css
                # eventually overrides body bg. !important here makes the
                # paper bg stick from first paint.
                f"html,body{{background:{paper_color}!important}}"
                "body{opacity:0;transition:opacity 220ms ease}"
                "html[data-ba-ready] body{opacity:1}"
                "</style>"
                f'<meta name="ba-editor-mode" content="add">'
                f'<meta name="ba-theme" content="{theme_safe}">'
            )
            web_content.css.append(f"{WEB}/addcard.css")
            web_content.js.append(f"{WEB}/addcard.js")


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


def _heatmap_level_fn(counts: Dict[int, int]):
    """Pick a bucketing algorithm based on the shape of the data, so the
    four shades stay visually varied across very different histories
    (uniform habit, gentle ramp, occasional cram days, long-tail outliers).

    The chosen strategy depends on:
      • # of distinct nonzero values (tiny histories get a direct mapping)
      • peak / median ratio (skewness)
      • peak / p95 ratio (outlier severity)
    """
    nonzero = sorted(c for c in counts.values() if c > 0)
    if not nonzero:
        return lambda n: 0

    uniq = sorted(set(nonzero))
    # Few distinct values → map each one directly to a shade. Avoids the
    # awkwardness of bucketing 4 values into 4 buckets via arithmetic.
    if len(uniq) <= 4:
        direct = {v: i + 1 for i, v in enumerate(uniq)}
        return lambda n: direct.get(n, 0) if n > 0 else 0

    def pct(p: float) -> int:
        # Nearest-rank percentile; safe for short lists.
        i = max(0, min(len(nonzero) - 1, int(round(p * (len(nonzero) - 1)))))
        return nonzero[i]

    peak = nonzero[-1]
    median = pct(0.5) or 1
    p95 = pct(0.95) or 1
    skew = peak / median
    outlier = peak / p95

    # Outlier-dominated (a few cram days dwarf the rest): quantile buckets
    # so the outliers can't squash everyone else into L1.
    if outlier > 3 and len(nonzero) >= 8:
        q1, q2, q3 = pct(0.25), pct(0.5), pct(0.75)
        def level_q(n: int) -> int:
            if n <= 0: return 0
            if n <= q1: return 1
            if n <= q2: return 2
            if n <= q3: return 3
            return 4
        return level_q

    # Heavy skew without runaway outliers: log compresses the long tail.
    if skew > 10:
        log_peak = math.log1p(peak) or 1.0
        return lambda n: 0 if n <= 0 else min(4, 1 + int(math.log1p(n) * 4 / log_peak))

    # Moderate skew: sqrt is gentler than log, keeps mid-range readable.
    if skew > 3:
        sqrt_peak = math.sqrt(peak) or 1.0
        return lambda n: 0 if n <= 0 else min(4, 1 + int(math.sqrt(n) * 4 / sqrt_peak))

    # Tight distribution: plain linear is enough.
    return lambda n: 0 if n <= 0 else min(4, 1 + int(n * 4 / (peak + 0.0001)))


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
    level = _heatmap_level_fn(counts)

    columns = (today_idx - grid_start) // 7 + 1

    cells = []
    month_spans = []  # [label, span_in_columns]
    prev_month = None
    for w in range(columns):
        cd = date_for(grid_start + w * 7)  # the column's Sunday
        if cd.month != prev_month:
            month_spans.append([_MONTHS[cd.month - 1], 1])
            prev_month = cd.month
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
    </div>
    """


# Force the deck-browser tree to render with every node expanded — the user
# wants the full hierarchy visible by default, not a "+/-" puzzle. We patch
# `_render_deck_node` (not the persisted collapsed state) so the user's saved
# collapse flags stay intact in the backend; we just ignore them in this view.
def _patch_deck_tree_always_expanded() -> None:
    try:
        if getattr(DeckBrowser, "_ad_expand_patched", False):
            return
        _orig = DeckBrowser._render_deck_node

        def _patched(self, node, ctx):
            try:
                # Walk and flatten any persisted collapse so all rows render.
                # Per-call: only mutates the in-memory tree node Anki built
                # for this render. The next render rebuilds from the backend.
                stack = [node]
                while stack:
                    n = stack.pop()
                    try:
                        n.collapsed = False
                    except Exception:
                        pass
                    stack.extend(getattr(n, "children", []) or [])
            except Exception:
                pass
            return _orig(self, node, ctx)

        DeckBrowser._render_deck_node = _patched  # type: ignore[assignment]
        DeckBrowser._ad_expand_patched = True  # type: ignore[attr-defined]
    except Exception:
        pass


def on_deck_browser_will_render_content(
    deck_browser: DeckBrowser, content: DeckBrowserContent
) -> None:
    cfg = _config()
    heatmap = ""
    if cfg.get("show_heatmap", True):
        try:
            heatmap = build_heatmap_html(int(cfg.get("heatmap_weeks", 53)))
        except Exception as e:
            heatmap = f"<!-- anki-design heatmap error: {e} -->"
    # Single-deck hero replaces the table (CSS hides the table in this mode).
    hero = ""
    try:
        if _top_decks_count() == 1:
            hero = _single_deck_hero()
    except Exception:
        pass
    practice = (
        f'<section class="ba-practice">{heatmap}</section>'
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
    # Re-check pending sync on every navigation so the sidebar dot reflects
    # current state after reviewing/adding/etc., not just on deck-browser
    # render.
    _refresh_sync_status()


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
    """Open the Anki Design settings — embedded inline if possible,
    standalone Preferences dialog otherwise."""
    # Tear down any other embed that might be up; only one inline view
    # at a time.
    for mod in ("addcard_embed", "browse_embed", "stats_embed"):
        try:
            from importlib import import_module
            import_module("." + mod, __name__).close_inline()
        except Exception:
            pass
    try:
        from . import settings_embed
        settings_embed.open_inline(mw)
        return
    except Exception:
        pass
    # Fallback: standalone Preferences dialog with Anki Design tab.
    try:
        from .settings import open_settings
        open_settings(mw)
    except Exception as e:
        try:
            from aqt.utils import showWarning
            showWarning(f"Anki Design settings: {e}")
        except Exception:
            pass


def _on_js_message(handled, message, context):
    """Dispatch `ba:<cmd>` pycmds from our sidebar/settings. Filter hook:
    return (True, None) when we handle it."""
    if not isinstance(message, str):
        return handled
    # Anki's deck browser emits `open:<did>` when a deck is clicked, which
    # normally lands on the intermediate Overview page. Skip that and go
    # straight into studying — same target as the single-deck hero.
    if message.startswith("open:") and isinstance(context, DeckBrowser):
        tail = message.split(":", 1)[1]
        if tail.isdigit():
            try:
                _start_studying(int(tail))
            except Exception:
                return handled
            return (True, None)
        return handled
    if not message.startswith("ba:"):
        return handled
    cmd = message[3:]
    try:
        if cmd.startswith("cmdk-search:"):
            try:
                from . import cmdk as _cmdk
                _cmdk.handle_search(cmd[len("cmdk-search:"):])
            except Exception:
                pass
            return (True, None)
        if cmd.startswith("cmdk-do:"):
            try:
                from . import cmdk as _cmdk
                _cmdk.handle_do(cmd[len("cmdk-do:"):])
            except Exception:
                pass
            return (True, None)
        if cmd == "cmdk-open":
            # Close any open embed so the palette renders above the deck
            # homepage instead of behind the embed's Qt overlay.
            try:
                from . import cmdk as _cmdk
                _cmdk.open_from_outside("")
            except Exception:
                pass
            return (True, None)
        if cmd == "embed-ready":
            # addcard.js fires this from reveal() once the editor body is
            # ready to fade in. We drop the anti-flash curtain that
            # open_inline put up, so the user transitions straight from
            # paper to faded-in editor with no intermediate state.
            try:
                from . import addcard_embed
                addcard_embed.drop_curtain()
            except Exception:
                pass
            return (True, None)
        if cmd.startswith("edit-save:"):
            payload = cmd[len("edit-save:"):]
            try:
                from . import editreviewer
                editreviewer.handle_edit_save(payload)
            except Exception:
                pass
            return (True, None)
        if cmd.startswith("edit-full"):
            # Either "edit-full" (no payload) or "edit-full:<json>".
            payload = ""
            if cmd.startswith("edit-full:"):
                payload = cmd[len("edit-full:"):]
            try:
                from . import editreviewer
                editreviewer.handle_edit_full(payload)
            except Exception:
                pass
            return (True, None)
        if cmd.startswith("edit-state:"):
            # JS enter/exit signal — toggles whether the reviewer's Qt
            # shortcuts are active. While editing they're disabled so the
            # user can type normally (including letters like e/m, plus
            # ⌘+Backspace which Anki normally maps to delete-note).
            on = cmd[len("edit-state:"):] == "on"
            try:
                from . import editreviewer
                editreviewer.set_edit_active(on)
            except Exception:
                pass
            return (True, None)
        if cmd == "decks":
            # If we're in any embedded view (Add, Browse, Stats,
            # Settings), close it first so the deck browser becomes
            # visible again. The embeds are overlays painted *on top
            # of* the deck browser — mw.state stays "deckBrowser" the
            # whole time. Calling moveToState while already in
            # deckBrowser state triggers a full re-render of the deck
            # list HTML (deckBrowser.show()), which reads as a
            # disorienting flash when switching tabs. Only move state
            # when we're actually somewhere else (reviewer, overview,
            # etc.).
            for mod in (
                "addcard_embed", "browse_embed", "stats_embed", "settings_embed",
            ):
                try:
                    from importlib import import_module
                    import_module("." + mod, __name__).close_inline()
                except Exception:
                    pass
            if getattr(mw, "state", None) != "deckBrowser":
                mw.moveToState("deckBrowser")
        elif cmd == "add":
            # Open AddCards inside the main window (over the deck area, to
            # the right of the sidebar). Falls back to the standard window
            # if the embed setup fails. Tear other embeds down first.
            for mod in ("browse_embed", "stats_embed", "settings_embed"):
                try:
                    from importlib import import_module
                    import_module("." + mod, __name__).close_inline()
                except Exception:
                    pass
            try:
                from . import addcard_embed
                addcard_embed.open_inline(mw)
            except Exception:
                mw.onAddCard()
        elif cmd == "browse":
            # Open the Browser embedded in the main window, mirroring the
            # Add embed. Tear other embeds down first.
            for mod in ("addcard_embed", "stats_embed", "settings_embed"):
                try:
                    from importlib import import_module
                    import_module("." + mod, __name__).close_inline()
                except Exception:
                    pass
            try:
                from . import browse_embed
                browse_embed.open_inline(mw)
            except Exception:
                mw.onBrowse()
        elif cmd == "stats":
            # Open Stats embedded in the main window. Tear other embeds
            # down first.
            for mod in ("addcard_embed", "browse_embed", "settings_embed"):
                try:
                    from importlib import import_module
                    import_module("." + mod, __name__).close_inline()
                except Exception:
                    pass
            try:
                from . import stats_embed
                stats_embed.open_inline(mw)
            except Exception:
                mw.onStats()
        elif cmd == "sync":
            mw.on_sync_button_clicked()
        elif cmd == "settings":
            _open_settings()
        elif cmd == "website":
            try:
                from aqt.utils import openLink
                openLink("https://anki.design")
            except Exception:
                return handled
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
            _focus_inline_new_deck()
        elif cmd == "create-fallback":
            _open_new_deck_dialog()
        elif cmd.startswith("create:"):
            _create_deck_inline(cmd.split(":", 1)[1])
        elif cmd == "import":
            mw.onImport()
        elif cmd.startswith("study:"):
            tail = cmd.split(":", 1)[1]
            if tail.isdigit():
                _start_studying(int(tail))
            else:
                return handled
        elif cmd == "prefs":
            # Same destination as ba:settings — route through the embed.
            try:
                _open_settings()
            except Exception:
                return handled
        elif cmd.startswith("deck:"):
            # Items from our custom deck-options menu (web/deckopts.js).
            # Format: deck:<action>:<did>[:<arg>]
            parts = cmd.split(":", 3)
            if len(parts) < 3 or not parts[2].isdigit():
                return handled
            action = parts[1]
            did = int(parts[2])
            extra = parts[3] if len(parts) >= 4 else None
            db = getattr(mw, "deckBrowser", None)
            try:
                if action == "rename" and db is not None:
                    db._rename(did)  # type: ignore[attr-defined]
                elif action == "rename-to" and extra is not None:
                    _rename_deck_inline(did, extra)
                elif action == "options":
                    try:
                        from aqt.deckoptions import display_options_for_deck_id
                        from anki.decks import DeckId
                        display_options_for_deck_id(DeckId(did))
                    except Exception:
                        if db is not None:
                            db._options(did)  # type: ignore[attr-defined]
                elif action == "export":
                    # Anki's deck-browser exporter dispatches on did.
                    try:
                        from aqt.import_export.exporting import ExportDialog
                        ExportDialog(mw, did=did)
                    except Exception:
                        if db is not None:
                            db._export(did)  # type: ignore[attr-defined]
                elif action == "rebuild" and db is not None:
                    db._rebuild(did)  # type: ignore[attr-defined]
                elif action == "empty" and db is not None:
                    db._empty(did)  # type: ignore[attr-defined]
                elif action == "delete" and db is not None:
                    db._delete(did)  # type: ignore[attr-defined]
                else:
                    return handled
            except Exception:
                return handled
        else:
            return handled
    except Exception:
        return handled
    return (True, None)


def _focus_inline_new_deck() -> None:
    """Focus the inline create input in the sidebar. Falls back to Anki's
    native dialog if the sidebar isn't reachable (other page, JS not loaded)."""
    web = getattr(mw, "web", None)
    state = getattr(mw, "state", "")
    if web is not None and state in ("deckBrowser", "overview"):
        try:
            web.eval(
                "if (window.__baFocusNewDeck) window.__baFocusNewDeck();"
                "else pycmd('ba:create-fallback');"
            )
            return
        except Exception:
            pass
    _open_new_deck_dialog()


def _open_new_deck_dialog() -> None:
    """Last-resort fallback: open Anki's native New Deck dialog."""
    try:
        from aqt.operations.deck import add_deck_dialog
        add_deck_dialog(parent=mw)
    except Exception:
        try:
            mw.deckBrowser._on_create()  # type: ignore[attr-defined]
        except Exception:
            pass


def _create_deck_inline(name: str) -> None:
    """Create a deck by name from the inline sidebar input. `decks.id(name,
    create=True)` is idempotent — a duplicate name returns the existing id,
    so no pre-check is needed."""
    name = (name or "").strip()
    if not name:
        return
    try:
        mw.col.decks.id(name, create=True)
    except Exception:
        return
    try:
        mw.reset()
    except Exception:
        pass


def _rename_deck_inline(did: int, encoded_leaf: str) -> None:
    """Apply an inline rename from the home page row. The user edits only
    the leaf segment, so we preserve any parent prefix and replace the
    last `::`-separated component with what they typed.

    If they typed `::` themselves, that path becomes the new tail — so
    `A::B::C` edited to `X::Y` becomes `A::B::X::Y`. Empty/unchanged
    inputs are no-ops."""
    try:
        from urllib.parse import unquote
        new_leaf = unquote(encoded_leaf or "").strip()
    except Exception:
        return
    if not new_leaf:
        return
    try:
        current = mw.col.decks.name(did)
    except Exception:
        return
    if not current:
        return
    parent_parts = current.split("::")[:-1]
    new_full = "::".join(parent_parts + [new_leaf]) if parent_parts else new_leaf
    if new_full == current:
        return
    try:
        from aqt.operations.deck import rename_deck
        from anki.decks import DeckId
        rename_deck(
            parent=mw, deck_id=DeckId(did), new_name=new_full,
        ).run_in_background()
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
          <h1 class="ba-deck-name" data-did="{did}">{name}</h1>
          <button class="ba-deck-opts"
                  onclick="window.__adDeckOpts({did}, event)"
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


# --------------------------------------------------------------------------- #
# Congrats page (Overview's empty state) — redesigned.
# Anki's "Congratulations! You have finished this deck for now." is a Svelte
# page loaded via `web.load_sveltekit_page("congrats")`. That bypasses the
# `webview_will_set_content` filter, so we hook `webview_did_inject_style_into_page`
# instead — it fires after Anki's standard CSS injection for *every* page,
# including Svelte ones. We detect the congrats URL and inject our redesign.
# --------------------------------------------------------------------------- #
def _deck_and_descendant_ids(did: int) -> list:
    """Return [did, *all_descendant_dids] for a given deck. Best-effort: we
    fall back to just [did] if Anki's deck API surface differs."""
    try:
        ids = [int(did)]
        try:
            children = mw.col.decks.children(did)  # [(name, id), ...]
            ids.extend(int(cid) for _name, cid in children)
        except Exception:
            pass
        return ids
    except Exception:
        return [int(did)]


def _finished_deck_stats(did: int) -> Dict[str, Any]:
    """Today's revlog stats for the deck the user just finished (deck + its
    descendants). Returns counts, total time, and ease breakdown — used as the
    big-number panel on the redesigned congrats page."""
    out: Dict[str, Any] = {
        "thisDeck": 0,
        "timeSec": 0,
        "breakdown": {"again": 0, "hard": 0, "good": 0, "easy": 0},
    }
    try:
        shift = _day_shift_seconds()
        today_idx = int((time.time() + shift) // 86400)
        ids = _deck_and_descendant_ids(int(did))
        if not ids:
            return out
        placeholders = ",".join("?" * len(ids))
        row = mw.col.db.first(
            f"select count(*), coalesce(sum(time),0), "
            f"sum(case when ease=1 then 1 else 0 end), "
            f"sum(case when ease=2 then 1 else 0 end), "
            f"sum(case when ease=3 then 1 else 0 end), "
            f"sum(case when ease=4 then 1 else 0 end) "
            f"from revlog where cid in "
            f"(select id from cards where did in ({placeholders})) "
            f"and cast((id/1000 + ?) / 86400 as int) = ?",
            *ids, shift, today_idx,
        )
        if row:
            cnt, ms, ag, hd, gd, ez = row
            out["thisDeck"] = int(cnt or 0)
            out["timeSec"] = int(float(ms or 0) / 1000.0)
            out["breakdown"] = {
                "again": int(ag or 0),
                "hard":  int(hd or 0),
                "good":  int(gd or 0),
                "easy":  int(ez or 0),
            }
    except Exception:
        pass
    return out


def _filtered_deck_tree(exclude_did: int) -> list:
    """Flat list of decks with any work (new/learn/review > 0), excluding the
    finished deck *and its descendants*. Preserves Anki's natural deck order
    (a depth-first walk of `deck_due_tree()`), tagging each entry with its
    visual depth so the JS can indent."""
    out: list = []
    try:
        exclude = set(int(x) for x in _deck_and_descendant_ids(int(exclude_did)))
        tree = mw.col.sched.deck_due_tree()

        def visit(node, depth):
            did = int(getattr(node, "deck_id", 0) or 0)
            n = int(getattr(node, "new_count", 0) or 0)
            l = int(getattr(node, "learn_count", 0) or 0)
            r = int(getattr(node, "review_count", 0) or 0)
            # Sum descendant work so a parent with empty self but stocked kids
            # still surfaces as a row (we still show kids individually).
            sub_total = n + l + r
            kids = list(getattr(node, "children", []) or [])
            kid_rows: list = []
            for c in kids:
                kid_rows.extend(visit(c, depth + 1))
                cn = int(getattr(c, "new_count", 0) or 0)
                cl = int(getattr(c, "learn_count", 0) or 0)
                cr = int(getattr(c, "review_count", 0) or 0)
                sub_total += cn + cl + cr
            if did in exclude:
                return []
            if did == 0:
                # Root — emit kids only.
                return kid_rows
            if sub_total == 0:
                return []
            # Leaf name (after the last "::" — Anki uses "^_" internally but
            # the `name` field on the tree node is the display path; we want
            # just the leaf for the row, the depth carries the hierarchy).
            full = str(getattr(node, "name", "") or "")
            leaf = full.split("::")[-1]
            row = {
                "did": did,
                "name": leaf,
                "depth": depth,
                "new": n,
                "learn": l,
                "review": r,
            }
            return [row] + kid_rows

        out = visit(tree, -1)  # root depth -1 so top-level decks are 0
    except Exception:
        pass
    return out


def _build_congrats_payload() -> Dict[str, Any]:
    """Bundle everything congrats.js needs for the redesigned page."""
    did = 0
    name = ""
    try:
        did = int(mw.col.decks.get_current_id())
    except Exception:
        try:
            did = int(mw.col.decks.current()["id"])
        except Exception:
            pass
    try:
        if did:
            name = str(mw.col.decks.name(did) or "")
            # Anki uses "::" as the display separator; the leaf reads best.
            name = name.split("::")[-1] or name
    except Exception:
        pass
    stats = _finished_deck_stats(did) if did else {}
    today_total = 0
    try:
        s = _standing()
        today_total = int(s.get("today", 0) or 0)
    except Exception:
        pass
    return {
        "deckId": did,
        "deckName": name or "this deck",
        "thisDeck": stats.get("thisDeck", 0),
        "todayTotal": today_total,
        "timeSec": stats.get("timeSec", 0),
        "breakdown": stats.get("breakdown", {"again": 0, "hard": 0, "good": 0, "easy": 0}),
        "otherDecks": _filtered_deck_tree(did),
    }


def _is_congrats_url(url: str) -> bool:
    if not url:
        return False
    # Anki serves the Svelte congrats page at <serverURL>/congrats (with an
    # optional `#night` fragment). Match flexibly so a future path tweak
    # (e.g. /pages/congrats) doesn't break detection.
    low = url.lower()
    if low.endswith("/congrats") or low.endswith("/congrats/"):
        return True
    if "/congrats#" in low or "/congrats?" in low:
        return True
    if low.rstrip("/").endswith("/pages/congrats"):
        return True
    return False


def _is_graphs_url(url: str) -> bool:
    if not url:
        return False
    # Anki serves the SvelteKit stats page at <serverURL>/graphs (with an
    # optional `#night` fragment). The page is loaded by NewDeckStats via
    # `web.load_sveltekit_page("graphs")`.
    low = url.lower()
    if low.endswith("/graphs") or low.endswith("/graphs/"):
        return True
    if "/graphs#" in low or "/graphs?" in low:
        return True
    return False


def _inject_graphs_overrides(webview) -> None:
    """Style the SvelteKit graphs page with our palette + typography.

    The page uses Anki's `--canvas` / `--fg` / etc tokens; web/stats.css
    re-maps those to our `--rf-*` tokens. tokens.css must load first so
    the `--rf-*` variables are defined when stats.css consumes them."""
    cfg = _config()
    accent = cfg.get("accent", "#6c8cff")
    theme_pref = cfg.get("theme", "system")
    theme_attr = ""
    if theme_pref in ("light", "dark"):
        import json as _json
        theme_attr = (
            f"document.documentElement.dataset.rfTheme="
            f"{_json.dumps(theme_pref)};"
        )
    accent_style = (
        f"var st=document.createElement('style');"
        f"st.textContent=':root,body{{--rf-accent:{accent};}}';"
        f"document.head.appendChild(st);"
    )
    css_files = ["tokens.css", "theme.css", "stats.css"]
    css_inject = ""
    for f in css_files:
        css_inject += (
            f"(function(){{var l=document.createElement('link');"
            f"l.rel='stylesheet';l.href='{WEB}/{f}';"
            f"document.head.appendChild(l);}})();"
        )
    try:
        webview.eval(theme_attr + accent_style + css_inject)
    except Exception:
        pass


def on_webview_did_inject_style_into_page(webview) -> None:
    """Detect Anki's congrats / graphs Svelte pages after their dynamic
    styling finishes, then graft our redesign on top. Idempotent (the
    style/script appends bail if they already ran), so re-firing on theme
    changes is harmless."""
    try:
        url = webview.page().url().toString()
    except Exception:
        return
    if _is_graphs_url(url):
        _inject_graphs_overrides(webview)
        return
    if not _is_congrats_url(url):
        return
    try:
        import json as _json
        cfg = _config()
        standing = _build_standing_payload()
        # Dev override: if a `?did=N` query string is present on /congrats,
        # build the payload around that deck instead of the current one.
        # Lets the screenshot loop preview any deck without finishing it.
        override_did = 0
        try:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(url).query)
            override_did = int((qs.get("did") or ["0"])[0])
        except Exception:
            override_did = 0
        if override_did:
            try:
                mw.col.decks.select(override_did)
            except Exception:
                pass
        congrats = _build_congrats_payload()
        # Build a single eval that:
        #   1. seeds globals BEFORE the scripts run,
        #   2. injects our stylesheets (tokens, theme, logo, sidebar, congrats),
        #   3. injects sidebar.js + congrats.js as scripts.
        # Asset URLs are absolute relative paths served by Anki's media server
        # (`/_addons/<dir>/web/<file>`), which works for Svelte pages too.
        accent = cfg.get("accent", "#6c8cff")
        theme_pref = cfg.get("theme", "system")
        # Mirror webview_will_set_content's :root accent declaration so colors
        # land consistently here too.
        theme_attr = ""
        if theme_pref in ("light", "dark"):
            theme_attr = (
                f"document.documentElement.dataset.rfTheme={_json.dumps(theme_pref)};"
            )
        accent_style = (
            f"var st=document.createElement('style');"
            f"st.textContent=':root,body{{--rf-accent:{accent};}}';"
            f"document.head.appendChild(st);"
        )
        css_files = [
            "tokens.css", "theme.css", "logo.css", "sidebar.css", "congrats.css",
        ]
        js_files = ["sidebar.js", "congrats.js"]
        css_inject = ""
        for f in css_files:
            css_inject += (
                f"(function(){{var l=document.createElement('link');"
                f"l.rel='stylesheet';l.href='{WEB}/{f}';"
                f"document.head.appendChild(l);}})();"
            )
        js_inject = ""
        for f in js_files:
            js_inject += (
                f"(function(){{var s=document.createElement('script');"
                f"s.src='{WEB}/{f}';s.defer=false;"
                f"document.head.appendChild(s);}})();"
            )
        seed = (
            f"window.__baStandingData={_json.dumps(standing)};"
            f"window.__baCongratsData={_json.dumps(congrats)};"
        )
        webview.eval(theme_attr + seed + accent_style + css_inject + js_inject)
    except Exception:
        pass


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
    count breakdown on the right, and Edit + More icon buttons next to
    them (Anki's More menu already covers flag/mark/undo)."""
    name = html.escape(_current_deck_name() or "Studying")
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
    # Reviewer state is authoritative — `mw.reviewer.state` is "question" or
    # "answer". Pass it explicitly so JS can drive ease-selector visibility
    # without relying on `<hr id=answer>` (which Image Occlusion and any
    # back template that doesn't start with `{{FrontSide}}` don't emit).
    is_answer = False
    try:
        is_answer = getattr(mw.reviewer, "state", "question") == "answer"
    except Exception:
        pass
    import json as _json
    intervals_js = _json.dumps(intervals)
    is_answer_js = "true" if is_answer else "false"
    try:
        mw.reviewer.web.eval(
            f"window.__reforgeProgress && window.__reforgeProgress({pct},{done},{rem});"
            f"var $=function(id){{return document.getElementById(id);}};"
            f"var cn=$('ba-rv-c-new'),cl=$('ba-rv-c-learn'),cd=$('ba-rv-c-due');"
            f"if(cn)cn.textContent={new_n};if(cl)cl.textContent={learn_n};"
            f"if(cd)cd.textContent={rev_n};"
            f"window.__baSetEase && window.__baSetEase({intervals_js}, {default_ease}, {is_answer_js});"
        )
    except Exception:
        pass


def on_show_question(card) -> None:
    _push_progress()


def on_show_answer(card) -> None:
    _push_progress()


def on_reviewer_will_end() -> None:
    _session["total"] = 0


def on_reviewer_will_answer_card(proceed_ease, reviewer, card):
    """Kick off the press-feedback animation in the reviewer webview.
    Fires on both keyboard (1–4) and click paths since both flow through
    ``Reviewer._answerCard``. The eval is queued and runs before Anki's
    next-card ``_updateQA`` (which Anki also queues, after our handler
    returns), so the ghost + bloom appear immediately and keep playing
    while the new card slides in beneath. Pure side effect — we return
    ``proceed_ease`` unchanged."""
    try:
        proceed, ease = proceed_ease
        if proceed and reviewer is not None and getattr(reviewer, "web", None):
            reviewer.web.eval(
                f"window.__baEaseFx && window.__baEaseFx({int(ease)});"
            )
    except Exception:
        pass
    return proceed_ease


# --------------------------------------------------------------------------- #
# Register hooks
# --------------------------------------------------------------------------- #
gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
gui_hooks.deck_browser_will_render_content.append(on_deck_browser_will_render_content)
gui_hooks.deck_browser_did_render.append(on_deck_browser_did_render)
# Expand-all patch applied at import time; idempotent.
_patch_deck_tree_always_expanded()
# Svelte pages (congrats) bypass webview_will_set_content; this hook fires
# after every page's dynamic styling finishes, so we use it to detect the
# congrats URL and inject our redesign.
try:
    gui_hooks.webview_did_inject_style_into_page.append(
        on_webview_did_inject_style_into_page
    )
except Exception:
    pass
gui_hooks.state_did_change.append(on_state_did_change)
gui_hooks.reviewer_did_show_question.append(on_show_question)
gui_hooks.reviewer_did_show_answer.append(on_show_answer)
gui_hooks.reviewer_will_end.append(on_reviewer_will_end)
try:
    gui_hooks.reviewer_will_answer_card.append(on_reviewer_will_answer_card)
except Exception:
    pass

# Sidebar nav: route `ba:*` pycmds to the right mw methods + settings dialog.
gui_hooks.webview_did_receive_js_message.append(_on_js_message)


# Sidebar shortcuts — make the keys hinted in the sidebar (A, D, comma) do
# what the user expects.
#
# Anki binds `a`/`d`/`b`/`t`/`y`/`s` as global shortcuts in aqt/main.py.
# We can't unbind those (they're created as QShortcut objects on `mw` at
# startup), but we CAN intercept the functions they call. So:
#   - A → onAddCard:  patch to open our inline embed instead of the
#     standalone AddCards window.
#   - D → moveToState("deckBrowser"):  patch to also tear down the embed
#     if it's currently open, so the deck-browser UI actually comes back.
#   - Plain `,` → settings:  Anki has no binding for `,` at all, so add a
#     QShortcut for it.
def _setup_sidebar_shortcuts() -> None:
    # Patch onAddCard so the Tools menu, toolbar, and any code path that
    # goes through `mw.onAddCard()` opens the inline embed instead of the
    # standalone window.
    try:
        _orig_on_add_card = mw.onAddCard

        def _patched_on_add_card(*args, **kwargs):
            try:
                from . import addcard_embed
                addcard_embed.open_inline(mw)
            except Exception:
                _orig_on_add_card(*args, **kwargs)

        mw.onAddCard = _patched_on_add_card  # type: ignore[assignment]
    except Exception:
        pass

    # The "A" global shortcut is bound by aqt/main.py:setupKeys via
    # `("a", self.onAddCard)` — a bound-method reference captured BEFORE
    # we monkey-patch `mw.onAddCard`. The QShortcut holds the original
    # bound method, so the monkey-patch above doesn't catch it. Find the
    # QShortcut child of mw whose key is "A", disconnect its existing
    # activation, and reconnect to our embed opener.
    try:
        from aqt.qt import QShortcut, QKeySequence
        target_seq = QKeySequence("a")

        def _open_inline_a() -> None:
            try:
                from . import addcard_embed
                addcard_embed.open_inline(mw)
            except Exception:
                try:
                    from aqt import dialogs
                    dialogs.open("AddCards", mw)
                except Exception:
                    pass

        for sc in mw.findChildren(QShortcut):
            try:
                if sc.key().toString() == target_seq.toString():
                    try:
                        sc.activated.disconnect()
                    except Exception:
                        pass
                    sc.activated.connect(_open_inline_a)
            except Exception:
                continue
    except Exception:
        pass

    # Same dance for Browse (B key + mw.onBrowse).
    try:
        _orig_on_browse = mw.onBrowse

        def _patched_on_browse(*args, **kwargs):
            try:
                from . import browse_embed
                browse_embed.open_inline(mw)
            except Exception:
                _orig_on_browse(*args, **kwargs)

        mw.onBrowse = _patched_on_browse  # type: ignore[assignment]
    except Exception:
        pass

    try:
        from aqt.qt import QShortcut, QKeySequence
        target_seq_b = QKeySequence("b")

        def _open_inline_b() -> None:
            try:
                from . import browse_embed
                browse_embed.open_inline(mw)
            except Exception:
                try:
                    from aqt import dialogs
                    dialogs.open("Browser", mw)
                except Exception:
                    pass

        for sc in mw.findChildren(QShortcut):
            try:
                if sc.key().toString() == target_seq_b.toString():
                    try:
                        sc.activated.disconnect()
                    except Exception:
                        pass
                    sc.activated.connect(_open_inline_b)
            except Exception:
                continue
    except Exception:
        pass

    # Same dance for Stats (T key + mw.onStats). Shift+T (legacy
    # DeckStats) is left alone — it falls through to the standalone
    # window; only the modern NewDeckStats gets embedded.
    try:
        _orig_on_stats = mw.onStats

        def _patched_on_stats(*args, **kwargs):
            try:
                from aqt.utils import KeyboardModifiersPressed
                want_old = KeyboardModifiersPressed().shift
                if want_old:
                    _orig_on_stats(*args, **kwargs)
                    return
            except Exception:
                pass
            try:
                from . import stats_embed
                stats_embed.open_inline(mw)
            except Exception:
                _orig_on_stats(*args, **kwargs)

        mw.onStats = _patched_on_stats  # type: ignore[assignment]
    except Exception:
        pass

    try:
        from aqt.qt import QShortcut, QKeySequence
        target_seq_t = QKeySequence("t")

        def _open_inline_t() -> None:
            try:
                from . import stats_embed
                stats_embed.open_inline(mw)
            except Exception:
                try:
                    from aqt import dialogs
                    dialogs.open("NewDeckStats", mw)
                except Exception:
                    pass

        for sc in mw.findChildren(QShortcut):
            try:
                if sc.key().toString() == target_seq_t.toString():
                    try:
                        sc.activated.disconnect()
                    except Exception:
                        pass
                    sc.activated.connect(_open_inline_t)
            except Exception:
                continue
    except Exception:
        pass

    # Same dance for Preferences: patch mw.onPrefs so the Tools menu
    # entry (and any code path that goes through mw.onPrefs()) opens
    # the inline embed instead of the standalone window.
    try:
        _orig_on_prefs = mw.onPrefs

        def _patched_on_prefs(*args, **kwargs):
            try:
                _open_settings()
            except Exception:
                _orig_on_prefs(*args, **kwargs)

        mw.onPrefs = _patched_on_prefs  # type: ignore[assignment]
    except Exception:
        pass

    # Patch moveToState so leaving the deck-area context (e.g., D from
    # inside an inline embed) closes the embed before the navigation.
    try:
        _orig_move_to_state = mw.moveToState

        def _patched_move_to_state(state, *args, **kwargs):
            for mod in (
                "addcard_embed", "browse_embed", "stats_embed", "settings_embed",
            ):
                try:
                    from importlib import import_module
                    import_module("." + mod, __name__).close_inline()
                except Exception:
                    pass
            return _orig_move_to_state(state, *args, **kwargs)

        mw.moveToState = _patched_move_to_state  # type: ignore[assignment]
    except Exception:
        pass

    # Plain comma → settings. Anki uses Ctrl/Cmd+, for preferences (already
    # wired by _add_tools_menu_action); this adds the bare-key version that
    # the sidebar hints at.
    try:
        from aqt.qt import QShortcut, QKeySequence
        sc = QShortcut(QKeySequence(","), mw)
        sc.setAutoRepeat(False)
        sc.activated.connect(_open_settings)
    except Exception:
        pass

    # Cmd-K / Ctrl-K — Command palette. cmdk.js already binds the hotkey
    # inside every themed webview (deck browser, overview, reviewer), but
    # when focus is on a Qt-native widget (Add Cards embed editor field,
    # Browser table, a dialog) the webview never sees the keydown. Bind a
    # Qt-level shortcut on mw so the palette is reachable from anywhere.
    def _open_cmdk_palette() -> None:
        try:
            from . import cmdk as _cmdk
            _cmdk.open_from_outside("")
        except Exception:
            pass
    try:
        from aqt.qt import QShortcut, QKeySequence, Qt
        for seq in ("Ctrl+K", "Meta+K", "Ctrl+Shift+P", "Meta+Shift+P"):
            try:
                sc = QShortcut(QKeySequence(seq), mw)
                sc.setAutoRepeat(False)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(_open_cmdk_palette)
            except Exception:
                continue
    except Exception:
        pass


gui_hooks.main_window_did_init.append(_setup_sidebar_shortcuts)

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

# Inject an "Anki Design" tab into Anki's native Preferences dialog so every
# entry point — including the Tools-menu "Preferences…" / app-menu shortcut
# the user already knows — surfaces our settings alongside Anki's own.
try:
    from .settings import install_into_preferences
    install_into_preferences()
except Exception:
    pass

# Anki add-on dialog "Config" → open Preferences on the Anki Design tab
# instead of dumping raw JSON in front of the user.
try:
    mw.addonManager.setConfigAction(__name__, _open_settings)
except Exception:
    pass


def _add_tools_menu_action() -> None:
    try:
        from aqt.qt import QAction, QKeySequence, QShortcut, Qt
        act = QAction("Anki Design Settings…", mw)
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
            showWarning(f"Anki Design: failed to register settings shortcut: {e}")
        except Exception:
            pass


gui_hooks.main_window_did_init.append(_add_tools_menu_action)


# Add Card window redesign — separate module so the file stays focused.
try:
    from . import addcard as _addcard
    _addcard.register()
except Exception as _e:
    try:
        print(f"[anki-design] addcard register failed: {_e}", flush=True)
    except Exception:
        pass


# Inline reviewer editing — replaces the EditCurrent dialog.
try:
    from . import editreviewer as _editreviewer
    _editreviewer.register()
except Exception as _e:
    try:
        print(f"[anki-design] editreviewer register failed: {_e}", flush=True)
    except Exception:
        pass


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
    # Bust the AddCards editor webview too (covers both the standalone
    # AddCards window and our inline embed — both hold a live editor.web
    # that loads addcard.css/addcard.js from /_addons).
    try:
        from aqt import dialogs
        ac = dialogs._dialogs.get("AddCards", [None, None])[1]
        if ac is None:
            try:
                from . import addcard_embed
                ac = addcard_embed._state.get("addcards")
            except Exception:
                ac = None
        if ac is not None and getattr(ac, "editor", None):
            w = getattr(ac.editor, "web", None)
            if w is not None:
                views.append(w)
    except Exception:
        pass
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


def _dev_screenshot(request_path: str) -> None:
    """Runs on the Qt main thread. Reads the JSON request file, finds the
    target Qt widget (by window-title substring or "main"), grabs it as a
    PNG and writes to the requested output path. Always removes the request
    file. Used by the iterative-design screenshot loop."""
    import json
    try:
        with open(request_path) as fh:
            req = json.load(fh)
    except Exception:
        try:
            os.remove(request_path)
        except Exception:
            pass
        return
    try:
        os.remove(request_path)
    except Exception:
        pass
    out = req.get("out")
    target_title = (req.get("title") or "").lower()
    open_addcards = bool(req.get("open_addcards"))
    if not out:
        return
    try:
        from aqt.qt import QApplication, QTimer
        embed_add = bool(req.get("embed_add"))
        if open_addcards:
            try:
                if embed_add:
                    from . import addcard_embed
                    addcard_embed.open_inline(mw)
                else:
                    mw.onAddCard()
            except Exception:
                pass
        # Optional: pre-fill the fields with sample text so we can validate
        # how the design looks with content (vs the empty/placeholder state).
        fill_sample = bool(req.get("fill_sample"))
        try:
            QApplication.processEvents()
        except Exception:
            pass

        close_after = bool(req.get("close_after"))
        test_add = bool(req.get("test_add"))
        if test_add:
            # End-to-end smoke test: fill the editor, click Add, count
            # before/after, write the result to <out>.txt next to the PNG.
            from aqt.qt import QTimer as _TT

            def _smoke() -> None:
                # Simulate two consecutive adds to reproduce the user's
                # "second click crashes" report. Between clicks Anki
                # re-loads a fresh note; if our flow left dangling state
                # the second add should crash.
                log = []
                try:
                    from . import addcard_embed
                    ac = addcard_embed._state.get("addcards")
                    if ac is None:
                        return
                    col = ac.col
                    before = col.note_count()

                    def fill_and_click(tag: str) -> None:
                        ed = ac.editor
                        if ed and ed.note:
                            ed.note.fields[0] = f"front-{tag}"
                            if len(ed.note.fields) > 1:
                                ed.note.fields[1] = f"back-{tag}"
                            try:
                                ed.loadNote()
                            except Exception as e:
                                log.append(f"loadNote-{tag}={e}")
                        try:
                            from aqt.qt import QPushButton as _QPB
                            overlay = addcard_embed._state.get("overlay")
                            if overlay is not None:
                                for child in overlay.findChildren(_QPB):
                                    if child.objectName() == "ba-add":
                                        child.click()
                                        log.append(f"clicked-{tag}=ok")
                                        return
                            log.append(f"no_btn-{tag}")
                        except Exception as e:
                            import traceback
                            log.append(f"click-{tag}-err={e}")
                            try:
                                print(
                                    f"[smoke] click-{tag} failed:\n"
                                    f"{traceback.format_exc()}",
                                    flush=True,
                                )
                            except Exception:
                                pass

                    def _verify() -> None:
                        try:
                            after = col.note_count()
                            with open(out + ".txt", "w") as fh:
                                fh.write(
                                    f"before={before} after={after} "
                                    f"delta={after - before} "
                                    + " ".join(log) + "\n"
                                )
                        except Exception:
                            pass

                    fill_and_click("A")
                    # Wait LONGER than _safe_add's 700ms debounce before
                    # the second click — should be safe now.
                    _TT.singleShot(1200, lambda: fill_and_click("B"))
                    _TT.singleShot(2700, _verify)
                except Exception as e:
                    log.append(f"smoke_err={e}")
            _TT.singleShot(1200, _smoke)
        hover_add = bool(req.get("hover_add"))
        if hover_add:
            # Schedule on a short timer so it runs AFTER the embed has been
            # opened and the layout settled.
            from aqt.qt import QTimer as _QT

            def _hover_add() -> None:
                # Directly trigger the animated reveal — easier than
                # synthesizing a QEnterEvent that reliably reaches the
                # filter through Qt's offscreen-grab path. We give the
                # animation 250ms to finish before the grab happens.
                try:
                    from . import addcard_embed
                    from aqt.qt import QApplication, QTimer as _T2
                    ac = addcard_embed._state.get("addcards")
                    if ac is None:
                        return
                    hover = getattr(ac, "_ba_add_hover", None)
                    if hover is None:
                        return
                    hover._animate_in()
                    QApplication.processEvents()
                    # Force a paint pass after the animation completes
                    # so the next grab() captures the fully-faded-in state.
                    def _post() -> None:
                        try:
                            QApplication.processEvents()
                        except Exception:
                            pass
                    _T2.singleShot(250, _post)
                except Exception:
                    pass
            # Fire the hover early so the 180ms animation has time to
            # complete before the 2000ms grab.
            _QT.singleShot(1000, _hover_add)
        mw_width = req.get("mw_width")
        mw_height = req.get("mw_height")
        if isinstance(mw_width, int) and mw_width > 200:
            try:
                h = mw_height if isinstance(mw_height, int) and mw_height > 200 else mw.height()
                mw.resize(mw_width, h)
                QApplication.processEvents()
            except Exception:
                pass
        elif isinstance(mw_height, int) and mw_height > 200:
            try:
                mw.resize(mw.width(), mw_height)
                QApplication.processEvents()
            except Exception:
                pass
        trigger_shortcut = req.get("trigger_shortcut")  # e.g. "a"
        if trigger_shortcut:
            try:
                from aqt.qt import QShortcut, QKeySequence
                seq = QKeySequence(trigger_shortcut).toString()
                for sc in mw.findChildren(QShortcut):
                    try:
                        if sc.key().toString() == seq:
                            sc.activated.emit()
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        run_js = req.get("run_js")
        if run_js:
            try:
                web = getattr(mw, "web", None)
                if web is not None:
                    web.eval(str(run_js))
                    QApplication.processEvents()
            except Exception:
                pass

        def _grab() -> None:
            widget = None
            if target_title in ("main", "mw"):
                widget = mw
            else:
                for w in QApplication.topLevelWidgets():
                    try:
                        if not w.isVisible():
                            continue
                        title = (w.windowTitle() or "").lower()
                        if target_title and target_title in title:
                            widget = w
                            break
                    except Exception:
                        continue
            if widget is None:
                try:
                    with open(out + ".err", "w") as fh:
                        fh.write(f"no widget for title={target_title!r}\n")
                except Exception:
                    pass
                return
            # No raise_/activateWindow: widget.grab() renders offscreen via Qt's
            # backing store, so the window doesn't need focus or to be on top.
            # Surfacing it would steal focus from whatever the user is doing.
            try:
                QApplication.processEvents()
            except Exception:
                pass
            try:
                pix = widget.grab()
                pix.save(out, "PNG")
            except Exception as e:
                try:
                    with open(out + ".err", "w") as fh:
                        fh.write(f"grab failed: {e}\n")
                except Exception:
                    pass
            if close_after:
                try:
                    from . import addcard_embed
                    addcard_embed.close_inline()
                except Exception:
                    pass

        # Optionally inject sample text into editor fields so we can preview
        # the design with content. We schedule this *before* the grab delay.
        def _fill() -> None:
            try:
                from aqt import dialogs
                ac = dialogs._dialogs.get("AddCards", [None, None])[1]
                if ac is None:
                    try:
                        from . import addcard_embed
                        ac = addcard_embed._state.get("addcards")
                    except Exception:
                        ac = None
                if ac is None or not getattr(ac, "editor", None):
                    return
                ed = ac.editor
                if not getattr(ed, "note", None):
                    return
                samples = [
                    "What is the capital of France?",
                    "Paris — capital and most populous city.",
                    "Located on the Seine river.",
                ]
                for i in range(min(len(ed.note.fields), len(samples))):
                    ed.note.fields[i] = samples[i]
                ed.loadNote()
            except Exception:
                pass
        if fill_sample:
            QTimer.singleShot(400, _fill)
        # Optionally click the toolbar cog to verify the dropdown renders.
        click_cog = bool(req.get("click_cog"))
        def _click_cog() -> None:
            try:
                from aqt import dialogs
                ac = dialogs._dialogs.get("AddCards", [None, None])[1]
                if ac is None:
                    try:
                        from . import addcard_embed
                        ac = addcard_embed._state.get("addcards")
                    except Exception:
                        ac = None
                if ac is None or not getattr(ac, "editor", None):
                    return
                web = ac.editor.web
                # Anki's Svelte popup listens for a real PointerEvent — .click()
                # alone doesn't fire it. Dispatch pointerdown + mousedown + click
                # so the floating-ui library actually toggles the dropdown.
                web.eval("""
                  (function(){
                    var btn = document.querySelector('#settings button');
                    if (!btn) return;
                    function fire(name) {
                      var ev = new MouseEvent(name, {bubbles:true, cancelable:true, view:window, button:0});
                      btn.dispatchEvent(ev);
                    }
                    fire('pointerdown');
                    fire('mousedown');
                    fire('mouseup');
                    fire('click');
                  })();
                """)
            except Exception:
                pass
        if click_cog:
            QTimer.singleShot(700, _click_cog)
        # Optionally trigger the in-page note-type picker so the dropdown is
        # visible in the screenshot.
        click_type = bool(req.get("click_type"))
        def _click_type() -> None:
            try:
                from aqt import dialogs
                from PyQt6.QtWidgets import QPushButton as _QPB
                ac = dialogs._dialogs.get("AddCards", [None, None])[1]
                if ac is None:
                    return
                btns = ac.form.modelArea.findChildren(_QPB)
                if btns:
                    btns[0].click()
            except Exception:
                pass
        if click_type:
            QTimer.singleShot(800, _click_type)

        # Give the WebEngine view time to render (templates load async).
        # 1500ms is conservative; the editor.html bundle plus Svelte hydration
        # can take a beat after window construction.
        delay_ms = int(req.get("delay_ms", 1500))
        QTimer.singleShot(delay_ms, _grab)
    except Exception as e:
        try:
            with open(out + ".err", "w") as fh:
                fh.write(f"screenshot fatal: {e}\n")
        except Exception:
            pass


_SCREENSHOT_DIR = os.path.join(ADDON_SRC, ".context", "screenshot-requests")
_DUMP_DIR = os.path.join(ADDON_SRC, ".context", "dump-requests")


def _dev_dump(request_path: str) -> None:
    """Runs on the Qt main thread. Reads a {out, title} JSON request and
    dumps that window's web HTML to `out`. Used for design inspection."""
    import json
    try:
        with open(request_path) as fh:
            req = json.load(fh)
    except Exception:
        try:
            os.remove(request_path)
        except Exception:
            pass
        return
    try:
        os.remove(request_path)
    except Exception:
        pass
    out = req.get("out")
    target_title = (req.get("title") or "").lower()
    target_kind = (req.get("kind") or "").lower()
    if not out:
        return
    try:
        from aqt.qt import QApplication
        from aqt import dialogs
        try:
            from aqt.qt import QWebEngineView  # type: ignore
        except Exception:
            from PyQt6.QtWebEngineWidgets import QWebEngineView  # type: ignore
        web = None
        widget = None
        # 1) Specific kind: the AddCards editor (in our inline embed the
        # editor lives inside mw, so the topLevelWidgets lookup misses it
        # — find via the dialogs registry or the embed's stash).
        if target_kind == "addcards-editor":
            ac = dialogs._dialogs.get("AddCards", [None, None])[1]
            if ac is None:
                try:
                    from . import addcard_embed
                    ac = addcard_embed._state.get("addcards")
                except Exception:
                    ac = None
            if ac is not None and getattr(ac, "editor", None):
                web = ac.editor.web
        elif target_kind == "stats-embed":
            try:
                from . import stats_embed
                sd = stats_embed._state.get("stats")
                if sd is not None and getattr(sd, "form", None):
                    web = getattr(sd.form, "web", None)
            except Exception:
                pass
        # 2) `main`/`mw`: pin to mw.web. mw has multiple QWebEngineViews
        # (toolbarWeb, web, bottomWeb); findChild() returns the first one
        # constructed (usually the toolbar) which gives a useless 1-line
        # DOM.
        if web is None and target_title in ("main", "mw"):
            widget = mw
            web = getattr(mw, "web", None)
        # 3) Fall back to a top-level window matching `target_title`, then
        # pick the first QWebEngineView under it.
        if web is None:
            for w in QApplication.topLevelWidgets():
                try:
                    if not w.isVisible():
                        continue
                    title = (w.windowTitle() or "").lower()
                    if target_title and target_title in title:
                        widget = w
                        break
                except Exception:
                    continue
            if widget is None:
                with open(out, "w") as fh:
                    fh.write(f"<!-- no widget for title={target_title!r} -->")
                return
            web = widget.findChild(QWebEngineView)
        if web is None:
            with open(out, "w") as fh:
                fh.write("<!-- no QWebEngineView found -->")
            return
        def _write(html: str, out: str = out) -> None:
            try:
                with open(out, "w") as fh:
                    fh.write(html or "")
            except Exception:
                pass
        web.page().toHtml(_write)
    except Exception as e:
        try:
            with open(out, "w") as fh:
                fh.write(f"<!-- dump error: {e} -->")
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
        # Process pending screenshot requests (one per file in the dir).
        try:
            if os.path.isdir(_SCREENSHOT_DIR):
                for name in sorted(os.listdir(_SCREENSHOT_DIR)):
                    if not name.endswith(".json"):
                        continue
                    req = os.path.join(_SCREENSHOT_DIR, name)
                    try:
                        mw.taskman.run_on_main(
                            lambda p=req: _dev_screenshot(p)
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        # Process pending DOM-dump requests.
        try:
            if os.path.isdir(_DUMP_DIR):
                for name in sorted(os.listdir(_DUMP_DIR)):
                    if not name.endswith(".json"):
                        continue
                    req = os.path.join(_DUMP_DIR, name)
                    try:
                        mw.taskman.run_on_main(lambda p=req: _dev_dump(p))
                    except Exception:
                        pass
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
        target=_dev_watch, name="anki-design-devwatch", daemon=True
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
        elif cmd.startswith("mweval:"):
            js = cmd[7:]
            if getattr(mw, "web", None):
                mw.web.eval(js)
        elif cmd.startswith("mwecb:"):
            # Like mweval but writes the result to .context/eval_result.txt
            js = cmd[6:]
            out = os.path.join(ADDON_SRC, ".context", "eval_result.txt")
            if getattr(mw, "web", None):
                def _cb(result, _path=out):
                    try:
                        with open(_path, "w") as fh:
                            fh.write(str(result))
                    except Exception:
                        pass
                mw.web.evalWithCallback(js, _cb)
        elif cmd.startswith("congrats:"):
            # Dev-only: force-load Anki's congrats page for the given deck id.
            # Lets us preview the redesign against any deck without having
            # to drain its actual due queue first.
            try:
                did = int(cmd.split(":", 1)[1])
            except Exception:
                _dev_cmd_log("congrats: bad did")
                return
            try:
                mw.col.decks.select(did)
            except Exception:
                pass
            # Patch the scheduler's _is_finished check to True so Anki's
            # native Overview._renderPage takes its `_show_finished_screen`
            # branch and loads the Svelte congrats page naturally. Restored
            # after a short window so normal navigation isn't affected.
            try:
                sched = mw.col.sched
                orig = getattr(sched, "_orig_is_finished", None) or sched._is_finished
                sched._orig_is_finished = orig
                sched._is_finished = lambda: True  # type: ignore
                _dev_cmd_log("congrats: patched _is_finished")
                def _restore(orig=orig):
                    try:
                        sched._is_finished = orig  # type: ignore
                        _dev_cmd_log("congrats: restored _is_finished")
                    except Exception:
                        pass
                if QTimer is not None:
                    QTimer.singleShot(5000, _restore)
            except Exception as e:
                _dev_cmd_log(f"congrats patch err: {e!r}")
            try:
                mw.moveToState("overview")
            except Exception:
                pass
        elif cmd.startswith("dump_main:"):
            # Dump main webview HTML to a file (parallel to dump_card which
            # uses the reviewer webview). Argument is the output filename
            # under .context/.
            out_name = cmd.split(":", 1)[1].strip() or "main.html"
            out = os.path.join(ADDON_SRC, ".context", out_name)
            if getattr(mw, "web", None):
                js = (
                    "JSON.stringify({"
                    "html: document.documentElement.outerHTML,"
                    "url: location.href,"
                    "title: document.title"
                    "})"
                )
                def _cb(result, _path=out):
                    try:
                        with open(_path, "w") as fh:
                            fh.write(str(result))
                    except Exception:
                        pass
                mw.web.evalWithCallback(js, _cb)
        elif cmd.startswith("beval:"):
            # Eval JS in the reviewer's bottom toolbar webview.
            js = cmd[6:]
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "bottom", None) and getattr(rv.bottom, "web", None):
                rv.bottom.web.eval(js)
        elif cmd == "reload_page":
            # Force a full webview reload — addon JS changes don't propagate
            # via the CSS-only hot-reload; reload picks them up cleanly.
            try:
                if getattr(mw, "web", None) is not None:
                    mw.web.reload()
            except Exception as e:
                _dev_cmd_log(f"reload_page err: {e!r}")
        elif cmd == "decks_list":
            try:
                items = [(d.id, d.name) for d in mw.col.decks.all_names_and_ids()]
                _dev_cmd_log(f"decks: {items}")
                _dev_cmd_log(f"col path: {mw.col.path!r}")
                _dev_cmd_log(f"notes: {mw.col.db.scalar('SELECT COUNT(*) FROM notes')}")
                _dev_cmd_log(f"cards: {mw.col.db.scalar('SELECT COUNT(*) FROM cards')}")
            except Exception as e:
                _dev_cmd_log(f"decks err: {e!r}")
        elif cmd.startswith("create_test:"):
            _create_deck_inline(cmd.split(":", 1)[1])
            _dev_cmd_log(f"create_test ran for: {cmd.split(':',1)[1]!r}")
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
        elif cmd.startswith("unbury_deck:"):
            did = int(cmd.split(":", 1)[1])
            try:
                mw.col.sched.unbury_deck(did)
                _dev_cmd_log(f"unburied deck {did}")
            except Exception as e:
                _dev_cmd_log(f"unbury err: {e!r}")
        elif cmd == "dump_fit":
            out = os.path.join(ADDON_SRC, ".context", "fit.txt")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "web", None):
                js = (
                    "(function(){"
                    "var qa=document.getElementById('qa');"
                    "var card=qa?qa.querySelector('.card'):null;"
                    "var bodyCls=document.body?document.body.className:'';"
                    "var qaCS=qa?getComputedStyle(qa):null;"
                    "var cardCS=card?getComputedStyle(card):null;"
                    "return JSON.stringify({"
                    "bodyClasses:bodyCls,"
                    "isLong:document.body.classList.contains('ba-rv-long'),"
                    "qaScrollHeight:qa?qa.scrollHeight:null,"
                    "qaClientHeight:qa?qa.clientHeight:null,"
                    "qaPaddingTop:qaCS?qaCS.paddingTop:null,"
                    "qaPaddingBottom:qaCS?qaCS.paddingBottom:null,"
                    "cardFontSize:cardCS?cardCS.fontSize:null,"
                    "cardInlineFontSize:card?card.style.fontSize:null"
                    "});})()"
                )
                def _cb(r, _p=out):
                    try: open(_p,"w").write(str(r))
                    except Exception: pass
                rv.web.evalWithCallback(js, _cb)
        elif cmd == "dump_html":
            out = os.path.join(ADDON_SRC, ".context", "html.txt")
            rv = getattr(mw, "reviewer", None)
            w = mw.web if mw else None
            if w is not None:
                js = (
                    "JSON.stringify({"
                    "title:document.title,"
                    "url:location.href,"
                    "bodyHead:document.body?document.body.innerHTML.substring(0,500):'no body'"
                    "})"
                )
                def _cb(r, _p=out):
                    try: open(_p,"w").write(str(r))
                    except Exception: pass
                w.evalWithCallback(js, _cb)
        elif cmd == "dump_body_css":
            out = os.path.join(ADDON_SRC, ".context", "body_css.txt")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "web", None):
                js = (
                    "(function(){"
                    "var b=document.body;"
                    "var cs=getComputedStyle(b);"
                    "var links=Array.from(document.querySelectorAll('link[rel=stylesheet]'))"
                    ".map(function(l){return l.href;});"
                    "return JSON.stringify({"
                    "height:cs.height,maxHeight:cs.maxHeight,"
                    "minHeight:cs.minHeight,overflow:cs.overflow,"
                    "display:cs.display,gridTemplateRows:cs.gridTemplateRows,"
                    "links:links"
                    "});})()"
                )
                def _cb(r, _p=out):
                    try: open(_p,"w").write(str(r))
                    except Exception: pass
                rv.web.evalWithCallback(js, _cb)
        elif cmd == "dump_layout":
            out = os.path.join(ADDON_SRC, ".context", "layout.txt")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "web", None):
                js = (
                    "(function(){"
                    "function rect(el){if(!el)return null;"
                    "var r=el.getBoundingClientRect();"
                    "var cs=getComputedStyle(el);"
                    "return {x:r.x,y:r.y,w:r.width,h:r.height,"
                    "display:cs.display,visibility:cs.visibility,"
                    "overflow:cs.overflow,gridRow:cs.gridRow};}"
                    "return JSON.stringify({"
                    "viewport:{w:window.innerWidth,h:window.innerHeight},"
                    "body:rect(document.body),"
                    "qa:rect(document.getElementById('qa')),"
                    "head:rect(document.querySelector('.ba-rv-head')),"
                    "ease:rect(document.querySelector('.ba-rv-ease')),"
                    "scroll:{x:window.scrollX,y:window.scrollY,"
                    "docH:document.documentElement.scrollHeight}"
                    "});})()"
                )
                def _cb(r, _p=out):
                    try: open(_p,"w").write(str(r))
                    except Exception: pass
                rv.web.evalWithCallback(js, _cb)
        elif cmd == "dump_state":
            # Quick state probe: writes JSON to .context/state.txt with
            # window.__baReviewerState, ease.hidden, populated intervals,
            # whether `hr#answer` is present, and the rendered card type.
            out = os.path.join(ADDON_SRC, ".context", "state.txt")
            rv = getattr(mw, "reviewer", None)
            if rv and getattr(rv, "web", None):
                js = (
                    "(function(){"
                    "var ease=document.querySelector('.ba-rv-ease');"
                    "var qa=document.getElementById('qa');"
                    "var hr=qa?qa.querySelector('hr#answer'):null;"
                    "var wrap=qa?qa.querySelector('.ba-rv-answer'):null;"
                    "var bodyCls=document.body?document.body.className:'';"
                    "var intervals=Array.from(document.querySelectorAll("
                    "'.ba-rv-ease-int')).map(function(s){return s.textContent;});"
                    "var hidden=ease?ease.hidden:null;"
                    "var visibleKeys=Array.from(document.querySelectorAll("
                    "'.ba-rv-ease-key')).filter(function(b){return !b.hidden;})"
                    ".map(function(b){return b.getAttribute('data-ease')+':'"
                    "+(b.querySelector('.ba-rv-ease-int')||{textContent:''})"
                    ".textContent;});"
                    "return JSON.stringify({"
                    "jsState:window.__baReviewerState,"
                    "easeHidden:hidden,"
                    "hasHrAnswer:!!hr,"
                    "hasWrap:!!wrap,"
                    "bodyClasses:bodyCls,"
                    "intervals:intervals,"
                    "visibleKeys:visibleKeys"
                    "});})()"
                )
                def _cb(r, _p=out, _rv=rv):
                    try:
                        rv_state = getattr(_rv, "state", "?")
                        cid = _rv.card.id if _rv.card else "?"
                        open(_p, "w").write(
                            f"pyState={rv_state} card={cid}\njs={r}\n"
                        )
                    except Exception:
                        pass
                rv.web.evalWithCallback(js, _cb)
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
        elif cmd.startswith("browse_dims"):
            try:
                from aqt.qt import QFrame, QSplitter
                ov = None
                for f in mw.form.centralwidget.findChildren(QFrame):
                    if f.objectName() == "ba-browse-embed":
                        ov = f
                        break
                if ov is None:
                    _dev_cmd_log("browse_dims: no overlay")
                else:
                    _dev_cmd_log(
                        f"overlay: geom={ov.geometry().getRect()} "
                        f"size={ov.width()}x{ov.height()}"
                    )
                    sp = ov.findChild(QSplitter)
                    if sp is None:
                        _dev_cmd_log("browse_dims: no splitter")
                    else:
                        _dev_cmd_log(
                            f"splitter: sizes={sp.sizes()} "
                            f"count={sp.count()} handle_w={sp.handleWidth()} "
                            f"orient={sp.orientation()}"
                        )
                        for i in range(sp.count()):
                            w = sp.widget(i)
                            _dev_cmd_log(
                                f"  child[{i}]: {type(w).__name__} "
                                f"obj={w.objectName()!r} "
                                f"size={w.width()}x{w.height()} "
                                f"min={w.minimumWidth()} max={w.maximumWidth()}"
                            )
            except Exception as e:
                _dev_cmd_log(f"browse_dims err: {e!r}")
        elif cmd.startswith("browse_search:"):
            # Run a search in the embedded Browser and select the first row.
            try:
                from . import browse_embed
                br = browse_embed._state.get("browser")
                q = cmd.split(":", 1)[1]
                if br is not None:
                    br.form.searchEdit.lineEdit().setText(q)
                    br.onSearchActivated()
                    try:
                        idx = br.table._model.index(0, 0)
                        br.table._view.setCurrentIndex(idx)
                        br.table._view.selectionModel().select(
                            idx,
                            br.table._view.selectionModel().SelectionFlag.ClearAndSelect
                            | br.table._view.selectionModel().SelectionFlag.Rows,
                        )
                    except Exception as e:
                        _dev_cmd_log(f"select err: {e!r}")
                    _dev_cmd_log(f"browse_search: {q!r}")
            except Exception as e:
                _dev_cmd_log(f"browse_search err: {e!r}")
        elif cmd.startswith("browse_resize:"):
            try:
                from aqt.qt import QFrame, QSplitter
                parts = cmd.split(":", 1)[1].split(",")
                want = [int(p.strip()) for p in parts]
                ov = None
                for f in mw.form.centralwidget.findChildren(QFrame):
                    if f.objectName() == "ba-browse-embed":
                        ov = f
                        break
                if ov is not None:
                    sp = ov.findChild(QSplitter)
                    if sp is not None:
                        sp.setSizes(want)
                        # Fire splitterMoved to mimic a user drag (so the
                        # clamp handler runs as it would in real usage).
                        try:
                            sp.splitterMoved.emit(sp.sizes()[0], 1)
                        except Exception:
                            pass
                        _dev_cmd_log(
                            f"browse_resize: set {want} -> got {sp.sizes()}"
                        )
            except Exception as e:
                _dev_cmd_log(f"browse_resize err: {e!r}")
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
        target=_dev_cmd_watch, name="anki-design-dev-cmd", daemon=True
    )
    t.start()


gui_hooks.profile_did_open.append(_dev_start)
gui_hooks.profile_did_open.append(_dev_cmd_start)
gui_hooks.main_window_did_init.append(_dev_start)
gui_hooks.main_window_did_init.append(_dev_cmd_start)
gui_hooks.profile_will_close.append(_dev_shutdown)
