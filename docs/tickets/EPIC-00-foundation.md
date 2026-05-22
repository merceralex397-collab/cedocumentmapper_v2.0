# EPIC-00 Foundation

## Objective

Create the runnable project shell and development workflow.

## Deliverables

- Installable Python package under `src/`.
- `pytest`, `ruff`, and `mypy` configured.
- Application service entrypoint placeholder.
- CI-ready command list documented.

## Acceptance Criteria

- `pip install -r requirements-dev.txt` succeeds on Windows.
- `pytest` runs without collection errors.
- `python -m compileall src` succeeds.
- No parsing behavior is implemented in this ticket.

