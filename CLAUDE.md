# CLAUDE.md

Notes for Claude agents working in this repo.

## Silent screenshots of any Anki state

This add-on ships a dev-only side channel (active when `.devmode` exists, i.e.
after `make dev`) that lets you (a) drive Anki to any state and (b) screenshot
that state — without the window ever surfacing or stealing focus from the
user.

The pipeline runs entirely on the running Anki's Qt main thread:

- `scripts/snap.sh <out.png> <title|"main"> [flags]` writes a JSON request to
  `.context/screenshot-requests/`. A watcher thread inside the add-on picks
  it up and calls `QWidget.grab()` on the matching top-level widget. `grab()`
  renders the widget tree through Qt's backing store — it does **not** raise,
  activate, or repaint visibly. The user sees nothing.
- `.context/cmd` is a one-line command file the watcher tails. Append to it
  with `echo "<cmd>" >> .context/cmd` to drive state. Supported commands
  (see `_dev_run_cmd` in `__init__.py`):
  - `decks` — back to deck browser
  - `overview:<deckId>` — open a deck's overview
  - `review:<deckId>` — start studying that deck
  - `show` — flip current card (Show Answer)
  - `ease:<1..4>` — rate current card (only valid in answer state)
  - `eval:<js>` / `beval:<js>` — run JS in the reviewer / bottom toolbar webview
  - `reload_page` — force `mw.web.reload()` (use after JS edits that the
    CSS-only hot-reload doesn't pick up)
  - `decks_list` — log all deck names to the cmd log
  - `create_test:<name>` — create a deck inline via `_create_deck_inline`
    (lets you exercise the sidebar's create path without UI input)
  - `state_info` — log current state to the cmd log (useful before grabbing)
- `scripts/dump.sh <out.html> <title>` does the same for HTML — dumps the
  matching window's `QWebEngineView` DOM to a file. Use this when you need to
  inspect computed styles or selectors instead of pixels.
  - Pass `main` (or `mw`) as the title to pin to `mw.web` specifically.
    `findChild(QWebEngineView)` on `mw` would otherwise return the toolbar
    webview, whose DOM is one useless line.

### Workflow

Pre-reqs: `make dev` once, then `make run` or `make demo` so Anki is alive
with the add-on linked.

```bash
# 1. Drive Anki to the state you want to capture (silent, no focus change).
echo "review:1745201234" >> .context/cmd     # start studying a deck
echo "show" >> .context/cmd                  # flip to answer
# (sleep a beat if you just changed state — WebEngine renders async)

# 2. Capture. snap.sh blocks up to 30s waiting for the PNG.
scripts/snap.sh out/reviewer-answer.png main

# 3. Or capture a non-main top-level (browser, add-card, preferences, etc.)
scripts/snap.sh out/addcard.png "add"        # title-substring match, case-insensitive
```

Pre-baked add-card states (handled by the request JSON, see `_dev_screenshot`):
`--open-addcards`, `--fill-sample`, `--click-cog`, `--hover-add`,
`--click-type`, `--embed-add`. These compose: `scripts/snap.sh out.png "add"
--open-addcards --fill-sample --click-cog`.

### Constraints

- The Anki window must **exist and not be minimized to the dock**. WebEngine
  suspends paints when fully iconified, so `grab()` of a minimized window
  yields a blank pixmap. Off-screen, occluded, or on-another-Space is fine.
- Python edits (anything outside `web/`) require an Anki restart — the
  add-on's Python is imported once at startup. `make demo-stop && make demo`
  is the fast way.
- The watcher only runs when `.devmode` is present. `make build` and the
  shipped `.ankiaddon` both exclude it, so end users never see this channel.
- Multiple worktrees run isolated Ankis simultaneously; each writes to its
  own `.context/` so requests can't cross-talk.

### When silent capture isn't an option

If a state genuinely can't be reached via `.context/cmd` (e.g. a Qt-native
dialog with no command hook), add a new command to `_dev_run_cmd` in
`__init__.py` rather than reaching for `osascript`/`screencapture -l` —
keeping all the navigation in-process avoids focus-stealing entirely.
