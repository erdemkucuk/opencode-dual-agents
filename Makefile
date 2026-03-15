.PHONY: test test-fast down

# Full cycle: rebuild images, bring up, run tests, bring down
test: .venv
	docker compose build
	.venv/bin/pytest tests/ -v --no-rebuild

# Skip rebuild (faster when only config/prompts changed, not Dockerfile)
test-fast: .venv
	.venv/bin/pytest tests/ -v --no-rebuild

down:
	docker compose down --remove-orphans

# Run linter and check formatting
check: .venv
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

# Apply linting and formatting fixes
format: .venv
	.venv/bin/ruff check . --fix && .venv/bin/ruff format .

# Set up test venv (run once)
.venv:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
