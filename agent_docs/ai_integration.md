# AI Provider Integration

The tool supports four optional AI providers for smart folder assignment. Provider is auto-detected from which env var is set. All SDK imports are optional (guarded by try/except at `bookmark_cleaner.py:65-84`).

## Providers

| Provider   | Env var(s)                          | Model env var      | Default model                  |
| ---------- | ----------------------------------- | ------------------ | ------------------------------ |
| OpenAI     | `OPENAI_API_KEY`                    | `OPENAI_MODEL`     | `gpt-5.4-nano`                 |
| Anthropic  | `ANTHROPIC_API_KEY`                 | `ANTHROPIC_MODEL`  | `claude-haiku-4-5`             |
| Gemini     | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | `GEMINI_MODEL`   | `gemini-3.1-flash-lite-preview`|
| OpenRouter | `OPENROUTER_API_KEY`                | `OPENROUTER_MODEL` | `openai/gpt-5.4-nano`          |

## Key functions

- `_get_ai_provider` (`bookmark_cleaner.py:370`) — returns `(provider, api_key, model)` or `None`.
- `_call_ai` (`:410`) — dispatches to the correct SDK; returns raw text response.
- `build_ai_folder_structure` (`:448`) — single batched call assigning all unfoldered bookmarks to folder paths.
- `build_ai_subfolder_map` / `_build_ai_subfolder_maps_batch` (`:583`/`:668`) — subfolder assignment for existing folders.
- `_ai_best_folders_for_bookmarks` (`:1472`) — picks best destination folder for lone-folder consolidation.
- `_ai_suggest_folder_merges` (`:1634`) — identifies same-topic folders to merge.

## Fallback behavior

If no API key is set, the API call fails, or `--no-ai` is passed, the tool falls back to the `TOPIC_RULES` keyword matcher (`_suggest_folder_path`, `:1266`). No crash — silent degradation.

## Adding a new provider

1. Add optional import block (try/except) near `bookmark_cleaner.py:65`.
2. Add env var detection in `_get_ai_provider`.
3. Add dispatch branch in `_call_ai`.
4. Document in `.env.example` and `README.md`.
