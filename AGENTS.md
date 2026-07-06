# AGENTS.md

## Project goal
Build a deterministic and testable toolkit for wheelchair pose validation,
path planning, functional accessibility checks, and layout optimization.

## Non-negotiable rules
- Geometry calculations must be deterministic.
- AI output must never replace collision checks or path validation.
- All public functions require type hints and docstrings.
- New geometry or planning behavior requires tests.
- Use metres internally.
- Do not silently repair malformed input geometry.
- Preserve backward compatibility of the JSON schema where practical.

## Commands
- Install: `python -m pip install -e ".[dev,cad,api]"`
- Test: `pytest`
- Lint: `ruff check .`
- Format: `ruff format .`
- Type check: `mypy src`
- Build: `python -m build`

## First development priorities
1. Reliable collision checker.
2. CAD import and schema validation.
3. Functional target zones.
4. A* state-space planning.
5. Layout optimization and robustness.
