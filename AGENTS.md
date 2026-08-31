# AGENTS.md

## Project

Bookmark Cleaner — a single-file Python 3.10+ CLI (`bookmark_cleaner.py`) that parses exported browser bookmarks (Netscape HTML), removes dead links, and organizes unfoldered bookmarks into topic folders via AI or keyword rules. Outputs cleaned HTML for re-import.

## Tech Stack

- **Language**: Python 3.10+ (one ~2,500-line script, no internal modules)
- **Runtime deps**: `requests`, `urllib3`, `python-dotenv`; optional AI SDKs (openai/anthropic/google-genai/openrouter)
- **Tooling**: pnpm, Prettier (non-Python), flake8 + black/ruff (Python, line-length 79), pytest, husky + commitlint, semantic-release
- **CI**: GitHub Actions — test, lint, release (`.github/workflows/`)

## Critical Rules

1. All changes go in `bookmark_cleaner.py` — do not split into modules.
2. Keep line length ≤ 79 (flake8 enforces; black/ruff configured).
3. Use Conventional Commits (`feat`, `fix`, `perf`, `refactor`, `docs`, `chore`, etc.) — semantic-release parses them; commitlint enforces (header ≤ 150 chars).
4. Never commit the `.env` file or real API keys.
5. Run `pnpm test` and `pnpm lint` before requesting review — both must pass.
6. AI SDK imports must stay optional (try/except guarded) — the tool runs without any AI provider installed.
7. URL-check and AI functions must remain mockable — unit tests must not hit the network.
8. Preserve existing folder structures; only unfoldered bookmarks and lone folders are reorganized.

## Progressive Disclosure

Read the relevant file before starting work on a given area:

- `agent_docs/commands.md` — setup, run, test, lint, format, release commands
- `agent_docs/architecture.md` — pipeline stages, data model, code section map with `file:line` refs
- `agent_docs/ai_integration.md` — AI providers, env vars, key functions, fallback, adding a provider
- `agent_docs/testing.md` — pytest conventions, coverage scope, no-network rule
