# Anki Design

A from-scratch Anki UI redesign add-on. One cohesive thing you control,
replacing Onigiri + a separate progress bar + a separate heatmap.

Home: <https://anki.design> · AnkiWeb: <https://ankiweb.net/shared/info/1809063985>

**Requires Anki 25.09 or newer** (`min_point_version: 250900`). Older
versions refuse to install it rather than half-working.

## How it works

Anki renders the deck list, overview, and reviewer as Chromium web views.
Anki Design injects `web/theme.css` into them via the `webview_will_set_content`
hook, sets `--rf-accent` from config in `<head>`, renders the heatmap
server-side in `__init__.py` (from the `revlog` table) and appends it to the
deck browser, and drives a small reviewer progress-bar widget from Python.

No network calls, no bundled binaries — keeps AnkiWeb review trivial.

> Internal CSS/JS identifiers use the `rf-` prefix and `__reforgeProgress`
> bridge. That's a stable internal namespace, deliberately not renamed with
> the product, so a rebrand never risks breaking style/JS wiring.

## Layout

| Path | Purpose |
|---|---|
| `__init__.py` | hooks, masthead + heatmap generation, progress, config |
| `web/theme.css` | the deck-homepage "study ledger" redesign |
| `web/heatmap.css` / `.js` | heatmap styling; scroll-to-newest + tooltip |
| `web/toolbar.css` | top toolbar redesign (flat full-width header) |
| `web/reviewer.css` / `.js` | progress bar |
| `config.json` / `config.md` | user-facing settings + their help text (every feature has a switch) |
| `colors.py` | hex helpers shared by the web injection and the Qt palettes |
| `manifest.json` | name, version, `conflicts` with rival add-ons |
| `build.py` / `Makefile` | produce `dist/anki-design.ankiaddon` |
| `web/logo.css` / `web/fonts/` | the "anki.DESIGN" wordmark lockup |

## Settings

Everything opinionated can be switched off from **Tools → Anki Design
Settings…** (or the sidebar's Settings row); defaults are the current
behaviour. Highlights:

- **Deck list** — sub-decks on startup (Remember / Expanded / Collapsed;
  Remember uses Anki's own synced collapse flag), drag-to-move, the
  single-deck hero, click-to-study vs. Anki's overview page.
- **Reviewer** — card width / font size, *Style card content* (off keeps
  your note type's CSS untouched), interval chips vs. Anki's answer
  buttons, click-to-reveal, press feedback, in-place editing, progress bar.
- **Windows** — command palette, inline Add / Browse / Stats / Preferences,
  the redesigned Add window, the finished-deck page, quiet sync.
- **Appearance** — theme, accent, background (Paper / White / custom and
  Ink / Black / custom), density, fonts.

Moving decks: drag a row onto another deck to nest it, drop it on the
top-level zone to un-nest it, or use **Move to…** in the deck's gear menu.
See `config.md` for the raw keys.

## Dev loop

Each git worktree gets a **fully isolated Anki**: its own base directory, its
own `addons21/` (so no add-on conflicts), and a unique single-instance key —
so multiple worktrees' Ankis run **simultaneously**.

Per worktree, once:

```
make dev        # symlink this worktree into its isolated base + hot-reload
make run        # launch THIS worktree's Anki (runs alongside the others)
```

Then:

1. Edit `web/*.css`, `web/*.js`, or the heatmap HTML.
2. **It reloads live** — no Anki restart. CSS updates in place with no
   flicker; the visible screen re-renders for JS / heatmap changes.
3. Editing `__init__.py` (Python logic / hooks) still needs a restart of
   *that* instance — Anki imports add-on Python once at startup.

Real data (optional):

```
make seed       # copy your real collection into this worktree's base
```

`make run` on a fresh base starts with an **empty collection** (fine for
theme/CSS work; the heatmap is empty). `make seed` rsyncs your real
`Anki2/` collection in (media + add-ons excluded, so it stays light).
**Do not sync a seeded instance** — it shares your AnkiWeb account and
syncing a copied collection can push unwanted merges upstream.

Showcase data (no real collection involved):

```
make demo                       # launch the default (full) variant
make demo VARIANT=single        # or VARIANT=three / VARIANT=full
make demo-rebuild VARIANT=full  # rebuild a variant's cache (slow, one-time)
make demo-stop                  # quit the current variant's demo Anki
```

`make demo` runs against a *separate* `anki-design-demo-<variant>` base
under `Anki2-dev/`. Three variants are defined in `scripts/seed_demo.py`:

- `single` — one Spanish deck (~450 cards, ~200 due today).
- `three` — Spanish + Japanese N5 + Med pathology (~420 cards, ~190 due).
- `full` — all 17 decks (~1100 cards, ~440 due). Default.

Each variant has a golden cache at `~/Library/Caches/anki-design-demo/<variant>/`
that's **shared across worktrees** — seed once anywhere, launch instantly
everywhere. `make demo` restores from cache in ~1s; if no cache exists yet
it falls through to `demo-rebuild` automatically. Re-run `demo-rebuild` only
after you change `scripts/seed_demo.py` and want the cache regenerated.

Cleanup:

- `make demo-clean` — drop a variant's live base (keeps the cache).
- `make demo-clean-cache` — drop a variant's cache.
- `make demo-clean-all` — nuke every variant's cache + base.

Your real `Anki2/` collection is **never opened** by any of these — the
seeder refuses any target inside your real base.

How parallelism works:

- `make run` launches Anki's bundled venv binary directly with
  `-b <isolated base>` and a per-worktree `USER` env. Anki keys its
  single-instance lock on the username, so a unique `USER` lets instances
  coexist; `open -a Anki` would only refocus the running one.
- Bases live in `~/Library/Application Support/Anki2-dev/<NAME>` and persist
  between runs (profile/settings stick).

Other targets:

- `make undev` — remove this worktree's symlink + `.devmode` (keeps the base).
- `make clean-base` — delete this worktree's isolated base entirely.
- A watcher thread (web/ mtimes, ~0.5s poll, stdlib only) runs only when
  `.devmode` is present; `make build` / `.gitignore` exclude `.devmode`, so
  shipped installs never start it.
- `make dev NAME=foo` / `make run ANKI=/path/to/.venv/bin/anki` override
  the addon name / Anki binary.

## Building for AnkiWeb

```
make build      # -> dist/anki-design.ankiaddon
```

The `.ankiaddon` is a zip with files at the root; `__pycache__`, `meta.json`,
`.git`, and dev tooling are excluded automatically.

## Submitting to AnkiWeb

1. Log in to <https://ankiweb.net> with your sync account.
2. Go to the shared add-ons area and choose to upload a new add-on.
3. Fill in title, tags, description, and a support page URL (the GitHub repo /
   issues link is fine).
4. Upload `dist/anki-design.ankiaddon`.
5. The first upload creates the listing and assigns a **numeric ID** — that
   becomes the install code *and* the installed folder name. Anki Design already
   resolves its own folder at runtime, so this is safe.
6. Later releases: bump `human_version` in `manifest.json`, update
   `CHANGELOG.md`, `make build`, re-upload to the same listing.

### Before the first submission
- Confirm the minimum Anki version you want to support and add
  `min_point_version` to `manifest.json`. Find the current number from Anki's
  debug console: `from anki.utils import point_version; point_version()`.
- Sanity-check on at least one older supported Anki version.

## License

MIT — see `LICENSE`.

## Roadmap

- Theme the remaining Qt chrome (menus, native dialogs) via Qt stylesheets.
- Interactive heatmap (click a day to see that day's reviews).
- Support for Anki versions before 25.09.
