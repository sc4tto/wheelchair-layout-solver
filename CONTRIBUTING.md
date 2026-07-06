# Contributing

1. Create a branch from `main`.
2. Install the development environment.
3. Add or update tests with every behavioral change.
4. Run:

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

5. Open a pull request describing:
   - the problem;
   - the chosen solution;
   - test evidence;
   - known limitations.

Geometry changes should include a small reproducible JSON example.
