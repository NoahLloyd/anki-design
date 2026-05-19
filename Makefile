SRC := $(CURDIR)

# Per-worktree addon name (override with: make <t> NAME=whatever)
WT := $(notdir $(CURDIR))
ifeq ($(WT),betteranki)
NAME ?= betteranki
else
NAME ?= betteranki-$(WT)
endif

# Each worktree gets its OWN isolated Anki base dir + addons21, so several
# Ankis run at once without touching each other or your real collection.
BASE := $(HOME)/Library/Application Support/Anki2-dev/$(NAME)
LINK := $(BASE)/addons21/$(NAME)

# Anki ships a uv-managed venv; this script runs Anki directly (bypassing the
# launcher) so we can pass -b and a per-instance USER. Override with ANKI=.
ANKI    ?= $(HOME)/Library/Application Support/AnkiProgramFiles/.venv/bin/anki
ANKI_PY ?= $(HOME)/Library/Application Support/AnkiProgramFiles/.venv/bin/python

# Real base, used only by `make seed` as a read source.
REAL_BASE := $(HOME)/Library/Application Support/Anki2

.PHONY: dev undev run run-fg logs seed deisolate clean-base build clean

# Symlink this worktree into its isolated base AND enable web/ hot-reload.
dev:
	@mkdir -p "$(BASE)/addons21"
	@rm -rf "$(LINK)"
	@ln -s "$(SRC)" "$(LINK)"
	@touch "$(SRC)/.devmode"
	@echo "addon  : $(NAME)"
	@echo "base   : $(BASE)"
	@echo "link   : $(LINK) -> $(SRC)"
	@echo "hotload: web/*.css and web/*.js reload live — no restart needed."
	@echo "next   : 'make run' (first run = empty collection; 'make seed' for real data)"

# Launch THIS worktree's Anki, backgrounded. Unique USER => unique
# single-instance key, so it runs alongside other worktrees' Ankis.
# Output is logged (NOT discarded) so add-on tracebacks are recoverable.
run:
	@test -x "$(ANKI)" || { echo "anki not found at: $(ANKI)"; echo "set ANKI=/path/to/.venv/bin/anki"; exit 1; }
	@mkdir -p "$(BASE)"
	@USER="$(NAME)" LOGNAME="$(NAME)" nohup "$(ANKI)" -b "$(BASE)" >"$(BASE)/run.log" 2>&1 &
	@echo "launched $(NAME) (base: $(BASE))"
	@echo "log    : make logs   (or: tail -f '$(BASE)/run.log')"

# Same, but in the foreground with output on the terminal — use this to see
# a crash/traceback live while debugging.
run-fg:
	@test -x "$(ANKI)" || { echo "anki not found at: $(ANKI)"; echo "set ANKI=/path/to/.venv/bin/anki"; exit 1; }
	@mkdir -p "$(BASE)"
	@USER="$(NAME)" LOGNAME="$(NAME)" "$(ANKI)" -b "$(BASE)"

# Tail this worktree's Anki log.
logs:
	@touch "$(BASE)/run.log"; tail -n 200 -f "$(BASE)/run.log"

# OPT-IN: copy your real collection into this worktree's base so the heatmap
# and decks are realistic. Snapshot only; media + add-ons excluded. The copied
# prefs21.db carries your AnkiWeb login + autoSync, so strip_sync.py clears it
# afterwards — the dev instance is then a fully local, inert copy that CANNOT
# sync to your real AnkiWeb account.
seed:
	@test -d "$(REAL_BASE)" || { echo "real base not found: $(REAL_BASE)"; exit 1; }
	@mkdir -p "$(BASE)"
	@rsync -a --delete \
		--exclude 'addons21/' --exclude 'backups/' --exclude 'logs/' \
		--exclude 'collection.media/' --exclude 'collection.media.db*' \
		"$(REAL_BASE)/" "$(BASE)/"
	@if [ -f "$(BASE)/prefs21.db" ]; then "$(ANKI_PY)" scripts/strip_sync.py "$(BASE)/prefs21.db"; else echo "strip_sync: no prefs21.db (skipped)"; fi
	@$(MAKE) -s dev
	@echo "seeded $(NAME): local copy, logged OUT of AnkiWeb (safe — cannot sync)."

# Make an existing seeded base safe without re-copying (clears AnkiWeb login).
deisolate:
	@test -f "$(BASE)/prefs21.db" || { echo "no prefs21.db at $(BASE)"; exit 1; }
	@"$(ANKI_PY)" scripts/strip_sync.py "$(BASE)/prefs21.db"

# Remove this worktree's symlink + disable its hot-reload (keeps the base).
undev:
	@rm -rf "$(LINK)"
	@rm -f "$(SRC)/.devmode"
	@echo "unlinked: $(NAME)"

# Nuke this worktree's isolated base entirely.
clean-base:
	@rm -rf "$(BASE)"
	@echo "removed base: $(BASE)"

# Produce dist/betteranki.ankiaddon for AnkiWeb upload.
build:
	@python3 build.py

clean:
	@rm -rf dist __pycache__
	@echo "cleaned."
