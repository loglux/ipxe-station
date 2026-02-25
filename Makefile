.PHONY: format backend-lint backend-test backend-check frontend-check quality

format:
	./.venv/bin/python -m black app
	./.venv/bin/python -m isort app

backend-lint:
	./.venv/bin/python -m black --check app
	./.venv/bin/python -m isort --check-only app
	./.venv/bin/python -m flake8 --jobs=1 app

backend-test:
	PYTHONPATH=. ./.venv/bin/pytest -q

backend-check: backend-lint backend-test

frontend-check:
	cd frontend && npm run lint && npm run build

quality: backend-check frontend-check
