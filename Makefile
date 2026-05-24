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

# Real base, used by `make seed` as a read source and `make install` as the
# install target (your actual Anki, NOT the dev/demo bases).
REAL_BASE    := $(HOME)/Library/Application Support/Anki2
REAL_INSTALL := $(REAL_BASE)/addons21/anki-design

.PHONY: dev undev run run-fg logs seed demo-seed demo-run demo demo-rebuild demo-stop demo-clean demo-clean-cache demo-clean-all demo-cache-write demo-cache-restore demo-link deisolate clean-base build install clean

# Demo bases — each variant gets its own Anki base + its own golden cache.
# The cache lives under ~/Library/Caches so it's shared across all worktrees:
# seed once (slow), load anywhere (fast). The live base under Anki2-dev is
# the working copy Anki actually launches against.
#
# Override the variant per command: `make demo VARIANT=single`.
# Known variants are declared in scripts/seed_demo.py (VARIANTS dict).
VARIANT      ?= full
DEMO_NAME    := anki-design-demo-$(VARIANT)
DEMO_BASE    := $(HOME)/Library/Application Support/Anki2-dev/$(DEMO_NAME)
DEMO_LINK    := $(DEMO_BASE)/addons21/$(DEMO_NAME)
DEMO_CACHE   := $(HOME)/Library/Caches/anki-design-demo/$(VARIANT)
DEMO_PROFILE := User 1

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
# worktree's base. Each variant has its own deck mix and "today" backlog —
# see VARIANTS in scripts/seed_demo.py.
#
# Writes BOTH the live base (for immediate launch) AND a golden cache
# under $(DEMO_CACHE). The cache is what `make demo` copies from on
# subsequent runs across any worktree — seed once, load fast everywhere.
demo-seed: demo-stop
	@test -x "$(ANKI_PY)" || { echo "anki venv python not found at: $(ANKI_PY)"; exit 1; }
	@"$(ANKI_PY)" scripts/seed_demo.py --force --variant "$(VARIANT)" --base "$(DEMO_BASE)"
	@$(MAKE) -s demo-cache-write
	@$(MAKE) -s demo-link
	@echo "demo  : seeded variant '$(VARIANT)' into $(DEMO_BASE)"
	@echo "      : cached at $(DEMO_CACHE)"
	@echo "next  : make demo-run VARIANT=$(VARIANT)"

# Snapshot the seeded base into the cross-workspace cache. We grab the
# whole profile dir (collection + media + scheduling data); addons,
# logs, and prefs are skipped (those are per-launch state, not data).
demo-cache-write:
	@test -f "$(DEMO_BASE)/$(DEMO_PROFILE)/collection.anki2" || { echo "no collection at $(DEMO_BASE)/$(DEMO_PROFILE) — seed first"; exit 1; }
	@mkdir -p "$(DEMO_CACHE)"
	@rsync -a --delete \
		--exclude 'addons21/' --exclude 'logs/' --exclude 'run.log' \
		--exclude 'prefs21.db' --exclude '.DS_Store' \
		"$(DEMO_BASE)/$(DEMO_PROFILE)/" "$(DEMO_CACHE)/$(DEMO_PROFILE)/"

# Restore the cache to the live demo base (fast — no seeding). Used by
# `make demo` when the cache for the requested variant already exists.
demo-cache-restore:
	@test -d "$(DEMO_CACHE)/$(DEMO_PROFILE)" || { echo "no cache for variant '$(VARIANT)' at $(DEMO_CACHE) — run 'make demo-rebuild VARIANT=$(VARIANT)' first"; exit 1; }
	@mkdir -p "$(DEMO_BASE)/$(DEMO_PROFILE)"
	@rsync -a --delete \
		"$(DEMO_CACHE)/$(DEMO_PROFILE)/" "$(DEMO_BASE)/$(DEMO_PROFILE)/"

# Symlink this worktree's source into the demo base's addons21 so the
# add-on runs against THIS code (not a copy).
demo-link:
	@mkdir -p "$(DEMO_BASE)/addons21"
	@rm -rf "$(DEMO_LINK)"
	@ln -s "$(SRC)" "$(DEMO_LINK)"
	@touch "$(SRC)/.devmode"

# Launch Anki against the demo base. Runs alongside your real Anki and
# alongside this worktree's regular dev instance (unique USER => unique
# single-instance key).
demo-run:
	@test -x "$(ANKI)" || { echo "anki not found at: $(ANKI)"; exit 1; }
	@test -f "$(DEMO_BASE)/$(DEMO_PROFILE)/collection.anki2" || { echo "no demo collection yet — run 'make demo VARIANT=$(VARIANT)' first"; exit 1; }
	@USER="$(DEMO_NAME)" LOGNAME="$(DEMO_NAME)" nohup "$(ANKI)" -b "$(DEMO_BASE)" >"$(DEMO_BASE)/run.log" 2>&1 &
	@echo "launched demo Anki ($(VARIANT) variant, base: $(DEMO_BASE))"
	@echo "log    : tail -f '$(DEMO_BASE)/run.log'"

