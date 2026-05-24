# Changelog

All notable changes to Anki Design are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver-ish.

## [0.2.0] — 2026-05-24
### Added
- Cmd-K command palette: searches actions, decks, cards, and tags from
  anywhere (deck browser, overview, reviewer). Opens via the sidebar's
  "Search anything…" pill, ⌘K / Ctrl-K, or Cmd-Shift-P.
- Press-feedback animation on ease grading — soft radial bloom expands
  from the pressed key and the interval text fades in place.
- Redesigned congrats page (deck-finished): editorial header, single-
  sentence result, proportional accuracy bar with legend.
- Shared deck-list component: the home tree and the congrats "keep going"
  list render through the same module (`web/decklist.{js,css}`).
- `min_point_version: 250900` in `manifest.json` so older Ankis don't try
  to install a build they can't run.

### Fixed
- Ease-interval chips (`10 min`, `1 day`, etc.) now appear on Image
  Occlusion, Cloze, and any non-FrontSide card types — previously they
  only showed up when the back template included `{{FrontSide}}`.
- Deck-browser single-deck mode no longer renders the deck twice (the
  shared deck-list bails when the hero card owns the page).
- "Search anything…" pill renders with its background and border on the
  congrats page; Anki's Svelte/Bootstrap reset was wiping them.
- "Try custom study" link no longer duplicates on the congrats page when
  there are no other decks with work due.

## [0.1.0]
Initial AnkiWeb release.
### Added
- Base theme injected into the deck browser, overview, and reviewer.
- Contribution-style review-activity heatmap on the deck list, with
  today / streak / total summary.
- Reviewer progress bar with a `done / total` label.
- Themed Add Card, Browse, Stats, Preferences windows.
- Inline rename and a custom deck-options menu on multi-deck rows.
- Inline field editing in the reviewer (in place of the EditCurrent dialog).
- Config: `accent`, `show_heatmap`, `show_progress`, `heatmap_weeks`,
  `theme`, `density`, `sidebar_nav`, `heatmap_palette`,
  `reviewer_card_width`, `reviewer_font_size`, `font_serif`, `font_sans`.
- Declares conflicts with Onigiri, Review Heatmap, and the Progress Bar
  add-on so Anki warns users instead of silently fighting them.

### Known issues
- Anki 25.09's deck-list DOM differs from the classic selectors; some rows
  are low-contrast until the theme selectors are tuned.
- Qt chrome (menus, native dialogs, sidebar) is not themed yet.
