SRC := $(CURDIR)

# Per-worktree addon name (override with: make <t> NAME=whatever)
WT := $(notdir $(CURDIR))
ifeq ($(WT),anki-design)
NAME ?= anki-design
else
NAME ?= anki-design-$(WT)
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

.PHONY: dev undev run run-fg logs seed demo-seed demo-run demo demo-stop demo-clean deisolate clean-base build clean

# Demo base — fully separate from your real Anki and from any other dev base.
DEMO_NAME := anki-design-demo
DEMO_BASE := $(HOME)/Library/Application Support/Anki2-dev/$(DEMO_NAME)
DEMO_LINK := $(DEMO_BASE)/addons21/$(DEMO_NAME)

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

# SHOWCASE seed: generate a fake-but-realistic demo collection in a
# *separate* base ($(DEMO_BASE)). Never touches your real Anki or any other
# worktree's base. Loads 11 themed decks (USMLE pathology/pharm, Spanish,
# Japanese N5, periodic table, world + US capitals, etc.) with ~4 years of
# day-by-day revlog history so the heatmap, progress bar, and reviewer all
# have impressive content to show. Pass FORCE=1 to wipe a prior demo run.
demo-seed:
	@test -x "$(ANKI_PY)" || { echo "anki venv python not found at: $(ANKI_PY)"; exit 1; }
	@"$(ANKI_PY)" scripts/seed_demo.py $(if $(FORCE),--force,) --base "$(DEMO_BASE)"
	@mkdir -p "$(DEMO_BASE)/addons21"
	@rm -rf "$(DEMO_LINK)"
	@ln -s "$(SRC)" "$(DEMO_LINK)"
	@touch "$(SRC)/.devmode"
	@echo "demo  : symlinked $(NAME) into $(DEMO_BASE)"
	@echo "next  : make demo-run"

# Launch Anki against the demo base. Runs alongside your real Anki and
# alongside this worktree's regular dev instance (unique USER => unique
# single-instance key).
demo-run:
	@test -x "$(ANKI)" || { echo "anki not found at: $(ANKI)"; exit 1; }
	@test -f "$(DEMO_BASE)/User 1/collection.anki2" || { echo "no demo collection yet — run 'make demo-seed' first"; exit 1; }
	@USER="$(DEMO_NAME)" LOGNAME="$(DEMO_NAME)" nohup "$(ANKI)" -b "$(DEMO_BASE)" >"$(DEMO_BASE)/run.log" 2>&1 &
	@echo "launched demo Anki (base: $(DEMO_BASE))"
	@echo "log    : tail -f '$(DEMO_BASE)/run.log'"

# Quit any running demo Anki (matches only the demo base path, so this
# never touches your real Anki or other worktrees' dev instances).
demo-stop:
	@pids="$$(pgrep -f 'Anki2-dev/$(DEMO_NAME)' || true)"; \
	if [ -n "$$pids" ]; then \
	  echo "stopping demo Anki (pids: $$pids)"; \
	  kill $$pids 2>/dev/null; sleep 1; \
	  kill -9 $$(pgrep -f 'Anki2-dev/$(DEMO_NAME)' || true) 2>/dev/null || true; \
	else echo "(no demo Anki running)"; fi

# One-shot: stop any prior demo Anki, re-seed, launch.
demo: FORCE=1
demo: demo-stop demo-seed demo-run

# Remove the entire demo base. Only ever touches $(DEMO_BASE) — your real
# Anki and other worktree bases are untouched.
demo-clean: demo-stop
	@rm -rf "$(DEMO_BASE)"
	@echo "removed demo base: $(DEMO_BASE)"

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

# Produce dist/anki-design.ankiaddon for AnkiWeb upload.
build:
	@python3 build.py

clean:
	@rm -rf dist __pycache__
	@echo "cleaned."
