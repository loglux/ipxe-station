# AGENTS.md

## Project overview
iPXE Station is a Docker-deployed PXE/iPXE service.
Backend: FastAPI.
Current UI: Gradio tabs.
The project manages boot resources (Ubuntu versions/ISOs), generates iPXE menus, and provides validation/testing tools.

## Non-negotiable principles
- **Backend is the source of truth.**
- UI must be a thin layer: no business logic in UI callbacks.
- iPXE generation is deterministic and testable.
- Configuration must be schema-driven and backwards compatible.

## Key modules (current)
- `app/backend/ipxe_menu/*` — menu structures, templates, menu manager
- `app/backend/ipxe_manager.py` — validation/helpers for iPXE and menu-related logic
- `app/backend/boot_templates.py` — boot templates for common menu items
- `app/ui_tabs/*` — Gradio UI tabs (presentation layer only)

## Contracts and data model
- Prefer Pydantic models for persisted config and API I/O.
- If dataclasses are used internally (e.g., `iPXEEntry`), provide explicit conversion boundaries.
- Any new field must define:
  - storage format (JSON/YAML/db),
  - validation rules,
  - UI representation,
  - impact on generated iPXE output.

## QA and correctness
### Mandatory checks
- Semantic config validation (“config lint”):
  - duplicates, missing references, invalid combinations, invalid timeouts, etc.
- Unit tests for iPXE generation (golden/snapshot tests).
- Avoid relying only on manual PXE boot testing.

### Suggested tooling
- `ruff` for linting
- `pytest` for tests
- optional: `mypy` for critical backend modules

## UI guidelines (Gradio now, others later)
- UI must never directly assemble iPXE lines; it calls backend services.
- Provide:
  - structured editor (simple mode),
  - advanced editor (raw JSON/YAML or expert options),
  - live preview (dry-run) of iPXE output,
  - visible validation errors/warnings.

## UI migration rule (if Gradio becomes limiting)
If a UI migration is proposed (e.g. to FastAPI templates/HTMX or React/Vue):
- Keep backend endpoints stable first.
- Create a thin API layer used by both old and new UIs.
- Migrate screen-by-screen, not big bang.
- Add contract tests around the generator and config schema before migration.

## Change workflow
- Make small, reviewable patches.
- Update tests and validation with each schema change.
- Provide a short manual verification checklist for UI + generated iPXE.
