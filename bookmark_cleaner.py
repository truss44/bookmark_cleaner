#!/usr/bin/env python3
"""
Microsoft Edge Favorites Cleaner & Organizer
=============================================
Parses a Netscape Bookmark HTML file (Edge favorites export), checks each URL,
removes dead links (404 / connection errors), and organizes loose bookmarks
into topic-based folders.
A timestamped backup of the original is always created.

Usage:
    python bookmark_cleaner.py <input_file> [options]

Options:
    --output FILE       Output file path (default: favorites_cleaned.html)
    --threads N         Concurrent HTTP workers (default: 20)
    --timeout N         Per-request timeout in seconds (default: 10)
    --dry-run           Report only; do not write output file
    --skip-check        Skip URL reachability checks (organize only)
    --no-ai             Skip AI folder assignment; use built-in keyword
                     rules instead
    --log FILE      Write detailed log to FILE
                     (default: bookmark_cleaner.log)

AI Providers (set via environment variables):
    - OpenAI: OPENAI_API_KEY (model: OPENAI_MODEL,
             default: gpt-5.4-nano)
    - Anthropic: ANTHROPIC_API_KEY (model: ANTHROPIC_MODEL,
                 default: claude-haiku-4-5)
    - Gemini: GEMINI_API_KEY or GOOGLE_API_KEY (model: GEMINI_MODEL,
             default: gemini-3.1-flash-lite-preview)
    - OpenRouter: OPENROUTER_API_KEY (model: OPENROUTER_MODEL,
                default: openai/gpt-5.4-nano)

Output:
    - <backup>_YYYYMMDD_HHMMSS.html   — original file, untouched
    - <output>.html                   — cleaned & reorganized bookmarks
    - <log file>                      — per-URL results

Edge Import:
    Open Edge → Settings → Import browser data → Import from other browsers
    Choose "Favorites or bookmarks HTML file" and point to the output file.
"""

import argparse
import concurrent.futures
import threading
import logging
import os
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import json

import requests
import urllib3
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional AI provider SDKs - imported only if available
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from google import genai
except ImportError:
    genai = None

try:
    from openrouter import OpenRouter
except ImportError:
    OpenRouter = None

# Load .env file if present (must come before any os.getenv calls)
load_dotenv()

# Suppress warnings for sites with bad/self-signed SSL certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class Bookmark:
    """Represents a single <A> bookmark entry."""

    def __init__(
        self,
        href: str,
        title: str,
        add_date: str = "",
        icon: str = "",
        raw_attrs: Optional[dict] = None,
    ):
        self.href = href
        self.title = title
        self.add_date = add_date
        self.icon = icon
        self.raw_attrs = raw_attrs or {}
        self.folder_path: list[str] = []  # folders this bookmark lives in
        self.alive: Optional[bool] = None  # None = unchecked

    def __repr__(self):
        return f"<Bookmark {self.title!r} {self.href!r}>"


class Folder:
    """Represents a <H3> folder entry."""

    def __init__(
        self,
        name: str,
        add_date: str = "",
        last_modified: str = "",
        personal_toolbar_folder: bool = False,
    ):
        self.name = name
        self.add_date = add_date
        self.last_modified = last_modified
        self.personal_toolbar_folder = personal_toolbar_folder
        self.children: list = []  # mix of Bookmark and Folder

    def __repr__(self):
        return f"<Folder {self.name!r} ({len(self.children)} items)>"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class BookmarkParser(HTMLParser):
    """Parse a Netscape Bookmark HTML file into a tree of Folder / Bookmark."""

    def __init__(self):
        super().__init__()
        self._root = Folder("__root__")
        self._stack: list[Folder] = [self._root]
        self._current_bookmark: Optional[Bookmark] = None
        self._in_title = False

    # ------------------------------------------------------------------ feed

    def handle_starttag(self, tag: str, attrs):
        tag = tag.upper()
        attr_dict = dict(attrs)

        if tag == "DL":
            # start of a new subfolder level — push a placeholder
            if self._stack and self._stack[-1].children:
                last = self._stack[-1].children[-1]
                if isinstance(last, Folder):
                    self._stack.append(last)
        elif tag == "H3":
            folder = Folder(
                name="",
                add_date=attr_dict.get("add_date", ""),
                last_modified=attr_dict.get("last_modified", ""),
                personal_toolbar_folder=(
                    attr_dict.get("personal_toolbar_folder", "").lower()
                    == "true"
                ),
            )
            self._stack[-1].children.append(folder)
            self._in_title = True  # next data is the folder name
            self._current_bookmark = None
        elif tag == "A":
            bm = Bookmark(
                href=attr_dict.get("href", ""),
                title="",
                add_date=attr_dict.get("add_date", ""),
                icon=attr_dict.get("icon", ""),
                raw_attrs=attr_dict,
            )
            self._stack[-1].children.append(bm)
            self._current_bookmark = bm
            self._in_title = True

    def handle_endtag(self, tag: str):
        tag = tag.upper()
        if tag == "DL":
            if len(self._stack) > 1:
                self._stack.pop()
        elif tag in ("H3", "A"):
            self._in_title = False
            self._current_bookmark = None

    def handle_data(self, data: str):
        if not self._in_title:
            return
        # Assign text to whatever is currently open
        if self._current_bookmark is not None:
            self._current_bookmark.title += data
        elif self._stack:
            # last child of current folder should be the H3 folder
            kids = self._stack[-1].children
            last = kids[-1] if kids else None
            if isinstance(last, Folder) and not last.name:
                last.name += data

    @property
    def root(self) -> Folder:
        return self._root


def parse_bookmarks(path: str) -> Folder:
    """Read *path* and return the root Folder tree."""
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    parser = BookmarkParser()
    parser.feed(content)
    return parser.root


# ---------------------------------------------------------------------------
# URL checking
# ---------------------------------------------------------------------------

DEAD_STATUS_CODES = {404, 410}

_SESSION: Optional[requests.Session] = None


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    return session