# Quit any running demo Anki for THIS variant (matches only this variant's
# base path, so other variants and your real Anki stay running).
demo-stop:
	@pids="$$(pgrep -f 'Anki2-dev/$(DEMO_NAME)' || true)"; \
	if [ -n "$$pids" ]; then \
	  echo "stopping demo Anki ($(VARIANT), pids: $$pids)"; \
	  kill $$pids 2>/dev/null; sleep 1; \
	  kill -9 $$(pgrep -f 'Anki2-dev/$(DEMO_NAME)' || true) 2>/dev/null || true; \
	else echo "(no demo Anki running for variant '$(VARIANT)')"; fi

# `make demo` — the fast path. Stops any prior demo for this variant,
# loads the cached snapshot into the live base, links the addon, launches.
# Falls through to `demo-rebuild` if no cache exists yet.
demo: demo-stop
	@if [ -d "$(DEMO_CACHE)/$(DEMO_PROFILE)" ]; then \
	  echo "demo  : loading cached '$(VARIANT)' (instant)"; \
	  $(MAKE) -s demo-cache-restore; \
	  $(MAKE) -s demo-link; \
	  $(MAKE) -s demo-run; \
	else \
	  echo "demo  : no cache for '$(VARIANT)' — seeding fresh (slow, one-time)"; \
	  $(MAKE) -s demo-seed; \
	  $(MAKE) -s demo-run; \
	fi

# `make demo-rebuild` — the slow path. Re-runs the seeder from scratch,
# overwrites the cache + live base, launches. Use this when you change
# seed_demo.py or want a different variant's golden state.
demo-rebuild: demo-stop demo-seed demo-run

# Remove the live demo base for this variant (keeps the cache so the next
# `make demo` is still instant).
demo-clean: demo-stop
	@rm -rf "$(DEMO_BASE)"
	@echo "removed live demo base: $(DEMO_BASE)"
	@echo "(cache at $(DEMO_CACHE) preserved — run 'make demo-clean-cache VARIANT=$(VARIANT)' to drop)"

# Drop just the cache for this variant.
demo-clean-cache:
	@rm -rf "$(DEMO_CACHE)"
	@echo "removed cache: $(DEMO_CACHE)"

# Drop ALL caches AND all live demo bases. The full nuke.
demo-clean-all:
	@for variant in single three full; do \
	  pids="$$(pgrep -f "Anki2-dev/anki-design-demo-$$variant" || true)"; \
	  [ -n "$$pids" ] && kill $$pids 2>/dev/null && sleep 1 && kill -9 $$pids 2>/dev/null || true; \
	  rm -rf "$(HOME)/Library/Application Support/Anki2-dev/anki-design-demo-$$variant"; \
	  rm -rf "$(HOME)/Library/Caches/anki-design-demo/$$variant"; \
	  echo "wiped $$variant"; \
	done

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

# Build + drop the addon into your REAL Anki (not the dev/demo bases).
# Removes ANY other folder under addons21/ whose manifest declares package
# "anki-design" first — otherwise an AnkiWeb-numeric-ID copy (e.g. 1809063985)
# and our install both register hooks, and the deck browser renders the hero
# + heatmap twice. If real Anki is open, quit and reopen it afterwards so the
# addon reloads.
install: build
	@test -f dist/anki-design.ankiaddon || { echo "build missing at dist/anki-design.ankiaddon"; exit 1; }
	@for d in "$(REAL_BASE)/addons21"/*/; do \
	  [ -d "$$d" ] || continue; \
	  [ -f "$$d/manifest.json" ] || continue; \
	  grep -q '"package":[[:space:]]*"anki-design"' "$$d/manifest.json" || continue; \
	  [ "$$d" = "$(REAL_INSTALL)/" ] && continue; \
	  echo "removing duplicate anki-design install: $$d"; \
	  rm -rf "$$d"; \
	done
	@rm -rf "$(REAL_INSTALL)"
	@mkdir -p "$(REAL_INSTALL)"
	@unzip -q dist/anki-design.ankiaddon -d "$(REAL_INSTALL)"
	@echo "installed: $(REAL_INSTALL)"
	@echo "next     : (re)start Anki to load this build"

clean:
	@rm -rf dist __pycache__
	@echo "cleaned."
