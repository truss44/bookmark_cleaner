# Architecture Overview

Single-file Python CLI: **`bookmark_cleaner.py`** (~2,500 lines). No internal modules — the entire tool is one script. Entry point: `main()` at `bookmark_cleaner.py:2001`.

## Pipeline (run order)

1. **Parse** — `BookmarkParser` (HTMLParser subclass) reads Netscape Bookmark HTML into a `Folder` tree (`Bookmark`/`Folder` classes at `bookmark_cleaner.py:98`).
2. **Backup** — timestamped copy of the input is written before any mutation.
3. **URL check** — `check_all_bookmarks` (`:295`) tests URLs concurrently via `ThreadPoolExecutor`; `is_url_alive` (`:255`) does HEAD→GET fallback with SSL retry. Dead = 404/410/connection failure.
4. **Duplicate removal** — `remove_duplicate_bookmarks` (`:1389`); interactive prompt unless `--delete-duplicates`.
5. **Organize unfoldered** — `organize_unfoldered` (`:1308`) moves root-level bookmarks into topic folders via AI (default) or `TOPIC_RULES` keyword fallback.
6. **Consolidate lone folders** — `consolidate_lone_folders` (`:1525`) relocates single-bookmark folders; up to `--max-passes` (default 15).
7. **Merge similar folders** — `merge_similar_folders` (`:1733`) uses AI to collapse same-topic folders. Skipped with `--no-ai`.
8. **Flatten hollow folders** — `flatten_hollow_folders` (`:1760`) removes folders that only contain one subfolder.
9. **Sort** — `sort_tree` (`:1804`) alphabetical, folders before bookmarks, case-insensitive.
10. **Write** — `write_bookmarks` (`:1879`) emits Netscape Bookmark HTML.

## Browser auto-detect

When no input file is given, `find_browser_bookmark_files` (`:1892`) locates Edge/Chrome/Brave bookmark JSON; `convert_chromium_json_to_html` (`:1963`) converts to HTML.

## Data model

`Folder` holds child `Folder`s and `Bookmark`s. All tree operations are recursive over this structure. See `bookmark_cleaner.py:98-141`.

## AI vs. rule-based

Two parallel organization paths share the same tree API:
- **AI path** (default): single batched API call assigns all unfoldered bookmarks to a folder structure. See `agent_docs/ai_integration.md`.
- **Rule-based fallback** (`--no-ai` or no API key): `TOPIC_RULES` keyword matcher — first match wins. Edit `TOPIC_RULES` near top of `bookmark_cleaner.py` to customize.

## Configuration

- `.env` — AI provider keys/models (see `.env.example`). Loaded via `python-dotenv`.
- `pyproject.toml` — black/ruff line-length, pytest paths, semantic-release config.
- `.prettierrc` — formatting for non-Python files.
