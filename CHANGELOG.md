# CHANGELOG

<!-- version list -->

## v1.3.3 (2026-04-21)

### Bug Fixes

- Remove Node.js/pnpm steps from Python lint workflow
  ([`f29edc8`](https://github.com/truss44/bookmark_cleaner/commit/f29edc8a035cc90985f881b749d0e1be4c8759d5))

### Chores

- Add .npmrc with pnpm configuration
  ([`38bf07f`](https://github.com/truss44/bookmark_cleaner/commit/38bf07fe0412afa3575f1183aa856faea29d3baf))

- Changing to pnpm
  ([`ddc6454`](https://github.com/truss44/bookmark_cleaner/commit/ddc645448058bb8362eb3cf2e9d3a1e708f94f47))

- Convert run commands to just pnpm
  ([`e77d464`](https://github.com/truss44/bookmark_cleaner/commit/e77d4648af9e2deff437c347f87e9454661f0c63))

- Remove .npmrc (Python project, not needed)
  ([`91bc709`](https://github.com/truss44/bookmark_cleaner/commit/91bc709f1697a00a52e840850136e44b395f2d63))


## v1.3.2 (2026-04-19)

### Bug Fixes

- Configure semantic-release to use commit-based versioning and sync package.json version
  ([`1a07039`](https://github.com/truss44/bookmark_cleaner/commit/1a070397c10abc75a3ae8cca88afe01458f7202a))


## v1.3.1 (2026-04-19)

### Bug Fixes

- Add error handling for OpenRouter API responses before parsing
  ([`e0006af`](https://github.com/truss44/bookmark_cleaner/commit/e0006afd0e91fd9ce4dd7c90ed4196d9e7d0fd78))


## v1.3.0 (2026-04-19)

### Bug Fixes

- Avoid double-remove in _merge_folder_into when recursing into subfolders
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Block AI-invented Unsorted-* folder variants
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Cap folder nesting at 3 levels deep ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Consolidate URL check header prints to prevent progress bar spacing overlap
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Enforce 3-level depth cap in _sanitize_folder_path
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Exclude _cleaned_ and _bookmarks_export output files from HTML auto-detection
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Guard against AI returning non-string subfolder values in batch parse
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Honor Ctrl+C between passes in consolidate_lone_folders
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Pause escape-watcher thread during input() prompts to restore keyboard
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Preserve original folders in _prune_empty_folders
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Resolve all flake8 E501 line-length violations in new browser export code
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Restore terminal settings on exit via atexit to fix broken stdin after run
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Sanitize AI folder paths at assignment so Unsorted Bookmarks never gains subfolders
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Use tty.setcbreak instead of setraw to preserve output newline handling
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

### Documentation

- Document auto-browser-detection and update Features section in README
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Document similar-folder merging, 3-level cap, and Ctrl+C/Escape cancellation
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Fix markdown table alignment in README ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Fix markdown table column alignment in README Options section
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

### Features

- Add duplicates removed count to summary output
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Add per-folder progress indicator during sub-folder creation pass
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Add sub-folder pass to organize bookmarks within existing folders
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Allow Escape key to trigger clean exit alongside Ctrl+C
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Auto-detect and export Chromium browser bookmarks
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Auto-detect and export Chromium browser bookmarks when no HTML file is present
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Flatten hollow folders that have no direct bookmarks
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Merge similar top-level folders using AI suggestions
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Preserve original folders from flattening; allow deletion only when truly empty
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Prompt user before removing duplicate bookmarks; add --delete-duplicates flag
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Remove duplicate bookmarks sharing the same URL
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Show AI model name in progress messages instead of generic 'AI'
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

- Show cancel hint (Ctrl+C or Escape) at startup
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))

### Performance Improvements

- Batch AI calls to reduce total API calls per run
  ([#6](https://github.com/truss44/bookmark_cleaner/pull/6),
  [`55edf9f`](https://github.com/truss44/bookmark_cleaner/commit/55edf9f8f9853ec690852e77f572930c6c145858))


## v1.2.2 (2026-04-18)

### Bug Fixes

- Preserve PERSONAL_TOOLBAR_FOLDER attribute in bookmark folders
  ([`5b67077`](https://github.com/truss44/bookmark_cleaner/commit/5b67077fd3897ea9b6b4c22efc458ab669e7032d))


## v1.2.1 (2026-04-18)

### Bug Fixes

- Correct semantic-release token configuration
  ([`17280d0`](https://github.com/truss44/bookmark_cleaner/commit/17280d08cd95ead17a5f7421000bdb40075257bb))


## v1.2.0 (2026-04-18)

### Bug Fixes

- Resolve all flake8 E501 line-length lint errors
  ([#5](https://github.com/truss44/bookmark_cleaner/pull/5),
  [`e15d57d`](https://github.com/truss44/bookmark_cleaner/commit/e15d57d806694f586a24bf31b9c02bec8c034fa0))

### Chores

- **deps**: Bump the github-actions group with 3 updates
  ([#4](https://github.com/truss44/bookmark_cleaner/pull/4),
  [`21deb23`](https://github.com/truss44/bookmark_cleaner/commit/21deb2372cba5c07836e3b0fc633aff899e3b8c6))

### Features

- Consolidate singleton folders and sort bookmarks alphabetically
  ([#5](https://github.com/truss44/bookmark_cleaner/pull/5),
  [`e15d57d`](https://github.com/truss44/bookmark_cleaner/commit/e15d57d806694f586a24bf31b9c02bec8c034fa0))


## v1.1.0 (2026-04-18)

### Features

- Add support for multiple AI providers (Anthropic, Gemini, OpenRouter) alongside OpenAI
  ([#3](https://github.com/truss44/bookmark_cleaner/pull/3),
  [`c32036e`](https://github.com/truss44/bookmark_cleaner/commit/c32036e0e2a8ed99556231c0fc6e5b7e6b228f95))

## v1.0.0 (2026-04-18)

- Initial Release