def is_url_alive(url: str, timeout: int = 10) -> tuple[bool, str]:
    """
    Returns (alive: bool, reason: str).
    Tries HEAD first, falls back to GET if HEAD returns 405/403.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return True, "non-http scheme — skipped"

    session = _make_session()
    try:
        resp = session.head(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 405 or resp.status_code == 403:
            resp = session.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
            resp.close()
        alive = resp.status_code not in DEAD_STATUS_CODES
        return alive, f"HTTP {resp.status_code}"
    except requests.exceptions.SSLError:
        # Some old sites have bad certs — retry without verification
        try:
            resp = session.head(
                url, timeout=timeout, allow_redirects=True, verify=False
            )
            alive = resp.status_code not in DEAD_STATUS_CODES
            return alive, f"HTTP {resp.status_code} (SSL ignored)"
        except Exception as exc:
            return False, f"SSL error: {exc}"
    except requests.exceptions.ConnectionError as exc:
        return False, f"Connection error: {exc}"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as exc:
        return False, f"Error: {exc}"


def check_all_bookmarks(
    bookmarks: list[Bookmark],
    max_workers: int = 20,
    timeout: int = 10,
    stop_event: threading.Event = None,
) -> None:
    """Update bookmark.alive in-place for every bookmark in the list.

    Checks each bookmark concurrently. Respects *stop_event* so the caller
    can request a clean shutdown (e.g. on Ctrl+C) without leaving a traceback.
    Bookmarks not yet checked are left with alive=None and treated as alive
    so no data is lost if the run is interrupted.
    """

    def _check(bm: Bookmark):
        if stop_event and stop_event.is_set():
            return bm, True, "skipped (interrupted)"
        alive, reason = is_url_alive(bm.href, timeout)
        bm.alive = alive
        return bm, alive, reason

    total = len(bookmarks)
    done = 0
    alive_count = 0
    dead_count = 0

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max_workers
    ) as pool:
        futures = {pool.submit(_check, bm): bm for bm in bookmarks}
        try:
            for future in concurrent.futures.as_completed(futures):
                if stop_event and stop_event.is_set():
                    # Cancel any futures not yet started
                    for f in futures:
                        f.cancel()
                    break
                bm, alive, reason = future.result()
                done += 1
                if alive:
                    alive_count += 1
                else:
                    dead_count += 1
                pct = (done / total) * 100
                status = "\u2713" if alive else "\u2717"
                logging.info(
                    "[%d/%d] %s  %s  (%s)",
                    done,
                    total,
                    status,
                    bm.href,
                    reason,
                )
                bar_filled = int(pct / 5)
                bar = "\u2588" * bar_filled + "\u2591" * (20 - bar_filled)
                print(
                    f"\r  [{bar}] {pct:5.1f}%  {done}/{total}  "
                    f"\u2713 {alive_count}  \u2717 {dead_count}",
                    end="",
                    flush=True,
                )
        except KeyboardInterrupt:
            if stop_event:
                stop_event.set()
            for f in futures:
                f.cancel()

    print(flush=True)  # newline after progress bar finishes


# Organizer — AI-based folder assignment via OpenAI, Anthropic,
# Gemini, or OpenRouter
# ---------------------------------------------------------------------------


def _get_ai_provider() -> Optional[tuple[str, str, str]]:
    """Return (provider, api_key, model) for first configured AI provider."""
    if OpenAI and os.getenv("OPENAI_API_KEY"):
        return (
            "openai",
            os.getenv("OPENAI_API_KEY"),
            os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
        )
    if Anthropic and os.getenv("ANTHROPIC_API_KEY"):
        return (
            "anthropic",
            os.getenv("ANTHROPIC_API_KEY"),
            os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
        )
    if genai and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        return (
            "gemini",
            os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
        )
    if OpenRouter and os.getenv("OPENROUTER_API_KEY"):
        return (
            "openrouter",
            os.getenv("OPENROUTER_API_KEY"),
            os.getenv("OPENROUTER_MODEL", "openai/gpt-5.4-nano"),
        )
    return None


def _call_ai(provider: str, api_key: str, model: str, prompt: str) -> str:
    """Dispatch prompt to AI provider and return raw text response."""
    if provider == "openai":
        client = OpenAI(api_key=api_key)
        response = client.responses.create(model=model, input=prompt)
        return response.output_text.strip()
    if provider == "anthropic":
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    if provider == "gemini":
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip()
    if provider == "openrouter":
        with OpenRouter(api_key=api_key) as client:
            response = client.chat.send(
                model=model, messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content.strip()
    raise ValueError(f"Unknown provider: {provider}")


def build_ai_folder_structure(
    bookmarks: list[Bookmark],
    existing_folders: Optional[list[str]] = None,
) -> dict[str, str]:
    """
    Send all surviving bookmark titles + URLs to an AI model in a single
    prompt. Returns a dict mapping each bookmark href to its suggested
    folder path (e.g. "Software Engineering/Frontend" or "Health & Fitness").

    existing_folders: optional list of folder paths already in the tree so
    the AI can reuse them instead of creating new ones.

    Supports multiple AI providers via environment variables:
    - OpenAI: OPENAI_API_KEY (model: OPENAI_MODEL,
             default: gpt-5.4-nano)
    - Anthropic: ANTHROPIC_API_KEY (model: ANTHROPIC_MODEL,
                 default: claude-haiku-4-5)
    - Gemini: GEMINI_API_KEY or GOOGLE_API_KEY (model: GEMINI_MODEL,
             default: gemini-3.1-flash-lite-preview)
    - OpenRouter: OPENROUTER_API_KEY (model: OPENROUTER_MODEL,
                default: openai/gpt-5.4-nano)

    Falls back to rule-based assignment if no API key is set
    or the API call fails.
    """
    prov = _get_ai_provider()
    if prov is None:
        print(
            "  WARNING: No AI API key set (OPENAI_API_KEY, "
            "ANTHROPIC_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY) — "
            "falling back to rule-based organizer."
        )
        return {}

    provider, api_key, model = prov

    bm_list = [
        {"id": i, "title": bm.title.strip(), "url": bm.href}
        for i, bm in enumerate(bookmarks)
    ]

    existing_section = ""
    if existing_folders:
        existing_section = f"""
Existing folders already in the bookmark collection:
{json.dumps(existing_folders, ensure_ascii=False)}

Decision rule — reuse vs. create:
  Score how well each group of bookmarks matches an existing folder (1–10):
    8–10  Strong, specific match (folder name directly describes the topic)
          → Reuse the existing folder.
    1–7   Weak or generic match (existing folder is vague, broad, or only
          loosely related)
          → Create a NEW, more specific folder or sub-folder instead.

Guidance:
- DEFAULT to creating a new folder when in doubt. Specificity beats reuse.
- You MAY nest sub-folders up to 4 levels deep using "/" as a separator
  (e.g. "Technology/DevOps/CI-CD/GitHub Actions").
- Use deeper nesting when it meaningfully narrows the topic — do not nest
  just for the sake of it.
- Never force bookmarks into a vague existing folder just to avoid
  creating a new one.
- Still apply the 2-bookmark minimum rule: every folder must contain
  at least 2 bookmarks.
"""

    prompt = f"""You are organizing a browser bookmark collection.
Below is a JSON array of bookmarks, each with an id, title, and URL.
{existing_section}
Your task:
1. Analyse all bookmarks and decide on the best set of top-level folders
   and sub-folders (up to 4 levels deep) that would logically group them.
   Folder names MUST be broad topic or category names (e.g. "React",
   "DevOps", "Crypto", "Fitness") — NEVER use a bookmark's own title,
   a package/library name, a website name, or a place name as a folder
   name unless it represents a whole category of related content.
   Avoid generic names like "Miscellaneous" unless truly needed.
   Use a catch-all folder called "Unsorted Bookmarks" only for items
   that genuinely defy categorisation. "Unsorted Bookmarks" must be
   flat — never create sub-folders under it.
