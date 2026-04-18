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
             default: gpt-5.4-mini)
    - Anthropic: ANTHROPIC_API_KEY (model: ANTHROPIC_MODEL,
                 default: claude-haiku-4-5)
    - Gemini: GEMINI_API_KEY or GOOGLE_API_KEY (model: GEMINI_MODEL,
             default: gemini-3.1-flash-lite-preview)
    - OpenRouter: OPENROUTER_API_KEY (model: OPENROUTER_MODEL,
                default: openai/gpt-5.4-mini)

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
from openai import OpenAI
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional AI provider SDKs - imported only if available
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
        self.folder_path: list[str] = []   # folders this bookmark lives in
        self.alive: Optional[bool] = None  # None = unchecked

    def __repr__(self):
        return f"<Bookmark {self.title!r} {self.href!r}>"


class Folder:
    """Represents a <H3> folder entry."""

    def __init__(self, name: str, add_date: str = "", last_modified: str = ""):
        self.name = name
        self.add_date = add_date
        self.last_modified = last_modified
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
            )
            self._stack[-1].children.append(folder)
            self._in_title = True   # next data is the folder name
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
            last = (
                self._stack[-1].children[-1]
                if self._stack[-1].children else None
            )
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
        total=2,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503]
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
                    done, total, status, bm.href, reason
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

