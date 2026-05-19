# Changelog

All notable changes to BetterAnki are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver-ish.

## [Unreleased]

## [0.1.0] — unreleased
### Added
- Base theme injected into the deck browser, overview, and reviewer.
- Contribution-style review-activity heatmap on the deck list, with
  today / streak / total summary.
- Reviewer progress bar with a `done / total` label.
- Config: `accent`, `show_heatmap`, `show_progress`, `heatmap_weeks`.
- Declares conflicts with Onigiri, Review Heatmap, and the Progress Bar
  add-on so Anki warns users instead of silently fighting them.

### Known issues
- Anki 25.09's deck-list DOM differs from the classic selectors; some rows
  are low-contrast until the theme selectors are tuned.
- Qt chrome (menus, native dialogs, sidebar) is not themed yet.
