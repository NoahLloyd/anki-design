# BetterAnki

A from-scratch Anki UI redesign add-on. One cohesive thing you control,
replacing Onigiri + a separate progress bar + a separate heatmap.

## How it works

Anki renders the deck list, overview, and reviewer as Chromium web views.
BetterAnki injects `web/theme.css` into them via the `webview_will_set_content`
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
| `__init__.py` | hooks, heatmap generation, progress logic, config |
| `web/theme.css` | the redesign — the main file to iterate on |
| `web/heatmap.css` | heatmap styling |
| `web/reviewer.css` / `.js` | progress bar |
| `config.json` / `config.md` | user-facing settings + their help text |
| `manifest.json` | name, version, `conflicts` with rival add-ons |
| `build.py` / `Makefile` | produce `dist/betteranki.ankiaddon` |

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
make build      # -> dist/betteranki.ankiaddon
```

The `.ankiaddon` is a zip with files at the root; `__pycache__`, `meta.json`,
`.git`, and dev tooling are excluded automatically.

## Submitting to AnkiWeb

1. Log in to <https://ankiweb.net> with your sync account.
2. Go to the shared add-ons area and choose to upload a new add-on.
3. Fill in title, tags, description, and a support page URL (the GitHub repo /
   issues link is fine).
4. Upload `dist/betteranki.ankiaddon`.
5. The first upload creates the listing and assigns a **numeric ID** — that
   becomes the install code *and* the installed folder name. BetterAnki already
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

- Tune deck-list selectors for Anki 25.09's DOM (current low-contrast rows).
- Theme the Qt chrome (menus, dialogs, sidebar) via Qt stylesheets.
- Stats / Browse / Add windows.
- Interactive heatmap (click a day to see that day's reviews).
