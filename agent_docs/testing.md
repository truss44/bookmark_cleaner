# Testing Guidelines

Framework: **pytest** (config in `pyproject.toml`, `testpaths = ["tests"]`). Tests live in `tests/`.

## Run

```bash
pnpm test              # python3 -m pytest tests/ -v
pnpm test:coverage     # adds --cov=bookmark_cleaner --cov-report=term-missing
```

## Current coverage

`tests/test_consolidation.py` covers lone-folder consolidation, alphabetical sorting, and supporting helpers. Coverage targets the pure tree-manipulation functions (no network, no AI calls).

## Conventions

- **No network in unit tests.** URL-checking (`is_url_alive`, `check_all_bookmarks`) and AI calls (`_call_ai`, `build_ai_folder_structure`) must be mocked or skipped.
- Build `Folder`/`Bookmark` trees directly in tests — the constructors are simple (`bookmark_cleaner.py:98`).
- Test names: `test_<behavior>` describing the outcome, not the implementation.
- All tests must pass before merging (enforced by `.github/workflows/test.yml`).

## Lint gate

`pnpm lint` (flake8, line-length 79) runs in CI (`.github/workflows/lint.yml`). Fix all lint errors before requesting review.
