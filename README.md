# Microsoft Edge Favorites Cleaner & Organizer

A Python command-line tool that parses your exported Edge favorites, removes dead links, and automatically organizes unfoldered bookmarks into topic-based folders — producing a clean HTML file ready to import back into Edge.

---

## Features

- **Automatic backup** — timestamped copy of the original is always created before any changes
- **Dead link removal** — checks every URL concurrently; removes 404s, 410s, and unreachable sites
- **Smart organization** — loose (unfoldered) bookmarks are matched against topic rules and moved into relevant folders and subfolders
- **Edge-compatible output** — writes standard Netscape Bookmark HTML that Edge imports natively
- **Detailed logging** — per-URL results written to a log file for review
- **Dry-run mode** — preview all changes without writing any files

---

## Requirements

- Python 3.10 or higher
- `requests`, `openai`, and `python-dotenv` libraries
- An OpenAI API key (free to create at [platform.openai.com](https://platform.openai.com/api-keys))

Install the dependencies:

```bash
pip install requests openai python-dotenv
```

---

## Setup

### API Key (.env)

The script uses OpenAI to intelligently assign your bookmarks to folders. To enable this, you need an OpenAI API key.

1. Copy the example env file:

   ```bash
   # Windows (PowerShell)
   Copy-Item .env.example .env

   # macOS / Linux
   cp .env.example .env
   ```

2. Open `.env` and configure your settings:

   ```
   OPENAI_API_KEY=sk-proj-...
   OPENAI_MODEL=gpt-5.4-mini
   ```

   - `OPENAI_API_KEY`: Your OpenAI API key (required)
   - `OPENAI_MODEL`: The model to use for folder assignment (optional, defaults to `gpt-5.4-mini`). You can use any OpenAI model name such as `gpt-4o`, `gpt-4o-mini`, `o1-mini`, etc.

3. The run scripts (`run.ps1` / `run.sh`) and the Python script itself will load `.env` automatically via `python-dotenv`.

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

Only root-level (unfoldered) bookmarks are organized — your existing folder structure is always preserved as-is.

### AI-Powered Organization (default)

After URL checking is complete, all surviving unfoldered bookmarks are sent to the OpenAI model specified in your `.env` file (defaults to `gpt-5.4-mini`) in a single API call. The model reviews every bookmark title and URL together, decides on a logical folder taxonomy tailored to your actual collection, and assigns each bookmark to a folder path.

The AI creates folders and subfolders appropriate to what it sees — for example:

- `Software Engineering/Frontend`
- `Health & Fitness/Nutrition & Diet`
- `AI Tools/MCP`
- `Finance & Crypto/Crypto`
- `Unsorted Bookmarks` _(catch-all for anything it can't categorize)_

Because the model sees the whole collection at once, it can create folders that reflect your specific bookmarks rather than a generic preset list.

### Rule-Based Fallback

If no `OPENAI_API_KEY` is set, the API call fails, or you pass `--no-ai`, the script falls back to a built-in keyword matcher. Each bookmark's title and URL are checked against a priority-ordered list of `(folder_path, [keywords])` rules — the first match wins.

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

---

## Limitations

- **Favicon/icon data** is preserved from the original file but not re-fetched for bookmarks moved to new folders
- The script does not restructure or rename your existing folders — it only moves loose (unfoldered) bookmarks
- Some CDN-protected or bot-blocking sites may return errors despite being live; always review the log before finalizing
- `file://` and `chrome://` URLs are kept without checking

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
