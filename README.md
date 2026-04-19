# Microsoft Edge Favorites Cleaner & Organizer

A Python command-line tool that parses your exported Edge favorites, removes dead links, and automatically organizes unfoldered bookmarks into topic-based folders — producing a clean HTML file ready to import back into Edge.

---

## Features

- **Automatic backup** — timestamped copy of the original is always created before any changes
- **Dead link removal** — checks every URL concurrently; removes 404s, 410s, and unreachable sites
- **Smart organization** — loose (unfoldered) bookmarks are matched against topic rules and moved into relevant folders and subfolders
- **Singleton consolidation** — folders with only one bookmark are detected and that bookmark is moved to the most relevant existing folder; empty folders are deleted
- **Alphabetical sorting** — all folders and bookmarks are sorted alphabetically after organization (folders first, then bookmarks)
- **Edge-compatible output** — writes standard Netscape Bookmark HTML that Edge imports natively
- **Detailed logging** — per-URL results written to a log file for review
- **Dry-run mode** — preview all changes without writing any files

---

## Requirements

- Python 3.10 or higher
- `requests` and `python-dotenv` libraries
- An API key from one of the following AI providers:
  - **OpenAI** (free to create at [platform.openai.com](https://platform.openai.com/api-keys))
  - **Anthropic/Claude** (free to create at [console.anthropic.com](https://console.anthropic.com/settings/keys))
  - **Google Gemini** (free to create at [aistudio.google.com](https://aistudio.google.com/app/apikey))
  - **OpenRouter** (free to create at [openrouter.ai](https://openrouter.ai/settings/keys))

The run scripts will automatically install the appropriate AI SDK based on which API key you configure.

---

## Setup

### API Key (.env)

The script uses AI to intelligently assign your bookmarks to folders. Choose one of the following providers and configure your API key.

1. Copy the example env file:

   ```bash
   # Windows (PowerShell)
   Copy-Item .env.example .env

   # macOS / Linux
   cp .env.example .env
   ```

2. Open `.env` and configure your chosen provider (uncomment the relevant section):

   **Option 1: OpenAI**

   ```
   OPENAI_API_KEY=sk-proj-...
   OPENAI_MODEL=gpt-5.4-nano
   ```

   **Option 2: Anthropic/Claude**

   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ANTHROPIC_MODEL=claude-haiku-4-5
   ```

   **Option 3: Google Gemini**

   ```
   GEMINI_API_KEY=AIza...
   GEMINI_MODEL=gemini-3.1-flash-lite-preview
   ```

   **Option 4: OpenRouter**

   ```
   OPENROUTER_API_KEY=sk-or-...
   OPENROUTER_MODEL=openai/gpt-5.4-nano
   ```

   Configuration details:
   - **OpenAI**: Model defaults to `gpt-5.4-nano`. You can use any OpenAI model such as `gpt-4o`, `gpt-4o-mini`, `o1-mini`, etc.
   - **Anthropic**: Model defaults to `claude-haiku-4-5`. You can use any Claude model.
   - **Gemini**: Model defaults to `gemini-3.1-flash-lite-preview`. You can also use `GOOGLE_API_KEY` as an alternative to `GEMINI_API_KEY`.
   - **OpenRouter**: Model defaults to `openai/gpt-5.4-nano`. OpenRouter provides access to hundreds of models from various providers via a single API. See [openrouter.ai/models](https://openrouter.ai/models) for available models.

3. The run scripts (`run.ps1` / `run.sh`) will automatically install the appropriate AI SDK based on which API key you configure, and the Python script will load `.env` automatically via `python-dotenv`.

> If no API key is found, the script falls back to built-in keyword-based folder rules automatically — no crash, no interruption.

### Code Formatting

This project uses Prettier for code formatting. The following npm scripts are available:

```bash
# Install dependencies (first time only)
npm install

# Format all supported files (.md, .json, .yml, .yaml, .html, .css, .js, .ts)
npm run format

# Check formatting without making changes
npm run format:check
```

Configuration is in `.prettierrc`. Note: Prettier does not format Python files; for Python code formatting, use Black or your preferred Python formatter.

### Python Testing

This project uses [pytest](https://pytest.org/) for testing. Tests live in the `tests/` directory.

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
npm test

# Or run directly
python3 -m pytest tests/ -v

# Run with coverage report
npm run test:coverage

# Or run directly
python3 -m pytest tests/ -v --cov=bookmark_cleaner --cov-report=term-missing
```

Tests cover singleton folder consolidation, alphabetical sorting, and all supporting helper functions. All tests must pass before merging PRs.

### Python Linting

This project uses [flake8](https://flake8.pycqa.org/) for Python linting. To lint the Python code:

```bash
# Run the linter
npm run lint

# Or run directly
python3 -m flake8 bookmark_cleaner.py
```

The lint script is configured in `package.json` and runs flake8 with a maximum line length of 79 characters. All lint errors must be fixed before merging PRs.

## Quick Start

```bash
python bookmark_cleaner.py favorites.html
```

Or using npm (after running `npm install`):

```bash
npm start favorites.html
```

This will:

1. Create a timestamped backup of `favorites.html`
2. Check all URLs for availability
3. Remove dead links
4. Organize unfoldered bookmarks into topic folders
5. Write `favorites_cleaned_<timestamp>.html`

---

## Usage

```
python bookmark_cleaner.py <input_file> [options]
```

### Options

| Option          | Default                            | Description                                                   |
| --------------- | ---------------------------------- | ------------------------------------------------------------- |
| `--output FILE` | `<input>_cleaned_<timestamp>.html` | Path for the output file                                      |
| `--threads N`   | `20`                               | Number of concurrent URL check workers                        |
| `--timeout N`   | `10`                               | Per-URL timeout in seconds                                    |
| `--dry-run`     | off                                | Preview changes without writing any files                     |
| `--skip-check`  | off                                | Skip URL checks; organize only                                |
| `--no-ai`       | off                                | Skip AI folder assignment; use built-in keyword rules instead |
| `--log FILE`    | `bookmark_cleaner.log`             | Path for the detailed per-URL log                             |

### Examples

**Standard full run** (URL check + organize):

```bash
python bookmark_cleaner.py favorites.html
```

**Slower or throttled connections** — reduce threads and increase timeout:

```bash
python bookmark_cleaner.py favorites.html --threads 10 --timeout 20
```

**Organize only, skip URL checks** (much faster):

```bash
python bookmark_cleaner.py favorites.html --skip-check
```

**Preview everything without writing files**:

```bash
python bookmark_cleaner.py favorites.html --dry-run
```

**Specify a custom output path**:

```bash
python bookmark_cleaner.py favorites.html --output my_cleaned_favorites.html
```

**Skip AI organization, use built-in keyword rules instead**:

```bash
python bookmark_cleaner.py favorites.html --no-ai
```

**Full options example**:

```bash
python bookmark_cleaner.py favorites.html \
  --output clean.html \
  --threads 15 \
  --timeout 15 \
  --log results.log
```

---

## Exporting Favorites from Edge

1. Open Microsoft Edge
2. Go to **Settings** (⋯ menu) → **Favorites** → **⋯ menu** → **Export favorites**
3. Save the `.html` file to your working directory
4. Run the script against that file

---

## Importing the Output into Edge

1. Open Microsoft Edge
2. Go to **Settings** (⋯ menu) → **Favorites** → **⋯ menu** → **Import favorites**  
   _or navigate to:_ `edge://settings/importData`
3. Under **Import from**, choose **Favorites or bookmarks HTML file**
4. Select the output file produced by this script
5. Click **Import**

> **Tip:** Before importing, you may want to clear or rename your existing favorites bar to avoid duplicates.

---

## How URL Checking Works

The script uses concurrent HTTP requests to test each bookmark:

1. Sends a `HEAD` request (lightweight — no body download)
2. If the server returns `405 Method Not Allowed` or `403 Forbidden`, falls back to a `GET` request
3. If SSL certificate errors are encountered, retries with certificate verification disabled (common on older sites)
4. Marks a bookmark as **dead** if the response code is `404` or `410`, or if the connection fails entirely (timeout, DNS failure, connection refused)
5. All other responses (including `301`/`302` redirects that resolve successfully) are treated as **alive**

Non-HTTP URLs (e.g. `javascript:`, `chrome://`, `file://`) are skipped and kept.

> **Note on false positives:** Some sites block automated requests and return errors even when the page is live. Review `bookmark_cleaner.log` before discarding anything important. You can re-run with `--skip-check` and manually prune those entries.

---

## How Organization Works

Root-level (unfoldered) bookmarks are organized into folders. After organization, singleton folders (folders containing only one bookmark) are consolidated, and all folders and bookmarks are sorted alphabetically.

### AI-Powered Organization (default)

After URL checking is complete, all surviving unfoldered bookmarks are sent to the AI model specified in your `.env` file in a single API call. The model reviews every bookmark title and URL together, decides on a logical folder taxonomy tailored to your actual collection, and assigns each bookmark to a folder path.

The script automatically detects which AI provider you've configured (OpenAI, Anthropic, Gemini, or OpenRouter) and uses the appropriate API. Default models:

- OpenAI: `gpt-5.4-nano`
- Anthropic: `claude-haiku-4-5`
- Gemini: `gemini-3.1-flash-lite-preview`
- OpenRouter: `openai/gpt-5.4-nano` (access to hundreds of models via one API)

The AI creates folders and subfolders appropriate to what it sees — for example:

- `Software Engineering/Frontend`
- `Health & Fitness/Nutrition & Diet`
- `AI Tools/MCP`
- `Finance & Crypto/Crypto`
- `Unsorted Bookmarks` _(catch-all for anything it can't categorize)_

Because the model sees the whole collection at once, it can create folders that reflect your specific bookmarks rather than a generic preset list.

### Rule-Based Fallback

If no API key is set (OpenAI, Anthropic, Gemini, or OpenRouter), the API call fails, or you pass `--no-ai`, the script falls back to a built-in keyword matcher. Each bookmark's title and URL are checked against a priority-ordered list of `(folder_path, [keywords])` rules — the first match wins.

You can customize these rules by editing the `TOPIC_RULES` list near the top of `bookmark_cleaner.py`:

```python
("Home Automation", [
    "home assistant", "hass.io", "zigbee", "z-wave", "smart home", "mqtt",
]),
```

Use a `/` separator to create subfolders:

```python
("Software Engineering/Rust", [
    "rust lang", "cargo", "crates.io", "rustacean",
]),
```

---

## Output Files

After a full run you will have:

| File                               | Description                                      |
| ---------------------------------- | ------------------------------------------------ |
| `<input>.html`                     | Your original file, left completely untouched    |
| `<input>_cleaned_<timestamp>.html` | Cleaned and organized favorites, ready to import |
| `bookmark_cleaner.log`             | Per-URL check results with HTTP status codes     |

The `.env` file (containing your API key) is never written to or modified by the script.

---

## Performance

For a collection of ~1,000 bookmarks with default settings (20 threads, 10s timeout):

- **URL checking** takes roughly 3–8 minutes depending on network speed and how many sites are slow to respond
- **Organizing** is nearly instant

Reduce `--threads` if you hit rate limits; increase `--timeout` if legitimate sites are being flagged as dead due to slow response times.

### Singleton Folder Consolidation

After all bookmarks are organized into folders, the script scans for folders containing only one bookmark. Each such folder is treated as a sign that the bookmark needs a better home. The lone bookmark is relocated to the most topically relevant existing folder (using AI or keyword rules), and the now-empty folder is deleted. This process repeats until no singleton folders remain.

The AI taxonomy prompt also instructs the model to avoid creating singleton folders in the first place — every folder should contain at least 2 bookmarks.

### Alphabetical Sorting

After consolidation, all folders and bookmarks are sorted alphabetically at every level of the hierarchy. Folders appear before bookmarks within each parent, and both groups are sorted case-insensitively by name/title.

---

## Limitations

- **Favicon/icon data** is preserved from the original file but not re-fetched for bookmarks moved to new folders
- Existing folder structures are preserved as-is; only unfoldered bookmarks and singleton folders are reorganized
- Some CDN-protected or bot-blocking sites may return errors despite being live; always review the log before finalizing
- `file://` and `chrome://` URLs are kept without checking

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
