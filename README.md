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

This repo is the source of truth (`~/betteranki`).
`~/Library/Application Support/Anki2/addons21/betteranki` is a symlink to it.

1. Edit a file here.
2. **Fully quit and reopen Anki** (no hot-reload for add-on assets).
3. Look at the result.

`make dev` re-creates the symlink (e.g. after a fresh clone on another machine).

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
