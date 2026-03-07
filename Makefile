.PHONY: format backend-lint backend-test backend-check frontend-check pre-commit-check verify quality

format:
	./.venv/bin/python -m black app
	./.venv/bin/python -m ruff check --fix app

backend-lint:
	./.venv/bin/python -m black --check app
	./.venv/bin/python -m ruff check app

backend-test:
	IPXE_DATA_ROOT=/tmp/ipxe-test PYTHONPATH=. ./.venv/bin/pytest -q

backend-check: backend-lint backend-test

frontend-check:
	cd frontend && npm run lint && npm run test && npm run build

pre-commit-check:
	./.venv/bin/pre-commit run --all-files

verify: backend-check frontend-check pre-commit-check

quality: verify