def build_ai_folder_taxonomy(bookmarks: list[Bookmark]) -> dict[str, str]:
    """
    Send all surviving bookmark titles + URLs to an AI model in a single
    prompt. Returns a dict mapping each bookmark href to its suggested
    folder path (e.g. "Software Engineering/Frontend" or "Health & Fitness").

    Supports multiple AI providers via environment variables:
    - OpenAI: OPENAI_API_KEY (model: OPENAI_MODEL,
             default: gpt-5.4-mini)
    - Anthropic: ANTHROPIC_API_KEY (model: ANTHROPIC_MODEL,
                 default: claude-haiku-4-5)
    - Gemini: GEMINI_API_KEY or GOOGLE_API_KEY (model: GEMINI_MODEL,
             default: gemini-3.1-flash-lite-preview)
    - OpenRouter: OPENROUTER_API_KEY (model: OPENROUTER_MODEL,
                default: openai/gpt-5.4-mini)

    Falls back to rule-based assignment if no API key is set
    or the API call fails.
    """
    # Check for available API keys in priority order
    provider = None
    api_key = None
    model = None

    # Try OpenAI first
    if os.getenv("OPENAI_API_KEY"):
        provider = "openai"
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    # Try Anthropic
    elif Anthropic and os.getenv("ANTHROPIC_API_KEY"):
        provider = "anthropic"
        api_key = os.getenv("ANTHROPIC_API_KEY")
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    # Try Gemini
    elif genai and (os.getenv("GEMINI_API_KEY")
                    or os.getenv("GOOGLE_API_KEY")):
        provider = "gemini"
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    # Try OpenRouter
    elif OpenRouter and os.getenv("OPENROUTER_API_KEY"):
        provider = "openrouter"
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL", "openai/gpt-5.4-mini")
    else:
        print(
            "  WARNING: No AI API key set (OPENAI_API_KEY, "
            "ANTHROPIC_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY) — "
            "falling back to rule-based organizer."
        )
        return {}

    # Build a compact list of bookmarks for the prompt
    bm_list = [
        {"id": i, "title": bm.title.strip(), "url": bm.href}
        for i, bm in enumerate(bookmarks)
    ]

    prompt = f"""You are organizing a browser bookmark collection.
Below is a JSON array of bookmarks, each with an id, title, and URL.

Your task:
1. Analyse all bookmarks and decide on the best set of top-level folders
   and optional sub-folders that would logically group them.
   Be specific and meaningful — avoid generic names like "Miscellaneous"
   unless truly needed.
   Use a catch-all folder called "Unsorted Bookmarks" only for items
   that genuinely defy categorisation.
2. Assign every bookmark to exactly one folder path using "/" as a separator
   for sub-folders (e.g. "Software Engineering/Frontend").
3. Return ONLY a valid JSON object mapping each numeric id
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

    print(f"  Sending bookmark list to {provider}/{model} "
          f"for folder taxonomy …")
    try:
        raw = ""

        if provider == "openai":
            client = OpenAI(api_key=api_key)
            response = client.responses.create(
                model=model,
                input=prompt,
            )
            raw = response.output_text.strip()
        elif provider == "anthropic":
            client = Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}]
            )
            # Anthropic returns content blocks
            raw = response.content[0].text.strip()
        elif provider == "gemini":
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            raw = response.text.strip()
        elif provider == "openrouter":
            with OpenRouter(api_key=api_key) as client:
                response = client.chat.send(
                    model=model,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw = response.choices[0].message.content.strip()

        # Strip markdown fences if model adds them
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        mapping_by_index = json.loads(raw)
        # Convert index-keyed dict to href-keyed dict
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
    ("Software Engineering/DevOps & Monitoring", [
        "dynatrace", "grafana", "datadog", "splunk", "pagerduty", "opsgenie",
        "prometheus", "kibana", "elastic", "new relic", "jira", "jira service",
        "atlassian", "confluence",
    ]),
    ("Software Engineering/Docker & Containers", [
        "docker", "kubernetes", "k8s", "helm", "podman", "containerd",
    ]),
    ("Software Engineering/Frontend", [
        "bootstrap", "tailwind", "react", "vue", "angular", "svelte", "nextjs",
        "html", "css", "javascript", "jquery", "webpack", "vite",
    ]),
    ("Software Engineering/Node & NPM", [
        "nodejs", "npm", "yarn", "deno", "bun", "express", "fastify",
    ]),
    ("Software Engineering/Python", [
        "python", "pypi", "flask", "django", "fastapi", "pandas", "numpy",
    ]),
    ("Software Engineering/Mobile", [
        "android", "ios", "flutter", "react native", "ionic", "phonegap",
        "framework7", "firebase", "expo", "capacitor",
    ]),
    ("Software Engineering/Databases", [
        "postgresql", "mysql", "mongodb", "redis", "sqlite", "oracle",
        "supabase", "planetscale",
    ]),
    ("Software Engineering/Version Control", [
        "github", "gitlab", "bitbucket", "svn", "git",
    ]),
    ("Software Engineering", [
        "stack overflow", "mdn web", "developer", "programming", "tutorial",
        "documentation", "docs.", "/docs/", "perl", "php", "laravel", "java",
        "kotlin", "swift", "rust", "go lang", "coding", "free tools",
        "dev.to", "medium.com",
    ]),
    ("Finance & Crypto/Crypto", [
        "coinbase", "binance", "kraken", "crypto", "bitcoin", "ethereum",
        "defi", "nft", "coingecko", "coinmarketcap", "uniswap",
    ]),
    ("Finance & Crypto", [
        "bank", "finance", "invest", "stock", "etf", "brokerage",
        "credit card", "loan", "mortgage", "tax", "fidelity", "vanguard",
        "schwab", "robinhood", "5/3", "53.com",
    ]),
    ("Health & Fitness/Nutrition & Diet", [
        "recipe", "food hub", "myfitnesspal", "nutrition", "calorie",
        "diet", "keto", "mediterranean dish", "ninja creami", "weight loss",
        "factor75", "factor meal", "diabetes food", "vitamix",
    ]),
    ("Health & Fitness/Exercise", [
        "yoga", "workout", "exercise", "fitness", "ddp yoga", "gym",
        "crossfit", "running", "cycling",
    ]),
    ("Health & Fitness/Mental Health", [
        "talkspace", "betterhelp", "therapy", "mental health", "meditation",
        "calm", "headspace",
    ]),
    ("Health & Fitness/Medical", [
        "peptide", "supplement", "pharmacy", "cap-rx", "medication",
        "health", "medical",
    ]),
    ("Health & Fitness", ["health", "wellness", "medicine"]),
    ("Shopping & Deals", [
        "ebay", "amazon", "etsy", "walmart", "target", "bestbuy",
        "deal", "coupon", "discount", "shop",
    ]),
    ("Social & Communication", [
        "facebook", "twitter", "instagram", "linkedin", "reddit", "discord",
        "slack", "youtube", "tiktok", "mastodon",
    ]),
    ("Entertainment/Gaming", [
        "steam", "gog", "epic games", "gaming", "game", "twitch",
    ]),
    ("Entertainment/Media", [
        "netflix", "hulu", "spotify", "ticketmaster", "12ft", "paywall",
    ]),
    ("Travel", [
        "travel", "hotel", "flight", "airbnb", "booking.com", "expedia",
        "tripadvisor", "kayak",
    ]),
    ("Education", [
        "udemy", "coursera", "pluralsight", "linkedin learn", "edx",
        "pega university", "google skills", "skillshare", "tutorial",
        "learn", "course",
    ]),
    ("Productivity", [
        "notion", "trello", "asana", "monday.com", "todoist", "google docs",
        "drive", "dropbox", "airtable",
    ]),
    ("Community & Organizations", [
        "civitan", "volunteer", "nonprofit", "church", "charity",
    ]),
    ("Job Sites", [
        "indeed", "linkedin job", "glassdoor", "monster", "ziprecruiter",
        "mystery shopping", "settlement",
    ]),
    ("News & Reference", [
        "news", "wikipedia", "bbc", "cnn", "nytimes", "reuters",
        "techcrunch", "wired", "ars technica",
    ]),
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


def _get_or_create_nested(parent: Folder, path: str) -> Folder:
    """Given 'AI Tools/Image Generation', return (or create)
    the nested folder."""
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
            folder_path = ai_map[bm.href]
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
    """Walk the tree in-place and remove any bookmarks with alive == False."""
    to_remove = [
        c for c in node.children
        if isinstance(c, Bookmark) and c.alive is False
    ]
    for bm in to_remove:
        node.children.remove(bm)
        removed.append(bm)
    for child in node.children:
        if isinstance(child, Folder):
            remove_dead_bookmarks(child, removed)


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
                if child.last_modified else ""
            )
            lines.append(
                f'{pad}<DT><H3{add_date}{last_mod}>'
                f'{_esc(child.name)}</H3>\n'
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
                f'{add_date}{icon}>{_esc(child.title)}</A>\n'
            )


def write_bookmarks(root: Folder, path: str) -> None:
    lines = [HEADER]
    _write_tree(root, lines, indent=1)
    lines.append(FOOTER)
    Path(path).write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Clean and organize Microsoft Edge favorites "
                    "(Netscape Bookmark HTML)."
    )
    parser.add_argument(
        "input", nargs='?', default=None,
        help="Path to the exported favorites HTML file "
             "(defaults to sole .html file in current "
             "directory if only one exists)"
    )
    parser.add_argument(
        "--output", default="",
        help="Output file path (default: auto-named)"
    )
    parser.add_argument(
        "--threads", type=int, default=20,
        help="Concurrent URL check workers"
    )
    parser.add_argument(
        "--timeout", type=int, default=10,
        help="Per-URL timeout (seconds)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report only; do not write output"
    )
    parser.add_argument(
        "--skip-check", action="store_true",
        help="Skip URL reachability checks"
    )
    parser.add_argument(
        "--no-ai", action="store_true",
        help="Skip AI folder assignment; use built-in keyword rules instead"
    )
    parser.add_argument(
        "--log", default="bookmark_cleaner.log",
        help="Log file path"
    )
    args = parser.parse_args()

    # ── Auto-detect HTML file if not specified ─────────────────────────────
    if args.input is None:
        html_files = list(Path('.').glob('*.html'))
        if len(html_files) == 1:
            args.input = str(html_files[0])
            print(f"Auto-detected HTML file: {args.input}")
        elif len(html_files) == 0:
            print(
                "ERROR: No HTML files found in current directory.",
                file=sys.stderr
            )
            print("Please specify the input file path.", file=sys.stderr)
            sys.exit(1)
        else:
            print(
                "ERROR: Multiple HTML files found in current directory:",
                file=sys.stderr
            )
            for f in html_files:
                print(f"  - {f}", file=sys.stderr)
            print("Please specify the input file path.", file=sys.stderr)
            sys.exit(1)

    # ── Ctrl+C handler — clean exit without traceback ─────────────────────
    stop_event = threading.Event()

    def _handle_interrupt(sig, frame):
        if not stop_event.is_set():
            print(
                "\n\n  Interrupted — finishing in-flight requests "
                "and exiting cleanly …",
                flush=True
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
            input_path.parent /
            f"{input_path.stem}_cleaned_{timestamp}{input_path.suffix}"
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
            stop_event=stop_event
        )
        elapsed = time.time() - t0

        dead = [bm for bm in all_bookmarks if bm.alive is False]
        alive = [bm for bm in all_bookmarks if bm.alive is True]
        print(
            f"\n  Checked in {elapsed:.1f}s:  {len(alive)} alive,  "
            f"{len(dead)} dead\n"
        )

        if stop_event.is_set():
            print(
                "\n  Interrupted — saving results for checked "
                "bookmarks and exiting."
            )
            unchecked = [bm for bm in all_bookmarks if bm.alive is None]
            if unchecked:
                print(
                    f"  {len(unchecked)} unchecked bookmarks "
                    "will be kept as-is."
                )
                for bm in unchecked:
                    bm.alive = True  # preserve unchecked bookmarks
        if not args.dry_run:
            remove_dead_bookmarks(root, removed_dead)
            print(f"  Removed {len(removed_dead)} dead bookmarks.")
        else:
            print(f"  [dry-run] Would remove {len(dead)} dead bookmarks.")
    else:
        print("\n  URL checking skipped (--skip-check).")

    # ── Organize unfoldered bookmarks ──────────────────────────────────────
    # Refresh after possible removals
    orphans = collect_unfoldered(root)
    print(f"\nOrganizing {len(orphans)} top-level (unfoldered) bookmarks …")

    ai_map: Optional[dict[str, str]] = None
    if not args.no_ai and orphans:
        ai_map = build_ai_folder_taxonomy(orphans)

    if not args.dry_run:
        moved = organize_unfoldered(root, orphans, ai_map=ai_map)
        for folder, bms in sorted(moved.items()):
            print(f"  → '{folder}': {len(bms)} bookmark(s)")
    else:
        for bm in orphans:
            fp = (
                (ai_map or {}).get(bm.href) or
                _suggest_folder_rules(bm) or
                "Unsorted Bookmarks"
            )
            print(f"  [dry-run] '{bm.title[:60]}' → {fp}")

    # ── Write output ───────────────────────────────────────────────────────
    if not args.dry_run:
        write_bookmarks(root, str(output_path))
        print(f"\n✓ Cleaned bookmarks written to: {output_path}")
        _print_summary(root, removed_dead, output_path)
    else:
        print("\n[dry-run] No output file written.")
    print(
        f"\nDetailed log: {args.log}"
    )
    print(
        "\nTo import into Edge:"
    )
    print(
        "  Settings → Import browser data → Favorites or bookmarks HTML file"
    )
    print(
        "  → Select: "
        f"{output_path if not args.dry_run else '(output file)'}"
    )


def _count_folders(node) -> int:
    count = 0
    for child in node.children:
        if isinstance(child, Folder):
            count += 1 + _count_folders(child)
    return count


def _print_summary(root: Folder, removed: list, output: Path) -> None:
    all_bms = collect_all_bookmarks(root)
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Bookmarks remaining : {len(all_bms)}")
    print(f"  Dead links removed  : {len(removed)}")
    print(f"  Folders in output   : {_count_folders(root)}")
    print(f"  Output file size    : {output.stat().st_size:,} bytes")
    print("=" * 60)


if __name__ == "__main__":
    main()
