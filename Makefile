.PHONY: format backend-lint backend-test backend-check frontend-check quality

format:
	./.venv/bin/python -m black app
	./.venv/bin/python -m ruff check --fix app

backend-lint:
	./.venv/bin/python -m black --check app
	./.venv/bin/python -m ruff check app

backend-test:
	PYTHONPATH=. ./.venv/bin/pytest -q

backend-check: backend-lint backend-test

frontend-check:
	cd frontend && npm run lint && npm run build

quality: backend-check frontend-check
