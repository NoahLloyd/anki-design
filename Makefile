ADDONS := $(HOME)/Library/Application Support/Anki2/addons21
LINK   := $(ADDONS)/reforge
SRC    := $(CURDIR)

.PHONY: dev build clean

# Re-create the dev symlink so Anki loads this working copy.
dev:
	@mkdir -p "$(ADDONS)"
	@rm -rf "$(LINK)"
	@ln -s "$(SRC)" "$(LINK)"
	@echo "linked: $(LINK) -> $(SRC)"
	@echo "now fully quit and reopen Anki to load changes."

# Produce dist/reforge.ankiaddon for AnkiWeb upload.
build:
	@python3 build.py

clean:
	@rm -rf dist __pycache__
	@echo "cleaned."