2. Assign every bookmark to exactly one folder path using "/" as a separator
   for sub-folders (e.g. "Software Engineering/Frontend/React" or
   "Finance/Crypto/DeFi/Lending").
3. IMPORTANT: Every folder you create must contain at least 2 bookmarks.
   Never assign a bookmark to a folder that would contain only that one
   bookmark. Group it with other relevant bookmarks instead, or assign it
   to the closest relevant existing folder or to "Unsorted Bookmarks".
4. Return ONLY a valid JSON object mapping each numeric id
   (as a string key) to its folder path string.
   No explanation, no markdown, no extra keys.

Example output format:
{{
  "0": "Finance & Crypto/Crypto",
  "1": "Health & Fitness/Nutrition",
  "2": "AI Tools"
}}

Bookmarks:
{json.dumps(bm_list, ensure_ascii=False)}
"""

    print(
        f"  Sending bookmark list to {provider}/{model} for folder grouping …"
    )
    try:
        raw = _call_ai(provider, api_key, model, prompt)
        # Strip markdown fences if model adds them
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        mapping_by_index = json.loads(raw)
        href_map: dict[str, str] = {}
        for idx_str, folder_path in mapping_by_index.items():
            idx = int(idx_str)
            if 0 <= idx < len(bookmarks):
                href_map[bookmarks[idx].href] = folder_path
        print(f"  AI assigned {len(href_map)} bookmarks to folders.")
        return href_map
    except Exception as exc:
        print(
            f"  WARNING: AI folder assignment failed ({exc}) — "
            "falling back to rule-based organizer."
        )
        return {}


# Rule-based fallback organizer (used when AI is unavailable)
# ---------------------------------------------------------------------------

TOPIC_RULES: list[tuple[str, list[str]]] = [
    (
        "AI Tools/Image Generation",
        [
            "dalle",
            "stable diffusion",
            "midjourney",
            "leonardo",
            "img2img",
            "image generator",
            "ai art",
            "flux playground",
            "piclumen",
            "imglarger",
            "perchance",
            "picogen",
        ],
    ),
    (
        "AI Tools/Coding Assistants",
        [
            "github copilot",
            "copilot",
            "cody",
            "augment code",
            "cursor",
            "tabnine",
            "sourcegraph",
            "continue.dev",
            "aider",
            "coding assistant",
        ],
    ),
    (
        "AI Tools/Video & Audio",
        [
            "synthesia",
            "heygen",
            "assemblyai",
            "elevenlabs",
            "runwayml",
            "sora",
            "video generator",
            "text to speech",
            "tts",
        ],
    ),
    (
        "AI Tools",
        [
            "openai",
            "chatgpt",
            "gpt-",
            "claude",
            "anthropic",
            "cohere",
            "deepseek",
            "gemini",
            "llama",
            "mistral",
            "perplexity",
            "ai model",
            "llm",
            "chatbot",
            "hugging face",
            "bfl.ai",
            "lmarena",
            "anylearn",
            "artificial analysis",
            "requesty",
            "bolt.new",
            "cloudskillsboost",
            "writer.com",
            "awesome chatgpt",
            "prompts.chat",
            "pixeldojo",
            "augmentcode",
            "assemblyai",
        ],
    ),
    (
        "Software Engineering/APIs",
        [
            "swagger",
            "postman",
            "rapidapi",
            "api reference",
            "rest api",
            "graphql",
            "openapi",
        ],
    ),
    # ... rest of the code remains the same ...
    (
        "Software Engineering/DevOps & Monitoring",
        [
            "dynatrace",
            "grafana",
            "datadog",
            "splunk",
            "pagerduty",
            "opsgenie",
            "prometheus",
            "kibana",
            "elastic",
            "new relic",
            "jira",
            "jira service",
            "atlassian",
            "confluence",
        ],
    ),
    (
        "Software Engineering/Docker & Containers",
        [
            "docker",
            "kubernetes",
            "k8s",
            "helm",
            "podman",
            "containerd",
        ],
    ),
    (
        "Software Engineering/Frontend",
        [
            "bootstrap",
            "tailwind",
            "react",
            "vue",
            "angular",
            "svelte",
            "nextjs",
            "html",
            "css",
            "javascript",
            "jquery",
            "webpack",
            "vite",
        ],
    ),
    (
        "Software Engineering/Node & NPM",
        [
            "nodejs",
            "npm",
            "yarn",
            "deno",
            "bun",
            "express",
            "fastify",
        ],
    ),
    (
        "Software Engineering/Python",
        [
            "python",
            "pypi",
            "flask",
            "django",
            "fastapi",
            "pandas",
            "numpy",
        ],
    ),
    (
        "Software Engineering/Mobile",
        [
            "android",
            "ios",
            "flutter",
            "react native",
            "ionic",
            "phonegap",
            "framework7",
            "firebase",
            "expo",
            "capacitor",
        ],
    ),
    (
        "Software Engineering/Databases",
        [
            "postgresql",
            "mysql",
            "mongodb",
            "redis",
            "sqlite",
            "oracle",
            "supabase",
            "planetscale",
        ],
    ),
    (
        "Software Engineering/Version Control",
        [
            "github",
            "gitlab",
            "bitbucket",
            "svn",
            "git",
        ],
    ),
    (
        "Software Engineering",
        [
            "stack overflow",
            "mdn web",
            "developer",
            "programming",
            "tutorial",
            "documentation",
            "docs.",
            "/docs/",
            "perl",
            "php",
            "laravel",
            "java",
            "kotlin",
            "swift",
            "rust",
            "go lang",
            "coding",
            "free tools",
            "dev.to",
            "medium.com",
        ],
    ),
    (
        "Finance & Crypto/Crypto",
        [
            "coinbase",
            "binance",
            "kraken",
            "crypto",
            "bitcoin",
            "ethereum",
            "defi",
            "nft",
            "coingecko",
            "coinmarketcap",
            "uniswap",
        ],
    ),
    (
        "Finance & Crypto",
        [
            "bank",
            "finance",
            "invest",
            "stock",
            "etf",
            "brokerage",
            "credit card",
            "loan",
            "mortgage",
            "tax",
            "fidelity",
            "vanguard",
            "schwab",
            "robinhood",
            "5/3",
            "53.com",
        ],
    ),
    (
        "Health & Fitness/Nutrition & Diet",
        [
            "recipe",
            "food hub",
            "myfitnesspal",
            "nutrition",
            "calorie",
            "diet",
            "keto",
            "mediterranean dish",
            "ninja creami",
            "weight loss",
            "factor75",
            "factor meal",
            "diabetes food",
            "vitamix",
        ],
    ),
    (
        "Health & Fitness/Exercise",
        [
            "yoga",
            "workout",
            "exercise",
            "fitness",
            "ddp yoga",
            "gym",
            "crossfit",
            "running",
            "cycling",
        ],
    ),
    (
        "Health & Fitness/Mental Health",
        [
            "talkspace",
            "betterhelp",
            "therapy",
            "mental health",
            "meditation",
            "calm",
            "headspace",
        ],
    ),
    (
        "Health & Fitness/Medical",
        [
            "peptide",
            "supplement",
            "pharmacy",
            "cap-rx",
            "medication",
            "health",
            "medical",
        ],
    ),
    ("Health & Fitness", ["health", "wellness", "medicine"]),
    (
        "Shopping & Deals",
        [
            "ebay",
            "amazon",
            "etsy",
            "walmart",
            "target",
            "bestbuy",
            "deal",
            "coupon",
            "discount",
            "shop",
        ],
    ),
    (
        "Social & Communication",
        [
            "facebook",
            "twitter",
            "instagram",
            "linkedin",
            "reddit",
            "discord",
            "slack",
            "youtube",
            "tiktok",
            "mastodon",
        ],
    ),
    (
        "Entertainment/Gaming",
        [
            "steam",
            "gog",
            "epic games",
            "gaming",
            "game",
            "twitch",
        ],
    ),
    (
        "Entertainment/Media",
        [
            "netflix",
            "hulu",
            "spotify",
            "ticketmaster",
            "12ft",
            "paywall",
        ],
    ),
    (
        "Travel",
        [
            "travel",
            "hotel",
            "flight",
            "airbnb",
            "booking.com",
            "expedia",
            "tripadvisor",
            "kayak",
        ],
    ),
    (
        "Education",
        [
            "udemy",
            "coursera",
            "pluralsight",
            "linkedin learn",
            "edx",
            "pega university",
            "google skills",
            "skillshare",
            "tutorial",
            "learn",
            "course",
        ],
    ),
    (
        "Productivity",
        [
            "notion",
            "trello",
            "asana",
            "monday.com",
            "todoist",
            "google docs",
            "drive",
            "dropbox",
            "airtable",
        ],
    ),
    (
        "Community & Organizations",
        [
            "civitan",
            "volunteer",
            "nonprofit",
            "church",
            "charity",
        ],
    ),
    (
        "Job Sites",
        [
            "indeed",
            "linkedin job",
            "glassdoor",
            "monster",
            "ziprecruiter",
            "mystery shopping",
            "settlement",
        ],
    ),
    (
        "News & Reference",
        [
            "news",
            "wikipedia",
            "bbc",
            "cnn",
            "nytimes",
            "reuters",
            "techcrunch",
            "wired",
            "ars technica",
        ],
    ),
]


def _score_bookmark(bm: Bookmark, keywords: list[str]) -> int:
    text = (bm.title + " " + bm.href).lower()
    return sum(1 for kw in keywords if kw.lower() in text)


def _suggest_folder_rules(bm: Bookmark) -> Optional[str]:
    best_folder = None
    best_score = 0
    for folder_path, keywords in TOPIC_RULES:
        score = _score_bookmark(bm, keywords)
        if score > best_score:
            best_score = score
            best_folder = folder_path
    return best_folder if best_score > 0 else None


def _get_or_create_folder(parent: Folder, name: str) -> Folder:
    for child in parent.children:
        if isinstance(child, Folder) and child.name == name:
            return child
    new_folder = Folder(name)
    parent.children.append(new_folder)
    return new_folder


def _sanitize_folder_path(path: str) -> str:
    """Collapse any 'Unsorted Bookmarks/...' path to the top-level only."""
    if path.startswith("Unsorted Bookmarks/"):
        return "Unsorted Bookmarks"
    return path


def _get_or_create_nested(parent: Folder, path: str) -> Folder:
    """Given 'AI Tools/Image Generation', return (or create)
    the nested folder."""
    path = _sanitize_folder_path(path)
    parts = [p.strip() for p in path.split("/")]
    node = parent
    for part in parts:
        node = _get_or_create_folder(node, part)
    return node


def organize_unfoldered(
    root: Folder,
    orphans: list[Bookmark],
    ai_map: Optional[dict[str, str]] = None,
) -> dict[str, list[Bookmark]]:
    """
    Move unfoldered bookmarks into topic folders.
    Uses AI-generated folder map when available;
    falls back to rule-based matching.
    Returns a dict of {folder_path: [bookmarks_moved]}.
    """
    moved: dict[str, list[Bookmark]] = {}
    still_loose: list[Bookmark] = []

    for bm in orphans:
        # Prefer AI assignment, fall back to keyword rules
        if ai_map and bm.href in ai_map:
            folder_path = _sanitize_folder_path(ai_map[bm.href])
        else:
            folder_path = _suggest_folder_rules(bm)

        if folder_path:
            target = _get_or_create_nested(root, folder_path)
            target.children.append(bm)
            moved.setdefault(folder_path, []).append(bm)
            if bm in root.children:
                root.children.remove(bm)
        else:
            still_loose.append(bm)

    # Remaining orphans go into "Unsorted Bookmarks"
    if still_loose:
        unsorted = _get_or_create_folder(root, "Unsorted Bookmarks")
        for bm in still_loose:
            unsorted.children.append(bm)
            if bm in root.children:
                root.children.remove(bm)
        moved.setdefault("Unsorted Bookmarks", []).extend(still_loose)

    return moved


# ---------------------------------------------------------------------------
# Collect helpers
# ---------------------------------------------------------------------------


def collect_all_bookmarks(node, path: list[str] = None) -> list[Bookmark]:
    """Walk the tree and return every bookmark with its folder_path set."""
    if path is None:
        path = []
    result = []
    for child in node.children:
        if isinstance(child, Bookmark):
            child.folder_path = list(path)
            result.append(child)
        elif isinstance(child, Folder):
            result.extend(collect_all_bookmarks(child, path + [child.name]))
    return result


def collect_unfoldered(root: Folder) -> list[Bookmark]:
    """Return bookmarks that are direct children of root (no folder)."""
    return [c for c in root.children if isinstance(c, Bookmark)]


def remove_dead_bookmarks(node, removed: list) -> None:
    """Walk tree in-place; remove bookmarks with alive == False."""
    to_remove = [
        c
        for c in node.children
        if isinstance(c, Bookmark) and c.alive is False
    ]
    for bm in to_remove:
        node.children.remove(bm)
        removed.append(bm)
    for child in node.children:
        if isinstance(child, Folder):
            remove_dead_bookmarks(child, removed)


def remove_duplicate_bookmarks(node: Folder, seen: set, removed: list) -> None:
    """Walk tree in-place; remove bookmarks whose URL was already seen."""
    to_remove = []
    for child in node.children:
        if isinstance(child, Bookmark):
            url = child.href.rstrip("/").lower()
            if url in seen:
                to_remove.append(child)
            else:
                seen.add(url)
    for bm in to_remove:
        node.children.remove(bm)
        removed.append(bm)
    for child in node.children:
        if isinstance(child, Folder):
            remove_duplicate_bookmarks(child, seen, removed)


# ---------------------------------------------------------------------------
# Singleton folder consolidation
# ---------------------------------------------------------------------------


def _collect_folder_names(
    root: Folder, _path: Optional[list[str]] = None
) -> list[str]:
    """Return sorted list of all folder paths in the tree (slash-separated)."""
    if _path is None:
        _path = []
    names: list[str] = []
    for child in root.children:
        if isinstance(child, Folder):
            child_path = _path + [child.name]
            names.append("/".join(child_path))
            names.extend(_collect_folder_names(child, child_path))
    return sorted(names)


def _move_bookmark(source: Folder, dest: Folder, bm: Bookmark) -> None:
    """Remove bm from source.children and append to dest.children."""
    source.children.remove(bm)
    dest.children.append(bm)


def _delete_empty_folder(parent: Folder, folder: Folder) -> None:
    """Remove folder from parent. Raises ValueError if non-empty/not found."""
    if folder.children:
        raise ValueError(f"Cannot delete non-empty folder: {folder.name!r}")
    if folder not in parent.children:
        raise ValueError(
            f"Folder {folder.name!r} not found in parent {parent.name!r}"
        )
    parent.children.remove(folder)


def _prune_empty_folders(node: Folder) -> None:
    """Recursively remove all childless folders from the tree."""
    for child in list(node.children):
        if isinstance(child, Folder):
            _prune_empty_folders(child)
            if not child.children:
                node.children.remove(child)


def collect_lone_folders(
    root: Folder,
) -> list[tuple[Folder, Folder, Bookmark]]:
    """
    Return (parent, lone_folder, lone_bookmark) for every folder that
    contains exactly one child and that child is a Bookmark (not a sub-folder).
    The root itself is never returned as a candidate.
    """
    results: list[tuple[Folder, Folder, Bookmark]] = []
    for child in root.children:
        if isinstance(child, Folder):
            lone = child.children[0] if len(child.children) == 1 else None
            if lone is not None and isinstance(lone, Bookmark):
                results.append((root, child, lone))
            else:
                results.extend(collect_lone_folders(child))
    return results


def _ai_best_folder_for_bookmark(
    bm: Bookmark, folder_names: list[str]
) -> Optional[str]:
    """Ask AI which existing folder best fits a lone bookmark."""
    prov = _get_ai_provider()
    if prov is None:
        return None
    provider, api_key, model = prov

    prompt = (
        "A bookmark is currently in its own isolated folder "
        "with no other bookmarks.\n"
        "Find the BEST existing folder from the list below to place it in.\n"
        f"\nBookmark:\n  Title: {bm.title}\n  URL: {bm.href}\n"
        "\nAvailable folders:\n"
        f"{json.dumps(folder_names, ensure_ascii=False)}\n"
        "\nRules:\n"
        "- Return ONLY a JSON string — exact folder path from list above.\n"
        "- Do not invent new folder names.\n"
        "- Pick the most topically relevant folder.\n"
        '- If nothing fits well, return "Unsorted Bookmarks".\n'
        '\nExample output: "Software Engineering/Frontend"\n'
    )
    try:
        raw = _call_ai(provider, api_key, model, prompt)
        raw = raw.strip().strip('"').strip("'")
        if raw in folder_names:
            return raw
        lower_map = {n.lower(): n for n in folder_names}
        if raw.lower() in lower_map:
            return lower_map[raw.lower()]
        return None
    except Exception:
        return None


def consolidate_lone_folders(
    root: Folder, use_ai: bool = True, max_passes: int = 15
) -> int:
    """
    Detect folders with exactly one bookmark, relocate that bookmark to the
    best matching existing folder, and delete the now-empty folder.
    Repeats until no lone folders remain.
    Returns count of relocated bookmarks.
    """
    total_moved = 0
    pass_num = 0
    while pass_num < max_passes:
        candidates = collect_lone_folders(root)
        if not candidates:
            break
        pass_num += 1
        total = len(candidates)
        all_folder_names = _collect_folder_names(root)
        moves_this_pass = 0
        for done, (parent, lone_folder, bm) in enumerate(candidates, start=1):
            # Exclude the lone folder itself so AI can't pick it
            lone_path = next(
                (
                    p
                    for p in all_folder_names
                    if p == lone_folder.name
                    or p.endswith("/" + lone_folder.name)
                ),
                None,
            )
            folder_names = (
                [p for p in all_folder_names if p != lone_path]
                if lone_path
                else all_folder_names
            )
            dest_path: Optional[str] = None
            if use_ai:
                dest_path = _ai_best_folder_for_bookmark(bm, folder_names)
            if dest_path is None:
                dest_path = _suggest_folder_rules(bm)
            if dest_path is None:
                dest_path = "Unsorted Bookmarks"
            dest = _get_or_create_nested(root, dest_path)
            # If dest is still the lone folder, force Unsorted Bookmarks
            if dest is lone_folder:
                if lone_folder.name == "Unsorted Bookmarks":
                    # Can't merge with itself; leave it
                    pct = (done / total) * 100
                    bar_filled = int(pct / 5)
                    bar = "\u2588" * bar_filled + "\u2591" * (20 - bar_filled)
                    pct = (done / total) * 100
                    bar_filled = int(pct / 5)
                    bar = "\u2588" * bar_filled + "\u2591" * (20 - bar_filled)
                    print(
                        f"\r  Pass {pass_num} [{bar}] {pct:5.1f}%"
                        f"  {done}/{total} processed"
                        f"  {moves_this_pass} moved",
                        end="",
                        flush=True,
                    )
                    continue
                dest_path = "Unsorted Bookmarks"
                dest = _get_or_create_nested(root, dest_path)
            pct = (done / total) * 100
            bar_filled = int(pct / 5)
            bar = "\u2588" * bar_filled + "\u2591" * (20 - bar_filled)
            print(
                f"\r  Pass {pass_num} [{bar}] {pct:5.1f}%"
                f"  {done}/{total} processed"
                f"  {moves_this_pass} moved",
                end="",
                flush=True,
            )
            _move_bookmark(lone_folder, dest, bm)
            if not lone_folder.children:
                _delete_empty_folder(parent, lone_folder)
            moves_this_pass += 1
            total_moved += 1
        print(f"    ({total_moved} total moved so far)", flush=True)
        _prune_empty_folders(root)
        if moves_this_pass == 0:
            break
    return total_moved


# ---------------------------------------------------------------------------
# Similar-folder merging
# ---------------------------------------------------------------------------


def _ai_suggest_folder_merges(
    folder_names: list[str],
) -> dict[str, list[str]]:
    """Ask AI to identify groups of similar folder names to merge.

    Returns {canonical_name: [names_to_merge_into_it, ...]}.
    Only folders with clear overlap are grouped; unrelated folders are omitted.
    """
    prov = _get_ai_provider()
    if prov is None:
        return {}
    provider, api_key, model = prov

    prompt = (
        "Below is a list of bookmark folder names.\n"
        "Identify groups of folders that represent the same topic "
        "and should be merged into one.\n"
        "For each group choose the best canonical name "
        "(prefer the most descriptive existing name).\n"
        "\nFolder names:\n"
        f"{json.dumps(folder_names, ensure_ascii=False)}\n"
        "\nRules:\n"
        "- Only group folders that are clearly about the same topic.\n"
        "- Do NOT merge unrelated folders just because they are small.\n"
        "- The canonical name MUST be one of the names in the list.\n"
        "- Omit folders that need no merging.\n"
        "- Return ONLY valid JSON: "
        '{"canonical": ["alias1", "alias2"], ...}\n'
        "- If nothing should be merged return {}\n"
    )
    try:
        raw = _call_ai(provider, api_key, model, prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        result: dict[str, list[str]] = {}
        for canonical, aliases in data.items():
            if (
                isinstance(aliases, list)
                and canonical in folder_names
                and aliases
            ):
                valid = [
                    a for a in aliases
                    if isinstance(a, str) and a in folder_names
                    and a != canonical
                ]
                if valid:
                    result[canonical] = valid
        return result
    except Exception:
        return {}


def _find_folder_by_name(
    node: Folder, name: str
) -> Optional[tuple["Folder", "Folder"]]:
    """Return (parent, folder) for first folder with given name, or None."""
    for child in node.children:
        if isinstance(child, Folder):
            if child.name == name:
                return (node, child)
            found = _find_folder_by_name(child, name)
            if found:
                return found
    return None


def _merge_folder_into(
    parent: Folder, src: Folder, dest: Folder
) -> None:
    """Move all children of src into dest, then delete src from parent."""
    for child in list(src.children):
        if isinstance(child, Bookmark):
            dest.children.append(child)
        elif isinstance(child, Folder):
            existing = next(
                (
                    c for c in dest.children
                    if isinstance(c, Folder) and c.name == child.name
                ),
                None,
            )
            if existing:
                _merge_folder_into(src, child, existing)
            else:
                dest.children.append(child)
        src.children.remove(child)
    if src in parent.children:
        parent.children.remove(src)


def merge_similar_folders(
    root: Folder, merges: dict[str, list[str]]
) -> int:
    """Apply merge groups to tree. Returns count of folders removed."""
    removed = 0
    for canonical, aliases in merges.items():
        canon_result = _find_folder_by_name(root, canonical)
        if canon_result is None:
            continue
        _, dest = canon_result
        for alias in aliases:
            alias_result = _find_folder_by_name(root, alias)
            if alias_result is None:
                continue
            alias_parent, src = alias_result
            if src is dest:
                continue
            _merge_folder_into(alias_parent, src, dest)
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# Alphabetical sort
# ---------------------------------------------------------------------------


def sort_tree(node: Folder) -> None:
    """Sort children: folders first (by name), then bookmarks (by title)."""
    node.children.sort(
        key=lambda c: (
            isinstance(c, Bookmark),
            (c.title if isinstance(c, Bookmark) else c.name).lower(),
        )
    )
    for child in node.children:
        if isinstance(child, Folder):
            sort_tree(child)


# ---------------------------------------------------------------------------
# HTML writer
# ---------------------------------------------------------------------------

HEADER = """\
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- This is an automatically generated file.
     It will be read and overwritten.
     DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
