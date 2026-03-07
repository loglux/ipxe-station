.PHONY: format backend-lint backend-test backend-check frontend-check pre-commit-check verify verify-e2e maybe-e2e quality

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

maybe-e2e:
	@if [ "$(RUN_E2E)" = "1" ]; then \
		if [ -z "$(E2E_BASE_URL)" ]; then \
			echo "E2E_BASE_URL is required when RUN_E2E=1"; \
			exit 2; \
		fi; \
		echo "Running E2E smoke suite against $(E2E_BASE_URL)"; \
		E2E_BASE_URL="$(E2E_BASE_URL)" npm --prefix frontend run test:e2e; \
	else \
		echo "Skipping E2E smoke suite (set RUN_E2E=1 E2E_BASE_URL=http://host:port/ui to enable)"; \
	fi

verify: backend-check frontend-check pre-commit-check maybe-e2e

verify-e2e:
	@if [ -z "$(E2E_BASE_URL)" ]; then \
		echo "E2E_BASE_URL is required, e.g. make verify-e2e E2E_BASE_URL=http://192.168.10.170:9021/ui"; \
		exit 2; \
	fi
	E2E_BASE_URL="$(E2E_BASE_URL)" npm --prefix frontend run test:e2e

quality: verify
