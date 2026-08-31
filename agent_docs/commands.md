# Development Commands

Package manager: **pnpm** (declared in `package.json`). Python tooling is invoked through pnpm scripts.

## Setup

```bash
pnpm install                 # install node devDeps (prettier, husky, commitlint)
pip install -r requirements.txt   # python runtime deps
pip install pytest pytest-cov flake8   # python dev deps
```

## Run

```bash
python bookmark_cleaner.py favorites.html           # full run
pnpm start favorites.html                            # same, via pnpm
python bookmark_cleaner.py favorites.html --dry-run  # preview only
python bookmark_cleaner.py favorites.html --skip-check   # organize only
```

## Test

```bash
pnpm test                       # pytest -v
pnpm test:coverage              # pytest with coverage
python3 -m pytest tests/ -v     # direct
```

## Lint & Format

```bash
pnpm lint                       # flake8 (line-length 79) on bookmark_cleaner.py
pnpm format                     # prettier --write (md/json/yml/html/css/js/ts)
pnpm format:check               # prettier --check
```

Python formatting uses **black** / **ruff** (line-length 79, configured in `pyproject.toml`). Prettier does not touch `.py` files.

## Release

Versioning is automated via **semantic-release** (config in `pyproject.toml`), reading the version from `package.json`. Releases trigger on pushes to `main` (`.github/workflows/release.yml`). Use Conventional Commits — semantic-release parses them to determine bump type.

## Git Hooks

Husky (`commit-msg`) runs commitlint enforcing Conventional Commits: `header-max-length: 150`, `body-max-line-length: 200`.