"""

FOOTER = "</DL><p>\n"


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _write_tree(node, lines: list[str], indent: int = 0) -> None:
    pad = "    " * indent
    for child in node.children:
        if isinstance(child, Folder):
            add_date = (
                f' ADD_DATE="{child.add_date}"' if child.add_date else ""
            )
            last_mod = (
                f' LAST_MODIFIED="{child.last_modified}"'
                if child.last_modified
                else ""
            )
            toolbar = (
                ' PERSONAL_TOOLBAR_FOLDER="true"'
                if child.personal_toolbar_folder
                else ""
            )
            lines.append(
                f"{pad}<DT><H3{add_date}{last_mod}{toolbar}>"
                f"{_esc(child.name)}</H3>\n"
            )
            lines.append(f"{pad}<DL><p>\n")
            _write_tree(child, lines, indent + 1)
            lines.append(f"{pad}</DL><p>\n")
        elif isinstance(child, Bookmark):
            add_date = (
                f' ADD_DATE="{child.add_date}"' if child.add_date else ""
            )
            icon = f' ICON="{child.icon}"' if child.icon else ""
            lines.append(
                f'{pad}<DT><A HREF="{_esc(child.href)}"'
                f"{add_date}{icon}>{_esc(child.title)}</A>\n"
            )


def write_bookmarks(root: Folder, path: str) -> None:
    lines = [HEADER]
    _write_tree(root, lines, indent=1)
    lines.append(FOOTER)
    Path(path).write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------

# Seconds between Windows epoch (1601-01-01) and Unix epoch (1970-01-01)
_CHROMIUM_EPOCH_OFFSET = 11_644_473_600


def find_browser_bookmark_files() -> list[tuple[str, Path]]:
    """Return (browser_name, path) for every Chromium Bookmarks JSON found."""
    home = Path.home()
    platform = sys.platform

    if platform == "win32":
        local = Path(
            os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")
        )
        bm = "User Data" / Path("Default") / "Bookmarks"
        candidates = [
            ("Microsoft Edge", local / "Microsoft" / "Edge" / bm),
            ("Google Chrome", local / "Google" / "Chrome" / bm),
            (
                "Brave",
                local / "BraveSoftware" / "Brave-Browser" / bm,
            ),
        ]
    elif platform == "darwin":
        app_support = home / "Library" / "Application Support"
        bm = Path("Default") / "Bookmarks"
        candidates = [
            ("Microsoft Edge", app_support / "Microsoft Edge" / bm),
            ("Google Chrome", app_support / "Google" / "Chrome" / bm),
            (
                "Brave",
                app_support / "BraveSoftware" / "Brave-Browser" / bm,
            ),
        ]
    else:
        config = home / ".config"
        bm = Path("Default") / "Bookmarks"
        candidates = [
            ("Microsoft Edge", config / "microsoft-edge" / bm),
            ("Google Chrome", config / "google-chrome" / bm),
            (
                "Brave",
                config / "BraveSoftware" / "Brave-Browser" / bm,
            ),
        ]

    return [(name, path) for name, path in candidates if path.exists()]


def _chromium_ts(raw: str) -> str:
    """Convert Chromium µs-since-1601 timestamp to Unix seconds string."""
    try:
        return str(int(raw) // 1_000_000 - _CHROMIUM_EPOCH_OFFSET)
    except (ValueError, TypeError):
        return ""


def _write_chromium_node(node: dict, lines: list[str], indent: int) -> None:
    pad = "    " * indent
    name = _esc(node.get("name", ""))
    date = _chromium_ts(node.get("date_added", ""))
    add_date = f' ADD_DATE="{date}"' if date else ""

    if node.get("type") == "url":
        url = _esc(node.get("url", ""))
        lines.append(f'{pad}<DT><A HREF="{url}"{add_date}>{name}</A>\n')
    elif node.get("type") == "folder":
        last_mod = _chromium_ts(node.get("date_modified", ""))
        last_modified = f' LAST_MODIFIED="{last_mod}"' if last_mod else ""
        lines.append(f"{pad}<DT><H3{add_date}{last_modified}>{name}</H3>\n")
        lines.append(f"{pad}<DL><p>\n")
        for child in node.get("children", []):
            _write_chromium_node(child, lines, indent + 1)
        lines.append(f"{pad}</DL><p>\n")


def convert_chromium_json_to_html(json_path: Path, output_path: Path) -> None:
    """Read a Chromium Bookmarks JSON file and write Netscape HTML."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    roots = data.get("roots", {})

    lines = [HEADER]
    lines.append("<DL><p>\n")

    root_order = [
        ("bookmark_bar", "Bookmarks bar", ' PERSONAL_TOOLBAR_FOLDER="true"'),
        ("other", "Other bookmarks", ""),
        ("synced", "Mobile bookmarks", ""),
    ]
    for key, fallback_name, extra_attrs in root_order:
        node = roots.get(key)
        if not node:
            continue
        name = _esc(node.get("name", fallback_name))
        date = _chromium_ts(node.get("date_added", ""))
        add_date = f' ADD_DATE="{date}"' if date else ""
        last_mod = _chromium_ts(node.get("date_modified", ""))
        last_modified = f' LAST_MODIFIED="{last_mod}"' if last_mod else ""
        lines.append(
            f"    <DT><H3{add_date}{last_modified}{extra_attrs}>{name}</H3>\n"
        )
        lines.append("    <DL><p>\n")
        for child in node.get("children", []):
            _write_chromium_node(child, lines, indent=2)
        lines.append("    </DL><p>\n")

    lines.append("</DL><p>\n")
    lines.append(FOOTER)
    output_path.write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Clean and organize Microsoft Edge favorites "
        "(Netscape Bookmark HTML)."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Path to the exported favorites HTML file "
        "(defaults to sole .html file in current "
        "directory if only one exists)",
    )
    parser.add_argument(
        "--output", default="", help="Output file path (default: auto-named)"
    )
    parser.add_argument(
        "--threads", type=int, default=20, help="Concurrent URL check workers"
    )
    parser.add_argument(
        "--timeout", type=int, default=10, help="Per-URL timeout (seconds)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only; do not write output",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip URL reachability checks",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI folder assignment; use keyword rules instead",
    )
    parser.add_argument(
        "--max-passes",
        type=int,
        default=15,
        metavar="N",
        help=("Max passes when merging lone folders (default: 15)"),
    )
    parser.add_argument(
        "--log", default="bookmark_cleaner.log", help="Log file path"
    )
    parser.add_argument(
        "--delete-duplicates",
        action="store_true",
        help="Remove duplicate URLs without prompting",
    )
    args = parser.parse_args()

    # ── Auto-detect HTML file if not specified ─────────────────────────────
    if args.input is None:
        html_files = list(Path(".").glob("*.html"))
        if len(html_files) == 1:
            args.input = str(html_files[0])
            print(f"Auto-detected HTML file: {args.input}")
        elif len(html_files) > 1:
            print(
                "ERROR: Multiple HTML files found in current directory:",
                file=sys.stderr,
            )
            for f in html_files:
                print(f"  - {f}", file=sys.stderr)
            print("Please specify the input file path.", file=sys.stderr)
            sys.exit(1)
        else:
            # No HTML file — try to find a browser Bookmarks JSON
            browsers = find_browser_bookmark_files()

            if len(browsers) == 0:
                print(
                    "No bookmark HTML file found in current directory.",
                    file=sys.stderr,
                )
                print(
                    "No browser bookmark files detected automatically.",
                    file=sys.stderr,
                )
                supplied = input(
                    "Enter path to bookmarks HTML file"
                    " (or press Enter to exit): "
                ).strip()
                if not supplied:
                    sys.exit(1)
                supplied_path = Path(supplied).expanduser().resolve()
                if not supplied_path.exists():
                    print(
                        f"ERROR: File not found: {supplied_path}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                args.input = str(supplied_path)

            elif len(browsers) == 1:
                bname, bjson = browsers[0]
                slug = bname.lower().replace(" ", "_")
                export_path = (
                    Path(".") / f"{slug}_bookmarks_export.html"
                )
                print(f"Found {bname} bookmarks at: {bjson}")
                print(f"Auto-exporting to: {export_path}")
                convert_chromium_json_to_html(bjson, export_path)
                args.input = str(export_path)

            else:
                print("Found browser bookmark files:")
                for i, (bname, bpath) in enumerate(browsers, 1):
                    print(f"  {i}. {bname}: {bpath}")
                last = len(browsers) + 1
                print(f"  {last}. Enter a custom file path")
                raw = (
                    input(f"Select [1–{last}] (default 1): ").strip()
                    or "1"
                )
                try:
                    choice = int(raw)
                except ValueError:
                    print("ERROR: Invalid selection.", file=sys.stderr)
                    sys.exit(1)
                if 1 <= choice <= len(browsers):
                    bname, bjson = browsers[choice - 1]
                    slug = bname.lower().replace(" ", "_")
                    export_path = (
                        Path(".") / f"{slug}_bookmarks_export.html"
                    )
                    print(f"Exporting {bname} bookmarks to: {export_path}")
                    convert_chromium_json_to_html(bjson, export_path)
                    args.input = str(export_path)
                elif choice == last:
                    supplied = input(
                        "Enter path to bookmarks HTML file: "
                    ).strip()
                    if not supplied:
                        sys.exit(1)
                    supplied_path = (
                        Path(supplied).expanduser().resolve()
                    )
                    if not supplied_path.exists():
                        print(
                            f"ERROR: File not found: {supplied_path}",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                    args.input = str(supplied_path)
                else:
                    print("ERROR: Invalid selection.", file=sys.stderr)
                    sys.exit(1)

    # ── Ctrl+C handler — clean exit without traceback ─────────────────────
    stop_event = threading.Event()

    def _handle_interrupt(sig, frame):
        if not stop_event.is_set():
            print(
                "\n\n  Interrupted — finishing in-flight requests "
                "and exiting cleanly …",
                flush=True,
            )
            stop_event.set()

    import signal

    signal.signal(signal.SIGINT, _handle_interrupt)

    # ── Logging setup ──────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(args.log, encoding="utf-8"),
        ],
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_path = Path(args.input).resolve()

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # ── Output path ────────────────────────────────────────────────────────
    # The original file is left untouched. The cleaned result is written to
    # a timestamped filename (or --output path if specified).
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = (
            input_path.parent
            / f"{input_path.stem}_cleaned_{timestamp}{input_path.suffix}"
        )

    print(f"✓ Original file kept as-is: {input_path}")
    print(f"✓ Cleaned output will be written to: {output_path}")

    # ── Parse ──────────────────────────────────────────────────────────────
    print(f"\nParsing bookmarks from: {input_path}")
    root = parse_bookmarks(str(input_path))
    all_bookmarks = collect_all_bookmarks(root)
    print(
        f"  Found {len(all_bookmarks)} bookmarks "
        f"across {_count_folders(root)} folders"
    )

    # ── URL checks ─────────────────────────────────────────────────────────
    removed_dead: list[Bookmark] = []
    if not args.skip_check:
        print(
            f"\nChecking {len(all_bookmarks)} URLs "
            f"({args.threads} threads, {args.timeout}s timeout) …"
        )
        print("  (This may take several minutes for large collections)\n")
        t0 = time.time()
        check_all_bookmarks(
            all_bookmarks,
            max_workers=args.threads,
            timeout=args.timeout,
            stop_event=stop_event,
        )
        elapsed = time.time() - t0

        dead = [bm for bm in all_bookmarks if bm.alive is False]
        alive = [bm for bm in all_bookmarks if bm.alive is True]
        print(
            f"\n  Checked in {elapsed:.1f}s:  {len(alive)} alive,  "
            f"{len(dead)} dead\n"
        )

        if stop_event.is_set():
            print("\n  Interrupted — saving results for checked bookmarks.")
            unchecked = [bm for bm in all_bookmarks if bm.alive is None]
            if unchecked:
                print(f"  {len(unchecked)} unchecked bookmarks will be kept.")
                for bm in unchecked:
                    bm.alive = True  # preserve unchecked bookmarks
        if not args.dry_run:
            remove_dead_bookmarks(root, removed_dead)
            print(f"  Removed {len(removed_dead)} dead bookmarks.")
        else:
            print(f"  [dry-run] Would remove {len(dead)} dead bookmarks.")
    else:
        print("\n  URL checking skipped (--skip-check).")

    # ── Remove duplicate bookmarks ─────────────────────────────────────────
    seen_urls: set[str] = set()
    dupe_count = 0
    for bm in collect_all_bookmarks(root):
        url = bm.href.rstrip("/").lower()
        if url in seen_urls:
            dupe_count += 1
        else:
            seen_urls.add(url)

    removed_dupes: list[Bookmark] = []
    if dupe_count > 0:
        print(f"\nFound {dupe_count} duplicate bookmark(s).")
        if args.dry_run:
            print(
                "  [dry-run] Would remove duplicates if confirmed."
            )
        elif args.delete_duplicates:
            remove_duplicate_bookmarks(root, set(), removed_dupes)
            print(
                f"  Removed {len(removed_dupes)} duplicate bookmark(s)."
            )
        else:
            answer = input(
                "  Delete duplicate bookmarks? [y/N]: "
            ).strip().lower()
            if answer in ("y", "yes"):
                remove_duplicate_bookmarks(root, set(), removed_dupes)
                print(
                    f"  Removed {len(removed_dupes)} duplicate bookmark(s)."
                )
            else:
                print("  Skipped — duplicates kept.")
    else:
        print("\nNo duplicate bookmarks found.")

    # ── Organize unfoldered bookmarks ──────────────────────────────────────
    # Refresh after possible removals
    orphans = collect_unfoldered(root)
    print(f"\nOrganizing {len(orphans)} top-level (unfoldered) bookmarks …")

    ai_map: Optional[dict[str, str]] = None
    if not args.no_ai and orphans:
        existing_folders = _collect_folder_names(root)
        ai_map = build_ai_folder_structure(
            orphans, existing_folders=existing_folders or None
        )

    if not args.dry_run:
        moved = organize_unfoldered(root, orphans, ai_map=ai_map)
        for folder, bms in sorted(moved.items()):
            print(f"  → '{folder}': {len(bms)} bookmark(s)")
    else:
        for bm in orphans:
            raw_fp = (
                (ai_map or {}).get(bm.href)
                or _suggest_folder_rules(bm)
                or "Unsorted Bookmarks"
            )
            fp = _sanitize_folder_path(raw_fp)
            print(f"  [dry-run] '{bm.title[:60]}' → {fp}")

    # ── Merge lone folders ─────────────────────────────────────────────────
    if not args.dry_run:
        print("\nMerging lone folders …")
        relocated = consolidate_lone_folders(
            root,
            use_ai=not args.no_ai,
            max_passes=args.max_passes,
        )
        if relocated:
            print(f"  Moved {relocated} bookmark(s) out of lone folders.")
        else:
            print("  No lone folders found.")
    else:
        lone_folders = collect_lone_folders(root)
        if lone_folders:
            print(
                f"\n[dry-run] {len(lone_folders)} lone folder(s) "
                "would be merged:"
            )
            for _, sf, bm in lone_folders:
                print(
                    f"  '{sf.name}' → bookmark "
                    f"'{bm.title[:60]}' would be relocated"
                )

    # ── Merge similar folders ──────────────────────────────────────────────
    if not args.no_ai:
        print("\nChecking for similar folders to merge …")
        all_folder_names = _collect_folder_names(root)
        top_level_names = [
            n for n in all_folder_names if "/" not in n
        ]
        merges = _ai_suggest_folder_merges(top_level_names)
        if merges:
            if not args.dry_run:
                removed_folders = merge_similar_folders(root, merges)
                for canonical, aliases in merges.items():
                    joined = ", ".join(f"'{a}'" for a in aliases)
                    print(f"  Merged {joined} → '{canonical}'")
                print(
                    f"  {removed_folders} redundant folder(s) removed."
                )
            else:
                print("  [dry-run] Would merge:")
                for canonical, aliases in merges.items():
                    joined = ", ".join(f"'{a}'" for a in aliases)
                    print(f"    {joined} → '{canonical}'")
        else:
            print("  No similar folders found.")

    # ── Sort all folders and bookmarks alphabetically ──────────────────────
    if not args.dry_run:
        sort_tree(root)

    # ── Write output ───────────────────────────────────────────────────────
    if not args.dry_run:
        write_bookmarks(root, str(output_path))
        print(f"\n✓ Cleaned bookmarks written to: {output_path}")
        _print_summary(root, removed_dead, removed_dupes, output_path)
    else:
        print("\n[dry-run] No output file written.")
    print(f"\nDetailed log: {args.log}")
    print("\nTo import into Edge:")
    print(
        "  Settings → Import browser data →"
        " Favorites or bookmarks HTML file"
    )
    out = output_path if not args.dry_run else "(output file)"
    print(f"  → Select: {out}")


def _count_folders(node) -> int:
    count = 0
    for child in node.children:
        if isinstance(child, Folder):
            count += 1 + _count_folders(child)
    return count


def _print_summary(
    root: Folder, removed: list, dupes: list, output: Path
) -> None:
    all_bms = collect_all_bookmarks(root)
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Bookmarks remaining : {len(all_bms)}")
    print(f"  Dead links removed  : {len(removed)}")
    print(f"  Duplicates removed  : {len(dupes)}")
    print(f"  Folders in output   : {_count_folders(root)}")
    print(f"  Output file size    : {output.stat().st_size:,} bytes")
    print("=" * 60)


if __name__ == "__main__":
    main()
