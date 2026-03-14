.PHONY: test test-fast down

# Full cycle: rebuild images, bring up, run tests, bring down
test: .venv
	.venv/bin/pytest tests/ -v

# Skip rebuild (faster when only config/prompts changed, not Dockerfile)
test-fast: .venv
	.venv/bin/pytest tests/ -v --no-rebuild

down:
	docker compose down --remove-orphans

# Set up test venv (run once)
.venv:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
