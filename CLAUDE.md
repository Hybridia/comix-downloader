# Comix Downloader — Project Context

This file is auto-loaded by Claude Code. It captures what the project is,
how it's structured, the design decisions that matter when changing
things, and a running log of feature work. **Update the changelog at the
bottom whenever you ship a non-trivial change.**

---

## What this is

A Python desktop tool that downloads manga / doujinshi / webtoon
galleries from multiple sites and saves them as a folder of images, a
PDF, or a CBZ. Two front-ends share the same core:

- **CLI** (`main.py`) — Typer + Rich, interactive or `download` subcommand.
- **GUI** (`gui/main.py`) — PyQt6 + QML, dark-themed.

NSFW-tolerant — comix.to, nhentai.to, hitomi.la, hentaifc.com,
hentairead.com, hentaifox.com, toonily.com, manhwaread.com,
manhwa18.com, manhwa18.net, toomics (paid VIP), and mangafire.to are
all supported sources.

### Provider matrix at-a-glance

| Provider                | Auth                | Special infra                     | Notes                              |
|-------------------------|---------------------|-----------------------------------|------------------------------------|
| `comix.to`              | none                | **Playwright** (DOM scrape; site rotates anti-scraper keys daily) | Now uses `/api/v1`; chapter list + reader pages scraped from rendered DOM |
| `nhentai.to`            | none                | inline `_gallery` JSON parse      | Single-chapter gallery shape       |
| `hitomi.la`             | none                | `gg.js` per-deploy URL maths      | Single-chapter gallery shape       |
| `hentaifc.com`          | none                | obfuscated charcode-array decode  | Single-chapter gallery shape       |
| `hentairead.com`        | none                | preview-thumb host swap           | Single-chapter; one HTTP call only |
| `hentaifox.com`         | none                | hidden form fields + `g_th` JSON  | Single-chapter; reader gives ext   |
| `toonily.com`           | Cloudflare only     | curl_cffi handles CF; per-ch HTML | **Multi-chapter**; img CDN needs ref |
| `manhwaread.com`        | Cloudflare (hard)   | mangomic theme; b64 chapterData; **FlareSolverr required since 2026-10** | **Multi-chapter**; same theme as hentairead |
| `manhwabuddy.com`       | Cloudflare only     | plain HTML; `data-src` reader imgs | **Multi-chapter**; simplest provider in the matrix |
| `manhwa18.com`          | Cloudflare only     | plain HTML; `data-src` lazy imgs; rotating CDN | Multi-chapter NSFW manhwa; chapters use multiple CDN hosts |
| `manhwa18.net`          | none                | **Inertia.js SPA**; props embedded as JSON in `data-page` | Distinct from `.com` — Laravel+Inertia; same pornwa→min CDN history |
| `mangadistrict.com`     | Cloudflare only     | Madara theme; eager `src` reader imgs | Multi-chapter NSFW manhwa; same theme as webtoonscan but no FlareSolverr needed |
| `manga18fx.com`         | none                | Madara-ish HTML; `chapter-name` anchors; `/uploads/` reader imgs | Multi-chapter NSFW manhwa; plain HTTP, no anti-bot. Unrelated to manhwa18.* |
| `webtoonscan.com`       | Cloudflare (hard)   | **FlareSolverr required** — defeats curl_cffi AND Playwright | Multi-chapter Madara theme; aggressive bot management |
| `global.toomics.com`    | **paid login**      | `secrets.json` cookie/credential  | One active session per account     |
| `mangafire.to`          | anti-bot only       | **Playwright** (CF + VRF capture) | Heaviest provider; needs Chromium  |

---

## Repo layout

```
comix/
├── main.py                       CLI entry point
├── config.json                   User settings (project-root anchored, tracked)
├── secrets.json                  Per-provider auth (gitignored, mode 0600)
├── library.json                  Persistent download library (gitignored)
├── gui/
│   ├── main.py                   GUI entry point (wires setup_logging from config)
│   ├── app.py                    build_engine(): bridges + context props + main.qml (shared by main.py and tests)
│   ├── bridge/                   Python ↔ QML bridges
│   │   ├── manga_bridge.py       Fetches manga info via the provider router
│   │   ├── download_bridge.py    Drives concurrent chapter downloads + per-run failure log + library recording
│   │   ├── library_bridge.py     Library tab: list / update / remove / open folder + Check for Updates (review queue)
│   │   └── settings_bridge.py    Exposes ConfigManager + toomics auth to QML
│   └── qml/                      Views + components (SettingsDrawer, ProgressPanel, LibraryView, UpdatesView, …)
│       ├── Style/                QML module: Theme (live palette + motion) and Fx (effect bus) singletons, palettes.js
│       ├── fx/                   Reusable effects: FxButton, Ripple, ToastHost, ParticleBurst, Skeleton, CountUpText,
│       │                         PulseRings, AmbientGlow, ViewPane, ThemeWipe, FormatSelector, Spinner
│       └── logic/                Pure JS (.pragma library): chapters.js, badge.js, motion.js — unit-tested via QJSEngine
├── tests/                        unittest suite: QJSEngine logic tests + headless GUI smoke tests (temp config/library)
├── scripts/                      Local diagnostic + iCloud-sync scripts (run from user's machine)
│   ├── toomics_test.py           End-to-end probe for the toomics provider
│   ├── mangafire_test.py         End-to-end probe for the mangafire provider
│   ├── comix_test.py             End-to-end probe for the comix provider (fast + Playwright paths)
│   ├── webtoonscan_test.py       End-to-end probe for webtoonscan (verifies FlareSolverr)
│   ├── start_flaresolverr.sh     Start the local FlareSolverr (manhwaread / webtoonscan CF human checks)
│   ├── repack_to_cbz.py          Pack image folders into CBZs (Library tab's Convert button)
│   ├── icloud_inventory.py       Read-only walk of iCloud Manga folder → icloud_inventory.json
│   ├── icloud_match.py           Fuzzy cross-site search per inventory entry (Madara AJAX + comix API + HTML)
│   ├── icloud_to_library.py      Import matched inventory entries into library.json
│   ├── enrich_alternatives.py    Populate library.alternative_sources from inventory matches
│   ├── library_dedupe.py         Drop pre-existing library entries whose title matches an iCloud one
│   ├── library_relocate_to_icloud.py  Repoint pre-existing entries at iCloud + drop / collapse leftovers
│   ├── missing_chapters.py       Dry-run Update All — report what's on sites but not in iCloud
│   └── refresh_icloud.py         Wrapper: inventory → match → import → enrich
└── src/
    ├── api/comix.py              Low-level comix.to API — fast-path RC4 signing + Playwright fallback router
    ├── providers/                Per-site providers (uniform interface)
    │   ├── base.py               Provider ABC
    │   ├── router.py             URL → Provider matcher (registry)
    │   ├── comix.py              ComixProvider (wraps src/api/comix.py)
    │   ├── nhentai.py            NhentaiProvider (HTML + inline JSON parser)
    │   ├── hitomi.py             HitomiProvider (gallery JSON + gg.js URL maths)
    │   ├── hentaifc.py           HentaiFCProvider (charcode-array decode)
    │   ├── hentairead.py         HentaireadProvider (preview-thumb → full-image host swap)
    │   ├── hentaifox.py          HentaifoxProvider (form-field load_id + g_th JSON for extensions)
    │   ├── toonily.py            ToonilyProvider (multi-chapter manhwa; CF via curl_cffi)
    │   ├── manhwaread.py         ManhwareadProvider (multi-chapter; mangomic theme + b64 chapterData)
    │   ├── manhwabuddy.py        ManhwabuddyProvider (multi-chapter; plain HTML, no JS, simplest provider)
    │   ├── manhwa18.py           Manhwa18Provider (multi-chapter; plain HTML; rotating CDN per chapter)
    │   ├── manhwa18net.py        Manhwa18NetProvider (multi-chapter; Inertia.js SPA — JSON in data-page)
    │   ├── mangadistrict.py      MangadistrictProvider (multi-chapter; Madara; plain HTTP, no FlareSolverr)
    │   ├── manga18fx.py          Manga18fxProvider (multi-chapter; Madara-ish; chapter-name anchors + /uploads/ imgs)
    │   ├── webtoonscan.py        WebtoonscanProvider (multi-chapter; Madara; FlareSolverr required)
    │   ├── toomics.py            ToomicsProvider (cookie/credential auth)
    │   └── mangafire.py          MangafireProvider (Playwright VRF + CF cookies)
    ├── core/
    │   ├── models.py             MangaInfo, Chapter, DownloadConfig, OutputFormat
    │   ├── downloader.py         ImageDownloader, ChapterDownloader, MangaDownloader
    │   └── failure_log.py        Per-run failure log written to <download>/<title>/_failed.txt
    ├── formats/
    │   ├── images.py             Save raw images to disk
    │   ├── cbz.py                Build .cbz with ComicInfo.xml
    │   └── pdf.py                Build .pdf via ReportLab
    ├── cli/
    │   ├── app.py                Typer app + interactive flow
    │   ├── menus.py              Rich prompts (URL, chapters, settings)
    │   └── display.py            Rich tables / banners / summaries
    └── utils/
        ├── config.py             ConfigManager (single config.json at project root)
        ├── secrets.py            Loader/writer for secrets.json (per-provider auth)
        ├── library.py            LibraryManager (persists library.json — what's downloaded + source URLs)
        ├── chapters.py           Chapter-number parsing / normalisation from CBZ filenames (shared)
        ├── provenance.py         Which site did these CBZs come from? (ComicInfo <Web>, local files only)
        ├── update_check.py       Probe-only update check for one library entry (no downloads)
        ├── session.py            HTTP client: curl_cffi + rate limiter + FlareSolverr
        ├── retry.py              Generic retry-with-backoff decorator
        ├── hash.py               comix.to API request signing (HaruNeko port; fast path only)
        ├── comix_capture.py      Dedicated-thread Playwright fallback for comix (DOM scrape + URL reconstruction)
        ├── toomics_login.py      POSTs toomics' email login form, captures cookies
        ├── mangafire_vrf.py      Dedicated-thread Playwright service (CF cookies + VRF)
        └── logger.py             Lazy stderr logger, off by default
```

---

## Architecture

### Provider abstraction (`src/providers/`)

Each site implements the `Provider` ABC: `matches(url)`, `extract_code`,
`get_manga_info`, `get_chapters`, `get_chapter_images`,
`chapter_request_headers`, plus `image_referer` for per-site image
fetches. The router (`get_provider_for_url`) iterates the registry to
pick one. Adding a new site = drop a class in `providers/`, add it to
`router._REGISTRY`. Nothing in CLI / GUI / downloader needs changes.

`MangaInfo.source` is set by the provider so the GUI bridge can
re-derive the right provider on the download side (where only dicts
cross the QML boundary).

For sites where one "manga" is really a single multi-page gallery
(nhentai), the provider returns a single `Chapter` with
`pages_count = N`; the chapter selector skips itself when `len(chapters)
== 1`. Each `Chapter` may carry pre-fetched `image_urls`, which avoids
a second fetch when the gallery page already gave us everything.

### Download pipeline (`src/core/downloader.py`)

`MangaDownloader` runs N chapters in parallel via
`ThreadPoolExecutor(max_chapter_workers)`. Each `ChapterDownloader` runs
M images in parallel (`max_image_workers`).

`download_chapter`:
1. Calls `provider.get_chapter_images(chapter)` (cached if pre-fetched).
2. **Whole-chapter skip**: `_is_chapter_complete()` — if the format's
   final artifact (CBZ/PDF/full image folder) already has every page,
   return success without any HTTP.
3. **Per-image resume**: when intermediate images are kept (IMAGES, or
   CBZ/PDF with `keep_images=true`), `_scan_existing_pages()` lists
   `NNN.ext` files already on disk; we only fetch the missing indices.
4. `image_downloader.download_indexed_images([(idx, url), ...])` —
   parallel, with per-host rate limiter and adaptive throttling.
5. Materialize the artifact (save_images / create_pdf / create_cbz),
   merging existing + newly-downloaded pages when applicable.

`download_image` tries the primary URL plus extension fallbacks
(`webp/jpg/png/gif`) **once** per attempt. If every candidate 404s, it
fails fast (no retry — a missing URL stays missing). Only transient
errors trigger the retry-with-backoff loop.

Cancellation is a module-level `threading.Event`; call
`reset_cancel()` before each new run from the CLI / GUI bridge.

### Library (`src/utils/library.py` + `library.json`)

Persistent record of every manga we've successfully (or partially)
downloaded, plus the source URL we got it from. `library.json` lives
at project root, gitignored, version-tagged, atomic-rewritten under a
process-wide `RLock`. Shape (per entry):

```
{
  "source": "hentairead",
  "source_url": "https://hentairead.com/hentai/<slug>",
  "title": "...", "alt_titles": [...], "poster_url": "...",
  "output_format": "cbz", "download_path": "downloads",
  "folder": "<safe_title>",
  "added_at": "...", "last_updated_at": "...", "last_checked_at": null,
  "chapters": { "1": { "title": "...", "downloaded_at": "..." }, ... }
}
```

- **Primary key** is the *normalized* `source_url` (lowercase host,
  trailing-slash stripped). Same URL with two cosmetic variants stays
  one entry.
- **Recording is at the chapter level** (`record_chapter`). `chapters`
  is a dict keyed by `Chapter.number` (string). It's kept up to date
  as a snapshot of what's been written, but it is NOT the source of
  truth for the Update flow any more (see below).
- **Update flow uses on-disk filenames, not `library.chapters`.**
  `UpdateProbeWorker.run()` (see `gui/bridge/library_bridge.py`)
  reads the actual `.cbz` files in `download_path/folder`, parses
  chapter numbers from filenames, and uses that set for the diff
  against the site's chapter list. Chapter numbers are normalised
  (`62.5` ⇄ `62-5` ⇄ `62_5`, leading zeros stripped) so the same
  chapter compares equal across naming conventions. This is the fix
  for "Update re-downloaded chapters I already have" — the library
  was historically a stale snapshot from import time. With on-disk
  truth, anything the user manually moves into iCloud is immediately
  recognised; format mismatches between provider URL slugs and
  iCloud filenames stop causing duplicates.
- **Cross-site fallback.** When the primary URL's chapter list has
  nothing new past what's on disk, the worker tries
  `alternative_sources[]` (sorted by chapter_count desc by the
  enricher). First alt whose recorded max exceeds on-disk max
  drives the diff and the download dispatch points at that alt's
  provider/url.
- **Empty / missing target folder → silent "no updates".** Library
  entries for series the user abandoned (no CBZs anywhere) stop
  triggering downloads.
- **`_reload_if_changed()` on every locked method.** LibraryManager
  tracks `library.json`'s mtime and reloads before any mutation if
  the file changed externally (i.e. a helper script edited it while
  the GUI was open). Without this, every script in the iCloud
  pipeline had to be re-run because the GUI overwrote its work.
- **Recorded from both front-ends.** `DownloadWorker._download_single_chapter`
  (GUI) and `MangaDownloader.download_chapters` (CLI) both call
  `library.shared().upsert_manga(...)` once at the start of a run and
  `record_chapter(...)` after each chapter succeeds. Library failures
  are caught and warned — they must never break a download.
- **No artifact verification** at update time. If the user manually
  deletes a CBZ, the library still says it's downloaded. This is
  intentional — accidentally re-downloading 200 chapters because a
  parent folder got renamed would be worse than the inverse. Hit
  "Remove" → re-download to recover.
- **Check for Updates → review → approve** (Updates view, sidebar 🔔).
  See the 2026-10-21 changelog entry. The Library toolbar's old
  "Update All" button (download everything found, no questions) was
  replaced by "Check for Updates"; the `updateAll()` slot remains.
- The GUI's `LibraryBridge` (`gui/bridge/library_bridge.py`) exposes
  these slots to QML: `listEntries`, `updateEntry(url)` and
  `updateAll()` (probe + download), `checkStatusAll()` (probe only,
  no downloads), `setStatus(url, status, manual)`, `removeEntry(url)`,
  `openFolder(url)`, `openWebsite(url)` (browser), `convertToCbz(url)`.
  `attach_download_bridge()` wires the cross-bridge call in `gui/main.py`.

### iCloud → Library workflow (`scripts/icloud_*.py` + `refresh_icloud.py`)

The macOS-flavoured side of the project. Users who keep their manga
collection in `~/Library/Mobile Documents/com~apple~CloudDocs/Manga/`
(Apple iCloud Drive) can have the Library tab automatically reflect
that collection, with multi-site URL tracking and status badges.

The iCloud folder is **read-only** as far as our code goes — every
script in this pipeline reads from iCloud and writes only to
`library.json` and the project's own report files. Phase 4 (chapter
updates from sites) writes to `config.download_path` (typically
`./downloads/`), not iCloud — the user moves new chapters into
iCloud manually when they want to.

Pipeline:

1. **`icloud_inventory.py`** — read-only walk of the iCloud folder.
   Per top-level folder: cleaned title (END suffix stripped, flagged
   as `marked_complete_by_user`), chapter count by format detection
   (`per_chapter_cbz` / `per_volume_cbz` / `single_cbz` / `mixed` /
   `image_folders` / `pdf`), total size. Output:
   `icloud_inventory.json` + `icloud_inventory.md` (gitignored).
   **Idempotent re-runs** — on a re-scan, Phase-2 match data for
   existing folders is carried forward; only genuinely-new folders
   need fresh searches.

2. **`icloud_match.py`** — cross-site fuzzy search. For each
   inventory entry, queries every provider that exposes a search
   endpoint (Madara AJAX for toonily/mangadistrict; HTML for
   manhwaread/manhwabuddy/nhentai/hentairead/hentaifox;
   comix.to keyword API). Records every high/medium-confidence
   match with `{provider, url, title_on_site, status,
   match_score, match_confidence}`. Aggregates effective_status
   by per-provider top match: any "completed" wins; any "ongoing"
   second; "unknown" otherwise. User's END marker forces
   "completed". `--unknowns-only` mode skips already-resolved
   entries.

3. **`icloud_to_library.py`** — imports each matched inventory
   entry into `library.json`. Picks the best non-skipped match
   (`ALLOWED_PROVIDERS = SERIAL_ALLOWED ∪ GALLERY_ALLOWED`),
   constructs a library entry with `download_path` = iCloud root,
   `folder` = the iCloud folder name (so the new entry's truth set
   IS the iCloud filenames). `origin = "icloud_import"` so dedupe
   later knows which entries are pipeline-built. Chapter numbers
   extracted from filenames into the entry's `chapters` dict for
   compatibility (Update doesn't strictly need it, but the GUI
   shows the count).

4. **`enrich_alternatives.py`** — for each library entry, walks
   inventory matches and records non-primary high/medium matches
   as `alternative_sources[] = [{provider, url, title_on_site,
   status, chapter_count, ...}]`. Sorted desc by chapter_count.
   The LibraryCard renders these as the "Also on:" chip row,
   click → opens the URL in browser. Used by UpdateProbeWorker as
   the fallback list when the primary site has nothing new.

5. **`library_dedupe.py`** — collapses pre-existing library entries
   whose title or folder fuzzy-matches an iCloud-imported entry.
   Two fuzz strengths: strict (alphanumerics only) and loose
   (strips TOP / END / Uncensored / Decensored / Raw / Hot /
   Complete suffix words too — catches "Glory Hole Shop TOP" vs
   iCloud's "Glory Hole Shop").

6. **`library_relocate_to_icloud.py`** — for any pre-existing
   library entry that survives dedupe but has an iCloud counterpart,
   rewrites `download_path`/`folder` to point at iCloud and tags
   `origin = "icloud_import"`. Drops entries with no iCloud
   counterpart entirely (these are series the user downloaded
   in-app once and never moved to iCloud — usually noise like
   Strawberry Love or Bastard). Final pass collapses entries that
   resolve to the same iCloud folder, keeping the richer
   `alternative_sources` list. After this, **every** library
   entry's truth folder lives in iCloud.

7. **`missing_chapters.py`** — read-only dry-run Update All. Walks
   library entries, probes primary + alternatives, lists chapters
   on any site that aren't in iCloud (format-normalised). Output:
   `missing_chapters_report.md` (gitignored). Run when you want to
   know what's missing without committing to actual downloads.

8. **`refresh_icloud.py`** — wrapper that runs inventory → match
   (`--unknowns-only`) → import → enrich in sequence. The standard
   "I added new manga to iCloud, sync the library" command.
   `--skip-match` / `--skip-import` / `--skip-enrich` flags for
   debugging individual stages.

All output files are gitignored — they contain the user's title list.

### Per-run failure log (`src/core/failure_log.py`)

Both `MangaDownloader.download_chapters` (CLI) and `DownloadWorker.run`
(GUI) instantiate a `FailureLog(manga, config)`, record failures as
chapters complete, then call `.write()` at the end. Output:
`<download_path>/<safe_title>/_failed.txt`, tab-separated
`number\ttitle\treason`. On a clean run the file is removed so the
manga directory stays tidy. Recommend telling the user "re-run, the
on-disk skip logic will whoosh past completed chapters and only retry
failures."

### Auth / secrets (`src/utils/secrets.py` + `secrets.json`)

`secrets.json` lives at project root, **gitignored**, mode 0600. Shape:

```json
{
  "toomics":   { "email": "...", "password": "...", "cookie": "...", "user_agent": "..." },
  "mangafire": { "cookie": "...", "user_agent": "..." }   // optional manual fallback
}
```

`get_provider_secrets(name)` reads the named block;
`save_provider_secrets(name, dict)` merges + atomic-rewrites (preserves
sibling provider blocks). Mode 0600 is reasserted after every write.

Auth model varies per provider:

- **Toomics**: real paid login. Two paths, both end up writing the
  same `cookie` field:
    - **Credential login** (preferred): user enters email + password in
      Settings → TOOMICS LOGIN → 🔐 Login. `src/utils/toomics_login.py`
      POSTs `/en/auth/layer_login` (`user_id`/`user_pw`/`keep_login=Y`)
      then GETs `/en` to finalise. The flow accepts `existing_cookies`
      and merges the response on top, so persistent state cookies
      (`GTOOMICSTOOMICS_USERTYPE=VG`, `tw_adultYN`, etc.) survive a
      re-login and VIP listings keep rendering.
    - **Cookie paste** fallback: user pastes the browser's cookie header
      (also editable in Settings).
- **Mangafire**: no account, but Cloudflare-protected. The provider
  defaults to driving Playwright (see below) and only consults the
  `mangafire.cookie` field as an emergency fallback when Playwright
  fails. **There's no UI section** for this anymore (removed
  2026-05-04); manual editing of `secrets.json` is the only way to set
  it, intentionally.

### Playwright service (`src/utils/mangafire_vrf.py`)

Mangafire requires **two** browser-derived secrets we can't reproduce
in pure Python:

1. **Cloudflare cookies** (`cf_clearance` + `__cf_bm`) — minted by a
   real Chromium passing the CF challenge. Plain `requests` is rejected.
2. **VRF token** — a per-AJAX-path query parameter computed by
   obfuscated client-side JS. We snoop the value off any outbound
   request whose URL contains `vrf=`.

`MangafireVRFGenerator` is a singleton (`shared()`) that owns one
Chromium instance. **Critical threading model**: Playwright's sync API
needs an asyncio event loop in the calling thread, and shared
`Browser`/`Page` objects can't safely cross threads. Qt's
`ThreadPoolExecutor` workers don't have an event loop and hit
`RuntimeError: There is no current event loop in thread 'ThreadPoolExecutor-N'`
the moment they touch Playwright. The fix:

- One **dedicated worker thread** (`mangafire-playwright`) owns
  Chromium. Workers from anywhere submit `(callable, args, future)`
  items to a `queue.Queue`; the dedicated thread services them and
  fulfils the future. All Playwright operations run sequentially in
  that thread.
- Public API is the `_submit(...)` helper. Three high-level methods:
  - `get_vrf(ajax_path, navigate_to=...)` — exact-path snoop.
  - `capture_ajax_url(path_regex, navigate_to=...)` — regex snoop;
    used by mangafire to recover both the chapter id AND vrf from
    `/ajax/read/chapter/<id>?vrf=...` in a single navigation.
  - `get_cf_state(force=False)` — returns `(cookies, user_agent)` from
    the live Chromium context. `force=True` skips the 25-min cache
    after a navigation has just happened.
- `_HEADLESS` is on by default; flip with `MANGAFIRE_HEADLESS=0` to
  show a real Chrome window (some Cloudflare deployments only trust
  visible Chromium).
- Capture timeout is 30 s; provider retries up to 3 times with backoff
  to absorb mangafire's bursty CDN throttling. **Do not enable retry
  on body-status 403** — Cloudflare logs that pattern and 1015s the IP.

### HTTP layer (`src/utils/session.py`)

Three layered defenses against blocks:

1. **curl_cffi browser impersonation** (default, `chrome120`) — sends
   real Chrome TLS / HTTP-2 / `Sec-Ch-Ua` fingerprints. Defeats most
   Cloudflare fingerprint blocks in-process. Falls back to plain
   `requests` if `curl_cffi` isn't installed.
2. **Adaptive per-host rate limiter** — token bucket per hostname,
   starts at 4 req/s, halves on 429/403, recovers +25% after 25
   successes. Bounded by `min/max_requests_per_second`. Stops the
   "after N downloads my IP gets blocked" pattern → no VPN required.
3. **FlareSolverr fallback** — only invoked when curl_cffi still hits
   a real JS challenge. Logs at info-level (not error) when missing.

`SessionManager` is a singleton (`get_session()`); `reset_session()`
drops it if config changes mid-run.

### Configuration (`src/utils/config.py`)

Single `config.json` **anchored to the project root** (parent of `src/`).
This is critical: previously the path was relative, and the GUI sometimes
wrote a second `gui/config.json` depending on CWD, causing settings
drift. `ConfigManager()` always resolves to `<project_root>/config.json`
unless an explicit path is passed.

Defaults live in `ConfigManager.DEFAULT_CONFIG`. Notable keys:

- `output_format` — `images` | `pdf` | `cbz`
- `keep_images` — keep intermediate image folder when building PDF/CBZ
- `max_chapter_workers`, `max_image_workers`
- `use_curl_cffi`, `impersonate` — HTTP client knobs
- `requests_per_second_per_host`, `min_requests_per_second`,
  `max_requests_per_second` — rate limiter
- `flaresolverr_url` — fallback service
- `verify_ssl` — set false only if the local CA store is broken

---

## Conventions / gotchas

- **Don't import from `src.core` package directly.** It used to re-export
  `MangaDownloader`, which created a circular import once the providers
  package was added. `src/core/__init__.py` now only re-exports models.
  Reach into submodules instead.
- **Don't break `src/api/comix.py`.** `ComixProvider` is a thin wrapper;
  the underlying RC4-hash request signing in `src/utils/hash.py` is
  ported from comix.to's TS bundle and is fragile.
- **Per-request `Referer` matters.** Each provider sets `image_referer`;
  the chapter downloader passes that through `headers={}` on every
  image request. Don't drop it.
- **404 isn't transient.** The image downloader's outer retry loop
  explicitly skips retry when every extension candidate 404s.
- **Filename safety.** `MangaInfo.get_safe_title()` and
  `Chapter.get_safe_folder_name()` strip everything except
  alphanumerics, space, dash, underscore. Non-Latin titles (e.g.
  Japanese) become underscores — that's fine, it stays unique enough.
- **No CLAUDE.md / README / docs unless asked.** This file is the
  exception; user explicitly requested it.
- **Toomics + mangafire bypass `SessionManager` for HTTP.** Both
  providers maintain a private `requests.Session()` because:
  - curl_cffi's `chrome120` impersonation overrides the User-Agent
    we set for toomics (which binds the session to a *specific* UA).
  - Mangafire needs cookies that came from the Playwright Chromium
    instance, attached precisely to the request — easier with a private
    session than negotiating with the global limiter / FlareSolverr.
  Image fetches still go through `get_session()` because the per-host
  rate limiter is useful there.
- **`Chapter.volume` is the per-provider stash field.** Toomics puts
  the toon id there; mangafire puts the alphanumeric chapter id (or
  empty string if it'll be discovered at download time). The model's
  numeric `chapter_id` field is reserved for ints. The GUI's
  download-bridge serialization preserves `volume` end-to-end.
- **GUI must call `setup_logging`.** `gui/main.py` reads
  `enable_logs` from config and calls `setup_logging(enable=...)` at
  startup. Without this, `logger.info`/`warning`/`debug` calls in
  providers are silently swallowed even when the user toggles "Enable
  Debug Logs" in Settings. CLI does this in `src/cli/app.py`.
- **GUI colours and motion go through `Style`.** Every QML file does
  `import Style` and binds colours to `Theme.*` (never hard-code a
  palette hex — `tests/test_theme.py` scans for that). Every animation
  duration goes through `Theme.dur(ms)` so Settings → Animations can
  make the app instant; decorative loops sit in
  `Loader { active: Theme.animations }`. Blur / masks / shadows
  (MultiEffect) are skipped when `Theme.software` (`--cpu`). App-wide
  effects are requested through the `Fx` singleton
  (`Fx.toast(text, kind)`, `Fx.flyRequested`, `Fx.themeWipeRequested`).
- **GUI tests:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -t .`
  Tests build the real engine against temp `config.json` /
  `library.json` / `pending_updates.json` and fail on any QML warning.
  MultiEffect does not render in offscreen grabs — check blur visually
  on the real platform.
- **`print(..., flush=True)` for unconditional diagnostics.** Provider
  code that needs to be visible in the user's terminal regardless of
  the logging toggle uses raw `print` — see the `[mangafire]` /
  `[vrf-worker]` traces. Logger calls go through the toggle; prints
  always show.
- **Don't import Playwright at module top-level.** `mangafire_vrf.py`
  imports `playwright.sync_api` lazily inside `_do_ensure_browser()` so
  importing the module doesn't fail on machines without Playwright.
  The module raises `VRFUnavailable` (a subclass of `RuntimeError`)
  with a clear install command when Playwright is missing.
- **`MangafireVRFGenerator` uses `RLock`, not `Lock`.** Playwright's
  sync API drains queued `request` events between our calls, firing
  `_on_request` on the same thread that already holds the lock. A
  non-reentrant lock deadlocks instantly. Same applies to any future
  Playwright integration; default to `RLock`.
- **GUI download progress signals (multi-job).** Every per-job signal
  carries the worker's ``job_id`` as its first argument so multiple
  concurrent downloads stay visually separated:
  `jobStarted(jobId, title, posterUrl, totalChapters)` (fires once
  per ``startDownload`` call — tells the UI to mint a new card),
  `chapterStarted(jobId, name)` (worker picked it up; used for the
  `Preparing…` sliver during slow VRF capture),
  `chapterProgress(jobId, name, current, total)`,
  `chapterComplete(jobId, name, success, message)`,
  `overallProgress(jobId, done, total)`,
  `downloadFinished(jobId, successful, failed)`.
  The `DownloadBridge` keeps a ``self._workers: dict[job_id, worker]``
  and self-evicts on finish/error. ``downloadStarted()`` (no args)
  remains as a "switch tab" trigger only — it no longer resets the
  panel, since that would clobber other in-flight downloads.
  ``cancelDownload()`` cancels every running job (the cancel
  ``threading.Event`` in ``src.core.downloader`` is process-wide).
- **Per-run failure log.** Every download session writes
  `<download>/<safe_title>/_failed.txt` with one line per failed
  chapter. Re-running the same selection skips already-on-disk
  chapters via existing resume logic, so the natural retry pattern is
  "select all → Download" — failures get logged, successes are
  untouched.

---

## How to run

```bash
pip install -r requirements.txt           # one-time
python -m playwright install chromium     # mangafire only — ~150 MB into .venv

# CLI
python main.py                             # interactive
python main.py download "<url>" -f cbz     # direct

# GUI
python gui/main.py
python gui/main.py --cpu                   # software rendering

# Force visible Chromium for mangafire (helps if CF blocks headless):
MANGAFIRE_HEADLESS=0 python gui/main.py
```

FlareSolverr is **optional now**; only start it if a download actually
fails with a hard challenge. Playwright is also optional but
recommended for mangafire — without it the provider only works if the
user manually drops a fresh `cf_clearance` cookie into
`secrets.json["mangafire"].cookie`.

### Per-provider local diagnostic scripts

When something breaks for a paid / anti-bot site, get the user to run
the matching script locally — it prints exactly what each pipeline
stage saw:

- `python scripts/toomics_test.py [4698|<url>]` — listing parse,
  chapter classification by tier label, image-URL discovery, sample
  image fetch.
- `python scripts/mangafire_test.py [<url>]` — manga page parse,
  chapter list (public endpoint), VRF capture for ch 1, image-list
  fetch, sample image download.

Both scripts read auth from `secrets.json`. They write nothing to
`secrets.json`. Output goes to stdout with clear stage labels — paste
back to debug.

---

## Changelog

Newest first. Bullet what changed and *why* (the why ages better than
the what).

### 2026-10-25 — GUI themes + motion (Ink & Sakura / Neon Tokyo / Ember)
- **Three live themes**, picked in Settings → Appearance with a
  circular colour wipe from the click point (`fx/ThemeWipe.qml`:
  snapshot of `windowRoot` + inverted circular MultiEffect mask;
  crossfade under `--cpu`). Default **Ink & Sakura**. Config keys
  `theme`, `animations_enabled`, `ambient_glow`. Design + plan:
  `docs/superpowers/specs|plans/2026-10-25-qml-motion-themes*.md`;
  interactive mockups were in `.superpowers/brainstorm/` (gitignored).
- **Why QML, not an HTML front-end:** the user wanted nicer visuals,
  not a second app; QML does the same effects natively and a second
  front-end would double every future feature.
- **Motion everywhere:** springy buttons with ripples, sliding sidebar
  indicator, view transitions (slide/fade/un-blur), toasts, drifting
  background glow, skeleton loaders, count-up numbers, confetti on
  finished downloads, fly-to-Downloads bubble + Downloads badge
  (chapters still queued, counts down), animated URL validation
  (match glow, shake on unknown URL, drag-a-link drop zone), manga
  card reveal (blur-up cover, rising title letters, popping tags),
  chapter list with text filter, shift-click ranges and cascading
  Select All, Library cards that rise in / tilt / flip (ⓘ) with a
  check → spinner → "✦ N new" morph, Updates chips that pop and a
  rolling Download count, flowing download progress bars, Settings
  drawer that springs in over a blurred app with hold-to-reset.
- **Animations off** (Settings) makes every duration 0 and removes
  decorative loops; everything still works.
- **Fixed on the way:** Library cards were wider than the window (the
  toolbar's minimum width forced the whole column wide — buttons cut
  off); Settings worker spinboxes had a binding loop; the Updates empty
  state wasn't centred.
- `gui/app.py:build_engine` now owns engine setup (main.py + tests).
- **New test suite** in `tests/` (stdlib unittest, 52 tests).

### 2026-10-24 — Library card "Downloading…" line now clears
- The card status set on dispatch ("Downloading N new chapters…") was
  never replaced, so it stayed after the download finished.
  `DownloadBridge.libraryJobFinished(library_url, successful, failed)`
  fires when a job whose `manga_dict` carries `library_url` ends
  (`failed = -1` on worker error); `LibraryView` swaps the line for
  "Downloaded N new chapters" / "N failed". Not emitted for jobs
  killed by the global cancel (`terminate()`).

### 2026-10-21 — fail fast on Cloudflare human checks (manhwaread)
- **manhwaread.com now serves Cloudflare's interactive challenge**
  (`cf-mitigated: challenge`, "Just a moment…") on every request —
  verified against curl_cffi chrome120/131/safari17/18/firefox133, and
  Playwright Chromium headless AND visible (never mints
  `cf_clearance`, same as webtoonscan). The provider-matrix note "no CF
  challenge in practice" is out of date. Only FlareSolverr can pass it.
- **New `CloudflareChallengeError(NonRetryableError)`** in
  `session.py`. When a response is still a human check after the
  FlareSolverr attempt, `SessionManager.get` raises it with a message
  naming the host and the remedy (start FlareSolverr / pick another
  site), instead of returning the 403 for the provider's
  `raise_for_status` → `retry_with_backoff` to grind through 4 attempts
  (~15 s per series, ending in a bare "HTTP Error 403:").
- **Per-host latch, 60 s TTL** (`_challenged_hosts`), mirroring the
  TLS-block latch: the rest of a bulk check skips the host instantly;
  starting FlareSolverr recovers within a minute without a restart.
- **Human checks no longer halve the host's rate limit** — it isn't
  throttling, and slowing down doesn't change the answer.
- Callers that catch generic exceptions keep working (comix fast path
  still falls back to Playwright).
- **FlareSolverr on this Mac:** installed from source at
  `~/Documents/FlareSolverr` (v3.5.2, own venv, uses the installed
  Google Chrome). Start with `scripts/start_flaresolverr.sh`. Two
  macOS gotchas baked into the script: `HEADLESS=true` means Xvfb
  (Linux-only) and crashes at startup, so it runs `HEADLESS=false`
  (a Chrome window flashes while solving); and the default bind is
  `0.0.0.0`, so it sets `HOST=127.0.0.1`. Verified: manhwaread
  challenge solved in ~15 s, chapter list + image fetch OK afterwards.
- **The app starts FlareSolverr itself** (`src/utils/flaresolverr_launcher.py`).
  On the first Cloudflare human check, `_solve_cloudflare` calls
  `ensure_running()`: if nothing answers on the (localhost) FlareSolverr
  URL and an install exists at `flaresolverr_dir` (config; "" =
  `~/Documents/FlareSolverr`), it launches it with the same env as the
  script, waits up to 60 s for it, then solves. Lazy on purpose — no
  Chrome unless a site actually challenges. The process is started in
  its own process group and killed with its Chrome children at app exit
  (`atexit`); a FlareSolverr the user started is never touched. Failed
  launches back off 5 min. Output: `<install>/flaresolverr-autostart.log`.
  Disable with `"flaresolverr_autostart": false`. The script remains for
  running it by hand.
- **FlareSolverr only for a real human check** (`SessionManager._is_human_check`:
  `cf-mitigated: challenge`, or a 403/503 *HTML* page with challenge
  markers). Previously ANY 403 from a `Server: cloudflare` host was sent
  to FlareSolverr — harmless while it never ran, but with auto-start
  every comix series opened Chrome 4× (once per `retry_with_backoff`
  attempt): comix answers `403 {"message":"Missing token."}` as JSON,
  which is the site's own refusal, not a challenge. Also: after taking
  the lock, the request is retried first, so concurrent workers that
  hit the same challenge reuse one solve instead of each launching one.
- **comix.to `/api/v1/manga/{hid}` now needs a token too** (403
  `missing_token`, 2026-10-21) — the "works without any token" note in
  the 2026-05-10 entry is out of date, so comix series currently fail
  to check/update. Not fixed yet.
- **FlareSolverr's Chrome runs in the background (no window).**
  `scripts/flaresolverr_hidden.py` wraps FlareSolverr: it monkeypatches
  `undetected_chromedriver.ChromeOptions` to add the flags in
  `FS_EXTRA_CHROME_ARGS` (`--headless=new`), then runs FlareSolverr's
  `flaresolverr.py` unchanged — no edits to the checkout. Chrome's new
  headless mode still passes manhwaread's Cloudflare check (~12 s), and
  FlareSolverr strips "Headless" from the User-Agent it reports.
  Launcher + start script both use it; config `flaresolverr_hidden`
  (default true) turns it off for debugging. Verified with a `ps`
  watcher: 3/3 fresh runs, 0 windowed Chrome processes.
- **Chrome 155 + undetected-chromedriver flakiness, measured:** the
  first solve after a FlareSolverr start fails 6/6 ("no such window:
  target window already closed", ~3 s) and the retry passes 6/6; the
  startup self-test itself dies ~1 in 6 launches with the same error.
  `--no-first-run` / `--no-default-browser-check` don't help. Handled
  by the solve retry and `_LAUNCH_ATTEMPTS = 3` in the launcher.
- **No more FlareSolverr `sessions.create`.** Its persistent-session
  mode is flaky on macOS ("no such window: target window already
  closed" within milliseconds, ~half the time); a plain `request.get`
  solved reliably (~12 s). `_solve_cloudflare` now sends one
  `request.get` with one retry — the first request after a fresh start
  sometimes hits the same browser error and the retry passes.

### 2026-10-21 — Check for Updates: review before download + source detection
- **New Updates view** (sidebar 🔔, with a pending-count badge).
  "Check for Updates" probes every ongoing library entry and lists
  the series with new chapters; **nothing downloads until the user
  ticks chapters and clicks "Download N chapters"**. Per series:
  include checkbox, a site dropdown (each option shows latest chapter,
  how many are new, and ★ when the files came from there), chapter
  chips, and an opt-in "+ N older chapters missing (gaps)" section.
  "Skip" hides a series until the next check. Replaces the Library
  toolbar's Update All button, which downloaded without asking — the
  foot-gun this feature exists to remove. Per-card "Update" is
  unchanged (it's an explicit single-series action).
- **Source detection (`src/utils/provenance.py`).** Every CBZ this app
  builds has the series URL in `ComicInfo.xml` `<Web>`; that is ground
  truth for where the chapters came from, unlike the title-fuzzy
  matching `icloud_match.py` does. Image filenames are useless for
  this (the downloader renames pages to `NNN.ext`), and third-party
  CBZs (Yen Press rips etc.) carry no URL, so they contribute nothing.
  On the first live run 14 of 180 folders had detectable files, and
  in most of those the detected site differed from the library's
  title-matched primary.
- **iCloud cloud-only files are never opened.** ~240 of the ~290
  iCloud Manga folders were entirely evicted (dataless placeholders);
  reading any byte makes macOS download the whole CBZ. `is_cloud_only`
  checks the `SF_DATALESS` stat flag (no file read) and skips them.
  Filenames are still listed, so on-disk chapter numbers are unaffected.
  Detected sources are persisted on the entry (`detected_sources`,
  merged across scans) so a site found while a file was local stays
  known after iCloud evicts it again. The `Manga/.reader_state.json`
  file (the iPhone reader app's sync state) is never touched: scans
  only look inside subfolders, and everything here is read-only.
- **Probe order** (`src/utils/update_check.py`): detected sources →
  primary URL → `alternative_sources`. Alternatives are probed only
  when the enricher saw them past the best chapter found so far, so a
  full-library check doesn't hit every mirror. Recommended source =
  most new chapters, tie-broken by "your files came from here", then
  primary. New chapters are split into `newer` (past the highest
  on-disk chapter — pre-selected) and `gaps` (holes below it — shown,
  not selected; often deliberate).
- **Manual selection.** Every Library card has a checkbox on its
  cover; with any ticked, the toolbar button becomes "Check N
  selected" (`LibraryBridge.checkForUpdatesFor(urls)`). Ticked series
  are checked even when marked completed — ticking is explicit. The
  toolbar's "Select all shown" respects the current search/filters.
- **Per-card "Check for new"** (replaces the card's direct-download
  "Update" button). `LibraryBridge.checkEntry(url)` runs on its own
  thread — it doesn't queue behind a full-library check — and reports
  via `entryCheckFinished(url, QVariantMap)`; the card shows
  "✦ N new (ch a–b) on <site>" with **Download N new**
  (`downloadRecommended(url)` = all `newer` chapters from the
  recommended site) and **Review…** (opens Updates). Note the signal
  type: a plain `dict` arrives in QML as an opaque object (every field
  undefined), so QML-bound signals must declare `"QVariantMap"`.
- **iCloud folder fallback** (`update_check.resolve_folder`). 76 entries
  pointed at `./downloads/<title>` folders that no longer exist because
  the user had moved the series into iCloud by hand — every check
  skipped them as "no files". When the recorded folder has no chapters,
  the iCloud Manga subfolder is found by fuzzy name (same strict/loose
  rules as `scripts/missing_chapters.py`) and the entry is repointed
  there via `LibraryManager.relocate` (origin → `icloud_import`). Also
  used by the per-card Update probe and the pre-download disk re-check.
- **Duplicate entries → one review item.** Several entries can resolve
  to one iCloud folder ("Secret Class" / "Secret Class TOP" / "Secret
  class"). The review list keeps one item per folder: the one offering
  more new chapters, or the one the user explicitly checked.
- **Why a full check covers ~89 of 264 entries:** 175 are completed
  and skipped; of the rest, ~40 have no parseable CBZ chapters (38
  point at `./downloads/...` folders that no longer exist, a few hold
  image folders or per-volume CBZs). Those return instantly and are
  counted as "skipped (no chapter files)" in the summary rather than
  silently as "up to date". (Most of those ~40 were the missing
  `./downloads` folders fixed by the iCloud fallback below — after it,
  ~11 remain: image folders, per-volume CBZs, or no iCloud match.)
- **Results persist** in `pending_updates.json` (project root,
  gitignored) so a long check survives an app restart. `applyUpdates`
  re-reads the folder before dispatching, so chapters moved into
  iCloud since the check aren't fetched twice.
- **Fixed: updates split / unhooked library entries.** Two pre-existing
  bugs in the Update path:
    1. `upsert_manga` rebuilt the entry from scratch, so a download
       for an existing series overwrote `download_path`/`folder` with
       `./downloads/<title>` and dropped `alternative_sources`,
       `origin` and any other script-written field. For an iCloud
       entry, Update then read the wrong folder and treated the whole
       iCloud collection as missing. Now unknown fields are carried
       over, and `icloud_import` entries keep their iCloud location.
    2. Downloading from an alternative site upserted under the *alt's*
       URL, creating a second library entry per site. Update dispatches
       (both the new flow and per-card Update) now set
       `manga_dict["library_url"]`; `DownloadWorker` skips the upsert
       and `record_chapter(..., library_url=...)` files chapters under
       the original entry.
- Chapter-number helpers moved from `gui/bridge/library_bridge.py` to
  `src/utils/chapters.py` (non-GUI code needed them). The underscore
  aliases stay in `library_bridge` because `scripts/missing_chapters.py`
  imports them from there.
- **Downloads still go to `config.download_path`, not iCloud** —
  unchanged policy; the summary line after approval says so.
- **Verified:** detection over all 180 library folders in 0.5 s with
  no iCloud downloads; live check of "Someone Stop Her!" recommended
  manhwabuddy (detected) with ch 77–78 while the primary
  (mangadistrict) was SNI-blocked; offscreen GUI run against a copy of
  library.json with a stubbed downloader confirmed chip toggles, site
  switching, gap selection, the on-disk re-check, badge updates and
  dispatch under `library_url`.

### 2026-08-09 — fail fast on network-level (SNI) blocks
- **Symptom:** a provider stops fetching entirely on some networks.
  Root cause is *not* in this repo — an on-path middlebox (ISP or
  network filter) kills the TLS handshake based on the hostname in the
  ClientHello, so the failure lands before a single HTTP byte moves.
  Diagnosis that nails it: sending the blocked SNI to an **unrelated**
  IP (example.com's) fails identically, while an unblocked SNI to the
  blocked site's own IP succeeds. DNS is clean. Fixed by a VPN.
- **Partial blocks are possible.** A filter may block a site domain
  but not its image CDN — that doesn't rescue a download, since the
  reader page must be fetched first to learn the image URLs.
- **None of our three defenses can help here** and it's worth
  internalising why: curl_cffi impersonation, the rate limiter and
  FlareSolverr all operate at or above HTTP. A ClientHello-level block
  precedes all of them. Playwright is equally powerless. **A VPN is
  the only fix** — don't go hunting for a code-side bypass next time
  this signature appears.
- **New `NonRetryableError` base in `src/utils/retry.py`.** Both
  `retry_with_backoff` and `RetryableDownloader.download_with_retry`
  now re-raise it instead of retrying. Same philosophy as the existing
  "404 isn't transient" rule in the image downloader.
- **New `NetworkBlockedError` in `src/utils/session.py`** (subclass of
  the above). `SessionManager.get()` inspects failed requests for the
  injected-packet signature and raises it with an actionable message
  naming the host and pointing at the VPN. Detection matches all three
  TLS stacks' wording for the same event — BoringSSL/curl_cffi
  (`WRONG_VERSION_NUMBER`), OpenSSL (`wrong version number`) and
  LibreSSL (`tlsv1 alert protocol version`) — because which one you
  see depends on the client, not the cause.
- **Per-host latch with a 60 s TTL** (`_blocked_hosts`). Once a host
  blocks, further requests to it fail instantly — no socket, no
  rate-limiter token, no FlareSolverr round-trip. The TTL is the
  important part: it lets **turning the VPN on recover without
  restarting the app**. A permanent latch (like comix's
  `_FAST_PATH_BROKEN`) would be wrong here because the condition is
  expected to change mid-session. `clear_blocked_hosts()` forces it.
- **`ImageDownloader.download_image` bails on `NonRetryableError`.**
  It previously would have burned 4 extension candidates × 4 attempts
  per image against a wall — the worst case in the codebase, since a
  blocked CDN would multiply that by every page in the chapter.
- **Before:** raw `SSLError` traceback after ~6 s of pointless backoff,
  with nothing telling the user their network was the problem.
  **After:** immediate, plain-language error naming the host.
- **Known unrelated bug spotted while verifying, NOT fixed** (needs a
  call on filename impact): `ToonilyProvider._parse_chapters` derives
  its sort key with `float(num_str)`, but toonily writes decimal
  chapters with a hyphen in the URL (`chapter-55-5` = 55.5). `float()`
  raises, the except-branch assigns `sort_key = -1.0`, and the chapter
  sorts **before chapter 1** instead of between 55 and 56. It also
  keeps `number = "55-5"`, so artifacts land as `Chapter_55-5.cbz`.
  The library's `_norm_chapter_number` already treats `55.5` ⇄ `55-5`
  as equal, so Update matching is unaffected — this is an ordering and
  filename-cosmetics issue. The other Madara providers convert with
  `.replace("-", ".")`; toonily is the odd one out.

### 2026-05-28 — manga18fx.com provider (Madara-ish, plain HTTP)
- New `Manga18fxProvider` for `manga18fx.com`. Server-rendered HTML,
  HTTP 200 with no Cloudflare challenge, no auth, no FlareSolverr,
  no Playwright — default `get_session()` passes straight through.
  **Unrelated to `manhwa18.com` / `manhwa18.net`** despite the
  similar name (different operator + markup); each provider's
  `matches()` substring-checks its own exact domain so there's no
  routing conflict.
- **Madara-derived theme with two deviations from the stock wp-manga
  markup** (so the `mangadistrict`/`webtoonscan` regexes don't apply
  verbatim):
    1. **Chapter list is NOT `<li class="wp-manga-chapter">`.** Chapters
       are bare `<a class="chapter-name text-nowrap mycover"
       href="/manga/<slug>/chapter-N">` anchors, newest-first (183 for
       His Place). The two `id="btn-read-last"`/`btn-read-first` CTA
       buttons use a different class (`c-btn`) so the `chapter-name`
       anchor regex skips them — 185 raw `<a>` to chapter URLs but only
       183 real chapters.
    2. **Reader pages aren't scoped by `reading-content`** (that
       container is absent; the theme uses `page-break` wrappers).
       Pages are `<img class="loading pN" data-src="https://imgNN.
       manga18fx.com/uploads/<id>/<ch>/<page>-<key>.jpg">`. Rather than
       scope to a container, filter image URLs to those containing
       `/uploads/` — related-manga cards at the page bottom use
       `/webtoon/` and chrome uses `/images/`, so `/uploads/` isolates
       exactly the chapter pages (62 for ch 1, verified equal to the
       `class="loading"` count).
- **Standard Madara summary sidebar** otherwise: title from
  `<div class="post-title"><h1>` (og:title fallback strips the
  `Read … Manhwa - Manga18fx` boilerplate); cover via `og:image`;
  status + alternative names from `summary-heading`/`summary-content`
  blocks via a shared `_summary_block_re(heading)` helper. Status
  ("Ongoing") flows through the existing `normalize_status`. Alt names
  are slash/comma-separated (`남자의 자취방 / 他的 房间 / That Man's
  Epilepsy / …`) → split into `alt_titles[]`.
- **Decimal chapters** use a hyphen in the URL (`chapter-176-5`);
  `.replace("-", ".")` → `176.5`, same as the other Madara providers.
- **Chapter number format note for Update:** filenames will be
  `Chapter_176.5.cbz`; the library's `_norm_chapter_number` already
  treats `176.5` ⇄ `176-5` ⇄ `176_5` as equal, so on-disk truth
  matching works without extra handling.
- `Chapter.volume` carries the absolute reader URL (per the
  per-provider stash convention — toonily / manhwabuddy / manhwaread /
  comix / mangadistrict all do this) so `get_chapter_images` works
  after the GUI bridge's lossy chapter-dict serialisation.
- `is_nsfw=True` hard-coded (site is explicitly 18+).
- `image_referer = "https://manga18fx.com/"` set defensively; the CDN
  (`imgNN.manga18fx.com`) actually serves without a Referer (verified).
- **Verified live** end-to-end via the router: 183 chapters parsed,
  ch 1 → 62 images, first/last image fetch HTTP 200 `image/jpeg`.
  No diagnostic script added — nothing anti-bot to debug.

### 2026-05-20 — manhwa18.net provider (Inertia.js SPA)
- New `Manhwa18NetProvider` for `www.manhwa18.net`. Despite the
  similar name, this is a different site than `manhwa18.com` — it's
  a Laravel + Inertia.js SPA. The server returns the same minimal
  HTML shell on every page; the real payload (manga record + entire
  chapter list, or reader page's image list) lives inside a single
  attribute: `<div id="app" data-page="...">`. The value is
  HTML-entity-encoded JSON.
- **Two-fetch flow, both Inertia-shaped**:
    1. `GET /manga/<slug>` → ``props.manga`` (name, other_name,
       cover_url, pilot/synopsis, genres[], artists[],
       latest_chapter_id) + ``props.chapters[]`` (every chapter in a
       single response — 309 for Secret Class). Each chapter has
       ``id``, ``name``, ``slug``, ``order``.
    2. `GET /manga/<slug>/<chapter-slug>` → ``props.chapterContent``
       is an HTML string of ``<img src="..." loading="lazy"/>`` tags
       in reading order.
- **Chapter URL slugs vary by chapter age.** Recent chapters use
  ``chapter-N`` (e.g. ``chapter-306``); older imports keep a legacy
  format ``chap-NN-<numeric_id>`` (e.g. ``chap-01-361``). The provider
  uses each chapter's ``slug`` field verbatim, so both formats
  reach the reader.
- **Image CDN rotates by chapter age** (same legacy as `.com`):
    - Recent (~2024+) → ``min.manhwa18.net``
    - 2022-era       → ``cdn.pornwa.club``
    - 2021-era       → ``cdn.pornwa.us``
  Provider does NOT host-filter image URLs from `chapterContent` —
  that field only contains the chapter's real images (Inertia gives
  us a clean slice without site chrome), so any host filter would
  mis-drop old chapters. Verified live with chapters 1, 153, and
  306; all three CDNs return 200 with image/jpeg.
- **No Cloudflare / anti-bot in practice.** Default `get_session()`
  (curl_cffi chrome120 impersonation) passes through with a normal
  Referer header.
- **`is_nsfw=True` hard-coded** — site is explicitly 18+, and the
  per-manga ``is_adult_content`` flag isn't reliable (Secret Class
  returns 0 despite being adult).
- **`status` left as None.** Site exposes ``status_id`` as an integer
  with no documented mapping; manual status override via the library
  card covers the gap.
- **No conflict with `manhwa18.com` provider.** That provider's
  `matches()` substring-checks ``"manhwa18.com"``, so it will not
  claim a ``.net`` URL.
- `Chapter.volume` carries the absolute reader URL per the
  per-provider stash convention (toonily / manhwabuddy / manhwaread /
  comix all do the same), so `get_chapter_images` works after the GUI
  bridge's lossy chapter-dict serialisation.

### 2026-05-16 — Update reads iCloud filenames; library cache reload
- **UpdateProbeWorker rewritten to use on-disk filenames as truth.**
  The library's ``chapters`` dict is now advisory only. The worker
  reads ``download_path / folder`` (which for iCloud-imported
  entries is the iCloud subfolder), parses chapter numbers from the
  .cbz filenames, and uses that set as "what I have" for the diff.
  Fixes the long-standing bug where the library was a stale snapshot
  from import-time and any chapter the user manually moved into / out
  of iCloud was invisible to Update. New helpers
  ``_chapter_numbers_on_disk`` / ``_norm_chapter_number`` /
  ``_max_chapter`` live at module level in
  ``gui/bridge/library_bridge.py``.
- **Chapter-number format normalisation.** The same chapter shows up
  in three notations across providers and filesystems: dot
  (``62.5`` — comix / canonical), hyphen (``62-5`` — Madara URL
  slugs), and underscore (``62_5`` — some iCloud filenames where
  the user replaced ``.``/``-`` with ``_`` for legibility).
  ``_norm_chapter_number`` collapses all three to a single canonical
  form (and strips leading zeros), so ``Chapter_68_1.cbz`` in iCloud
  correctly matches ``chapter-68-1`` from toonily and doesn't get
  re-downloaded.
- **Cross-site fallback in Update.** When the primary site has
  nothing new for the on-disk set, the worker walks
  ``entry.alternative_sources[]`` (already sorted desc by
  chapter_count from the enricher). First alt whose recorded max
  exceeds on-disk max wins — its chapter list drives the diff and
  the download dispatch points at its provider/url. So if comix
  has chapter 35 but toonily (primary) only has 34, Update fetches
  from comix.
- **Empty / missing target folder → silent "no updates".** Library
  entries for series the user abandoned (no CBZs anywhere) stop
  triggering downloads. This is what caught the 154-chapter Bastard
  re-download.
- **LibraryManager: mtime-based reload.** The singleton used to load
  ``library.json`` once at startup and any subsequent ``_save()``
  blindly wrote the cached dict back. So if a script
  (``library_relocate_to_icloud.py`` etc.) edited the file while the
  GUI was open, the next GUI mutation reverted it. Fix:
  ``_reload_if_changed()`` is called at the top of every locked
  method; if the file's mtime advanced since our last load/save,
  reload first. Tolerance of 0.5s so our own writes don't look
  "external" on the very next call. Without this fix every script
  in this changelog round had a "ran twice because GUI clobbered
  it" story.

### 2026-05-15/16 — iCloud → Library pipeline (Phases 2 + 3 + cleanup)
- **Phase 2 (cross-site matcher) shipped.** ``scripts/icloud_match.py``
  walks inventory entries, runs fuzzy search across 12 providers
  (Madara AJAX, comix.to keyword API, gallery HTML), scores results
  with a custom containment-aware similarity, records every
  high/medium-confidence hit per entry. ``--unknowns-only`` mode for
  incremental runs. Cache at ``icloud_match_cache.json``.
- **Provider search adapters**:
  ``_aj_search_madara`` (toonily, mangadistrict — Madara
  ``/wp-admin/admin-ajax.php`` AJAX); HTML adapters for nhentai,
  hentairead, hentaifox, manhwaread, manhwabuddy;
  ``_api_search_comix`` (comix's ``/api/v1/manga?keyword=`` — note
  the parameter name; ``q``/``search``/``title`` all return the
  unfiltered catalogue). Manhwa18 / hentaifc / hitomi / mangafire
  search not implemented (no working endpoint, or Playwright-heavy).
- **``query_variants()``** generates 1-3 progressive search strings:
  primary (just cleanup) → modifier-stripped (drops "Uncensored",
  "TOP", "END", "Full Color", "Releasing") → first-3-words last
  resort. Used to find e.g. "From Pauper to Prince" when the iCloud
  folder is "From Pauper to Prince (Uncensored)".
- **Per-provider-best aggregator.** Searches return multiple
  similar-titled siblings on comix ("Chained Soldier" returns
  "Chained Soldier" + two unrelated "Soldier" entries). Original
  aggregator OR'd reported_status across ALL matches, so an unrelated
  sibling's "completed" would mis-tag the real ongoing series.
  Fixed: ``aggregate_status`` keeps only the TOP-scoring match per
  provider before checking statuses.
- **Phase 3 — ``icloud_to_library.py``** — imports each iCloud
  inventory entry into ``library.json`` keyed by the best match's
  URL. ``origin = "icloud_import"``, chapter numbers extracted from
  iCloud filenames (so Update has accurate on-disk state),
  ``download_path = ICLOUD_ROOT`` and ``folder = iCloud folder name``
  so "📂 Folder" opens the real files. Allowed providers: serial
  manhwa (toonily / mangadistrict / manhwaread / manhwabuddy /
  comix / webtoonscan / manhwa18 / mangafire) AND gallery (nhentai /
  hentairead / hentaifox / hentaifc / hitomi) — gallery imports
  carry ``is_nsfw = True``.
- **``enrich_alternatives.py``** — for each library entry, walks
  inventory matches and records non-primary high/medium matches as
  ``alternative_sources[] = [{provider, url, status, chapter_count,
  match_score, ...}]``. ``chapter_count`` comes from each provider's
  ``latest_chapter`` (cached). The GUI's LibraryCard renders these
  as the "Also on:" chip row, click → opens that URL in browser.
- **``library_dedupe.py``** — collapses pre-existing library entries
  whose title (or folder) fuzzy-matches an iCloud entry's title or
  folder. Uses both strict fuzz (alphanumerics only) and "loose"
  fuzz that drops TOP/END/Uncensored/Decensored/Raw/Hot/Complete
  suffixes. Also drops the single intra-import dup (manhwaread "The
  Mating of Elves" vs the comix one).
- **``library_relocate_to_icloud.py``** — for pre-existing entries
  that survived dedupe but have an iCloud counterpart, rewrites
  ``download_path``/``folder`` to point at iCloud and tags
  ``origin = "icloud_import"``. Drops entries with no iCloud
  counterpart (Strawberry Love, Please Put Them On, Bastard et al.).
  Collapses entries that now resolve to the same iCloud folder,
  keeping the richer alternative_sources list. After this, every
  library entry's truth folder is iCloud — Update never reads from
  ``./downloads/`` again.
- **``missing_chapters.py``** — dry-run Update All. Walks every
  library entry, probes primary + alternatives, lists chapters on
  any site that aren't in iCloud (format-normalised). Output:
  ``missing_chapters_report.md`` (gitignored). Run when you want to
  know what to manually pull into iCloud without committing to
  actual downloads.
- **``refresh_icloud.py``** — wrapper that runs inventory → match
  (``--unknowns-only``) → import → enrich in sequence. Idempotent;
  fast on no-op runs because cache covers everything.
- **GUI additions for the iCloud workflow**:
    - LibraryCard "Also on:" chip row with provider badges +
      chapter counts; click opens the URL.
    - "🔗 Website" button + a new ``LibraryBridge.openWebsite``
      slot that uses ``webbrowser.open()``.
    - Toolbar chips: "Hide completed" (existing) is now joined by
      "Only completed" (mutually exclusive) and "Hide hentai"
      (independent — filters by ``is_nsfw``).
    - Unset status pill renders as an amber "+ Set status" CTA
      instead of dim "? Status?".
- **Provider status extraction added for 5 more providers**:
  manhwaread (``data-status=`` attribute), manhwabuddy (h5+span),
  manhwa18 (info-item span — value carries the literal "On going"
  with a space), mangadistrict + webtoonscan (Madara summary block:
  ``<h5>Status</h5></div><div class="summary-content">…``).
  ``normalize_status`` now collapses whitespace + hyphens so
  ``OnGoing`` / ``On going`` / ``on-going`` all resolve to
  ``ongoing``; ``releasing`` (mangafire's term) added to the
  ongoing vocabulary.
- **The two remaining no-status providers** are mangafire (JS-rendered
  series page — would need Playwright DOM read) and toomics
  (paywalled). Manual ✋ "Mark as Completed" override covers them.

### 2026-05-15 — iCloud Manga inventory (Phase 1)
- New ``scripts/icloud_inventory.py`` — read-only walk of
  ``~/Library/Mobile Documents/com~apple~CloudDocs/Manga/`` that
  produces ``icloud_inventory.json`` + ``icloud_inventory.md`` at the
  project root. **Never** mutates the iCloud tree; the user carved
  it out as off-limits.
- Per-entry shape includes ``folder_name`` (raw), ``title``
  (END-stripped), ``marked_complete_by_user`` flag from the ``END``
  suffix convention, ``chapter_count`` (number of CBZ files / PDFs /
  image subfolders), ``format``, ``size_bytes``, plus empty
  ``matches`` and ``effective_status`` fields that Phase 2 will fill.
- Format detection partitions: ``per_chapter_cbz`` /
  ``per_volume_cbz`` / ``single_cbz`` (one-shot doujinshi) /
  ``numbered_cbz`` / ``image_folders`` / ``pdf`` / ``mixed`` /
  ``empty``. ``single_cbz`` was added in a follow-up after the
  initial run — pre-split, all 77 doujinshi landed in ``other_cbz``
  with no useful signal for Phase-2 routing.
- ``icloud_inventory.json`` + ``icloud_inventory.md`` are gitignored
  (private title list).
- **Phase 2** (cross-site status lookup) and **Phase 3** (library
  import) shipped later the same day. See the
  "2026-05-15/16 — iCloud → Library pipeline" entry above.

### 2026-05-15 — Check Status All + Open Website
- **New "Check Status" button** in the Library toolbar. Probes every
  entry's status via ``StatusCheckWorker`` — a new lightweight worker
  that ONLY calls ``provider.get_manga_info()`` to refresh
  ``status_auto`` and stamps ``mark_checked``. Crucially: it does NOT
  fetch chapter lists and never enters the download pipeline. Fixes
  the foot-gun the user hit with Update All — clicking the obvious
  refresh button shouldn't silently download chapters they didn't
  ask for.
- **Tooltips spell out the difference.** "Check Status" → "Does NOT
  download any chapters — safe to run any time." "Update All" →
  "Check every entry for new chapters AND download them. Use 'Check
  Status' instead if you only want to refresh badges." The buttons
  disable each other while one is in flight.
- **Bridge surface** mirrors Update All:
  ``checkStatusAll()`` / ``cancelCheckStatusAll()`` slots, signals
  ``statusCheckAllStarted(total)``,
  ``statusCheckAllProgress(done, total, url, title)``,
  ``statusCheckAllFinished(completed, ongoing, unknown, failed)``.
  State (``_status_urls`` / ``_status_idx`` / ``_status_stats``) is
  fully independent of the Update All state so concurrent runs are
  *possible* — but the QML gates them mutually exclusively to be
  polite to providers.
- **Shared banner.** The Update All / Check Status / Summary banner
  is one component that flips wording + colour based on which flow
  is running ("Updating N of M…" vs "Checking status N of M…").
  Saves a chunk of duplicated QML.
- **New "🔗 Website" button** on every Library card. Sits in a
  side-by-side row with "📂 Folder" so the card height doesn't
  grow. Calls ``LibraryBridge.openWebsite(source_url)`` which uses
  ``webbrowser.open()`` (cross-platform, respects the user's
  default browser). Tooltip shows the exact URL so it's clear what
  will open.

### 2026-05-15 — Status extraction for 5 more providers
- Added ``status`` parsing to **manhwaread**, **manhwabuddy**,
  **manhwa18**, **mangadistrict**, and **webtoonscan**. The audit two
  hours earlier said 7 providers don't expose status; this brings it
  down to 2 (mangafire + toomics). Coverage now: **12 of 14 providers
  auto-report status**, of which 6 also include "always complete"
  single-gallery sites (nhentai, hitomi, hentaifc, hentairead,
  hentaifox, comix.to).
- Markup patterns (each anchored on the ``Status`` label to survive
  unrelated DOM changes):
    - **manhwaread** — ``<span class="manga-status" data-status="X">``.
      Cleanest: read the attribute, not the i18n'd visible label.
    - **manhwabuddy** — ``<li><h5>Status</h5><span>X</span></li>``.
      Plain HTML; no class on the value span, so we anchor on the H5.
    - **manhwa18** — ``<span class="info-name">Status:</span>
      <span class="info-value"><a>X</a></span>``. Value is wrapped in
      an ``<a>`` linking to a filter URL; regex strips the wrapper.
      Site uses literal **"On going"** (with a space) for ongoing.
    - **mangadistrict** / **webtoonscan** — Madara theme:
      ``<div class="summary-heading"><h5>Status</h5></div>
      <div class="summary-content">X</div>``. Identical pattern, so
      the same regex works on both. Mangadistrict uses **"OnGoing"**
      (one word, mixed case).
- **Normalizer hardened.** ``normalize_status()`` now collapses
  internal whitespace + hyphens before matching, so "On going" /
  "On-going" / "on  going" / "OnGoing" all resolve to ``ongoing``.
  Added ``"releasing"`` (mangafire's term, for when we extract it
  there too) and ``"current"`` (some Madara variants) to the ongoing
  set. Verified live against all 4 patched sites — manhwa18's
  "On going", mangadistrict's "OnGoing", manhwabuddy's "Completed",
  manhwaread's ``data-status="completed"`` all map correctly.
- **What's left:**
    - **mangafire** doesn't render the series page in the initial
      HTTP response (the 27 KB body is just header chrome — the
      manga detail is mounted by JS). Would need to extract status
      from the Playwright-rendered DOM in ``mangafire_vrf.py``,
      which is a bigger change. Marked as follow-up.
    - **toomics** is paid-auth. Status is presumably visible on
      logged-in viewer pages, but parsing it requires the cookie
      path and isn't worth it until there's a use case beyond
      "skip Update All for finished series" — which is solved
      for toomics by the manual ✋ "Mark as Completed" override.
- **Unset-pill CTA polish.** When ``status == ""`` the badge now
  shows **"+ Set status"** in amber (the accent colour) instead of
  a dim grey "? Status?". The pill reads as a call-to-action; users
  can't miss it. The tooltip also points to Update as the primary
  way to fetch status, with manual marking as the fallback.

### 2026-05-15 — Library: completion status tracking
- **New per-entry status field**: ``status`` (one of ``completed`` /
  ``cancelled`` / ``hiatus`` / ``ongoing`` / ``""``), with companion
  fields ``status_auto`` (last provider-reported value) and
  ``status_manual`` (user override flag). Normalised through
  ``src/utils/library.py::normalize_status()`` from arbitrary
  provider strings (handles "Completed" / "complete" / "End" /
  "Publishing" / "Ongoing" / 完結 / etc., plus substring fallbacks).
- **Status pill on every LibraryCard.** Colour-coded badge with a
  ✓/●/⏸/✕/? glyph; click opens a popup menu to override
  (Completed / Ongoing / Hiatus / Cancelled / Use site status).
  A ✋ glyph appears when the user has set a manual override; the
  tooltip surfaces the site-reported value when it disagrees.
- **"Hide completed" toolbar toggle.** When on, completed and
  cancelled entries are filtered from the grid (client-side, like
  search/sort). Counter row shows "Showing N of M" when any filter
  is active.
- **Update All skips completed/cancelled entries automatically.**
  ``LibraryBridge.updateAll()`` partitions entries into a "to-probe"
  list and a "skipped" count before iterating. New signal arity:
  ``updateAllStarted(total, skipped)`` and
  ``updateAllFinished(with_updates, up_to_date, failed, skipped)``.
  The header summary spells out skipped count so it's not silent.
- **Auto status is re-synced on every probe.** ``mark_checked()``
  takes an optional ``manga_status`` kwarg; ``UpdateProbeWorker``
  passes ``manga.status`` so Ongoing → Completed transitions on the
  site land in the library on the next Update click.
- **Provider reality (per audit 2026-05-15):** 6 providers expose
  reliable status (the 5 single-gallery NSFW sites + comix), 1
  parses it (toonily — value strings vary; we normalise), and 7 do
  not expose it at all (mangafire, toomics, manhwaread, manhwabuddy,
  manhwa18, mangadistrict, webtoonscan). That's why the manual
  override exists — auto-tracking alone covers maybe half the
  catalogue. Adding status extraction to the Madara-themed sites
  (manhwabuddy/manhwaread/mangadistrict/webtoonscan) is plausible
  follow-up work; each parses the "Status" row from a sidebar that
  uses very similar markup.
- **Why "clear override" restores last-known auto, not ""**: the
  obvious naive behaviour (set ``status=""``, ``manual=False``)
  blanks the badge until the next probe re-syncs, which feels
  broken if you just clicked "Use site status". The setter now
  copies ``status_auto`` into ``status`` in that path.

### 2026-05-15 — Library tab: Update All, search, sort
- **Update All button** in the Library header. Probes every entry in
  sequence (one at a time — politeness, not laziness; Playwright
  providers can't safely run in parallel and rate-limited sites would
  earn IP cooldowns under 30+ concurrent probes). Each probe still
  funnels through ``LibraryBridge._on_probe_finished``, so per-card
  status messages and the download-dispatch path are unchanged — the
  bulk run is just a coordinator that emits header progress and tallies
  results. Downloads kicked off by individual probes run in parallel
  with subsequent probes via the existing multi-job DownloadBridge.
- Bridge signals: ``updateAllStarted(total)``,
  ``updateAllProgress(done, total, current_url, current_title)``,
  ``updateAllFinished(with_updates, up_to_date, failed)``. Slot
  ``updateAll()`` is a no-op if a bulk run is already in flight (second
  click won't restart). ``cancelUpdateAll()`` sets a flag checked
  between probes; the in-flight one always finishes (cancelling a
  running QThread mid-network-call is messier than waiting 30s).
- **Search field** in a new toolbar row. Case-insensitive substring
  match against ``title``, ``alt_titles[]``, and ``source``. Filter is
  client-side over the cached entries list — snappy, no bridge round
  trips on every keystroke.
- **Sort dropdown** with five modes, stored as stable keys not labels
  so renaming is cosmetic-only: ``last_downloaded`` (default — matches
  the existing newest-first behaviour), ``recently_added`` (by
  ``added_at`` desc), ``name`` (A→Z), ``chapter_count`` (largest
  libraries first), ``site`` (group by source, then by title). The old
  bridge-side ``listEntries()`` sort is left alone — QML re-sorts the
  master list locally via ``applyFilterAndSort()`` on filter/sort
  change.
- New view properties on ``LibraryView``: ``entries`` (master),
  ``visibleEntries`` (filtered+sorted view), ``filterText``,
  ``sortMode``, plus the bulk-progress state
  (``bulkBusy``/``bulkDone``/``bulkTotal``/``bulkCurrentTitle``/
  ``bulkSummary``). Two new empty states: library-actually-empty
  (existing) and filter-matches-nothing (new, with "Clear search"
  affordance).
- **What I deliberately didn't do:** per-row cancel for individual
  probes inside Update All. The in-flight probe can finish in seconds
  for most providers, and adding a per-worker cancel ``threading.Event``
  is a meaningful refactor of ``UpdateProbeWorker``. If the bulk run
  needs to die immediately, the cancel button stops queuing further
  entries — which is enough for the common case (47 entries, ~30s each
  = "I'll wait the current one out").

### 2026-05-11 — mangadistrict.com provider (Madara, plain HTTP)
- New `MangadistrictProvider` for `mangadistrict.com`. Standard
  Madara theme, but unlike webtoonscan it does NOT require
  FlareSolverr — Cloudflare lets `get_session()` (curl_cffi
  chrome120) through cleanly.
- URL pattern: `/series/<slug>/` for series, `/series/<slug>/chapter-N/`
  for reader.
- **Title regex gotcha:** the Madara theme on this site puts
  ``<span class="manga-title-badges">`` (Adult / Hot / etc. badges)
  between the opening ``<div class="post-title">`` and the ``<h1>``.
  Webtoonscan's tight ``<div class="post-title"...">\s*<h1>`` pattern
  doesn't match; allow ``.*?`` between them.
- **Reader uses eager ``src``** (not lazy ``data-src``) — both
  attributes are accepted by the regex for forward compatibility.
- **Site-chrome decoy:** Madara mounts an ``id="image-99999"``
  pointing at ``/assets/publication/media/…`` as a default banner.
  Filter it out by URL prefix (``/assets/publication/media/`` and
  ``/wp-content/`` covers all the non-page images).
- `og:title` includes a ``" - MANGA DISTRICT - Read Scan - Manhwa"``
  boilerplate suffix; strip it so library shows a clean title.
- `Chapter.volume` carries the absolute reader URL. NSFW flag taken
  from the ``adult-content`` body class.
- Verified live: 40 chapters parsed; first / middle / last all return
  HTTP 200 (1-1.4 MB JPEG) from ``cdn.mangadistrict.com``.

### 2026-05-11 — manhwa18.com provider (multi-chapter, rotating CDN)
- New `Manhwa18Provider` for `manhwa18.com`. Plain HTML, no JS, no
  AJAX. Cloudflare-fronted but the default `get_session()` passes
  fine — no FlareSolverr needed.
- URL pattern: `/manga/<slug>` for series, `/manga/<slug>/chap-N-<id>`
  for reader. Early chapters use a bare `/<num>` suffix instead of
  `chap-<num>-<id>`; the chapter-link regex accepts either.
- **Chapter list:** every entry is
  `<a href=".../chap-N-<id>" title="chap N">
  <li><div class="chapter-name">chap N</div>
  <div class="chapter-time">VIEWS - DATE</div></li></a>`. Same number
  can appear multiple times (different scanlation groups → different
  `<id>`). We surface every entry; the download bridge already dedups
  by number when no scanlator filter is set.
- **Title parse:** `<title>Manga X (group) - MyManga</title>` → `X (group)`.
  Strip the literal `"Manga "` prefix and `" - MyManga"` suffix.
- **Reader images:** `<img class="lazy" data-src="https://<cdn>/.../<id>.jpg">`.
  The CDN host **rotates per chapter age**:
    - Old chapters (~2021) → `cdn.manhwa18.com`
    - Mid-2022 chapters    → `cdn.pornwa.us` (with an occasional `//`
      typo in the path; we collapse repeated slashes in the path
      portion when reconstructing)
    - Recent (~2023+)      → `cdn.pornwa.club`
  So the host filter has to be loose — we accept any URL with the
  `lazy`-class + `data-src` markers. There are no decoy lazy-loaded
  chrome elements that would otherwise leak in.
- **Dead old URLs:** very old chapters on `cdn.manhwa18.com` 404 (the
  site purged the originals when migrating to pornwa CDNs). Not our
  bug — we faithfully extract whatever URL the site advertises; if
  the CDN doesn't have it, that's content-side rot.
- `Chapter.volume` carries the absolute reader URL (same convention
  as toonily / manhwabuddy / manhwaread / comix).
- `image_referer = "https://www.manhwa18.com/"` — the CDNs accept
  requests without referer in practice, but set defensively.
- `is_nsfw=True` baked in (site is explicitly 18+).

### 2026-05-11 — webtoonscan.com provider (FlareSolverr-required Madara site)
- New `WebtoonscanProvider` for `webtoonscan.com`. Standard Madara
  theme, but the site is fronted by **aggressive Cloudflare** that
  defeats every bypass approach we've used elsewhere:
    - `curl_cffi` chrome120/131/chrome_android/safari17/safari18/edge101
      all return HTTP 403 ("Just a moment…" JS challenge).
    - Playwright Chromium — headless AND visible, with
      `--disable-blink-features=AutomationControlled`,
      `navigator.webdriver` spoofing, locale/timezone/viewport set —
      sits on the challenge indefinitely without minting `cf_clearance`.
      CF fingerprints Playwright more aggressively than mangafire's
      deployment does.
    - WP-JSON works for stock routes but doesn't expose the manga /
      chapter custom post types, so there's no API-only path.
- **Solution: FlareSolverr.** Provider uses
  `get_session().get(url, force_flare=True)` for every HTML fetch.
  Our existing `SessionManager._solve_cloudflare()` does the round-trip:
  POST `/v1` with `cmd=request.get`, take the returned cookies +
  user-agent, install on the underlying session, replay the request.
- **User has to run FlareSolverr** the same way they already do for
  mangafire — any deployment works (binary release / Docker / npm),
  they all expose the same REST API on `http://localhost:8191/v1`.
  Default URL already in `config.json → flaresolverr_url`. If
  FlareSolverr is unreachable the provider's `_fetch_html` detects the
  CF challenge in the response body and raises with a clear "start
  FlareSolverr" hint.
- **Madara theme parsing** — standard WordPress wp-manga markup:
    - Title: `<div class="post-title"><h1>` (falls back to `og:title`)
    - Cover: `og:image`
    - Description: `og:description` → `meta[name=description]`
    - Chapters: `<li class="wp-manga-chapter"><a href=".../chapter-N/">`
    - Reader: `<img class="wp-manga-chapter-img"` with `data-src`
      (lazy-loader; falls back to `src`). Scoped to the
      `<div class="reading-content">` container so sidebar thumbnails /
      recommendation cards don't pollute the image list.
- **Image CDN** — unknown until first verified fetch; provider sets
  `image_referer = "https://webtoonscan.com/"` defensively. If the
  CDN turns out to NOT be CF-protected, image fetches use the normal
  rate-limited session (no FlareSolverr round-trip per image — would
  be intolerably slow).
- **Diagnostic** — `scripts/webtoonscan_test.py` walks every stage
  (FlareSolverr reachability → slug parse → manga info → chapter list
  → reader → image HEAD). First thing to run when the site breaks.
- **What we tried first that didn't work** (so we don't waste time
  retrying next site):
    - `src/utils/webtoonscan_capture.py` — Playwright-based CF cookie
      minter, mirror of `mangafire_vrf.get_cf_state`. **Deleted** —
      never minted `cf_clearance` even with stealth tweaks. The
      mangafire-style approach only works on CF deployments that DON'T
      fingerprint Playwright; webtoonscan does. If we ever need to
      bypass without FlareSolverr, the right tools are
      `nodriver`/`undetected-chromedriver` (CF-Turnstile-specific
      stealth libs), not vanilla Playwright.

### 2026-05-11 — manhwabuddy.com provider (multi-chapter, plain HTML)
- New `ManhwabuddyProvider` for `manhwabuddy.com`. Cleanest provider
  in the matrix to date: no JS execution, no AJAX, no obfuscation —
  the chapter list AND every image URL are embedded directly in the
  page HTML on first paint.
- URL pattern: `/manhwa/<slug>/` for series, `/manhwa/<slug>/chapter-N/`
  for the reader. The slug is the canonical code.
- **Series-page parse:**
    - **Title** — strip `Read X Manhwa ...` boilerplate from `<title>`.
    - **Cover** — `<meta property="og:image">`.
    - **Alt titles + description** — both packed into
      `<meta name="description">`. The site puts slash-separated alt
      names at the start (`"물이 넘쳐요/Super Wet/Dripping Wet. Oh, crazy..!!..."`);
      we split on the first `". "` after a run of `/`-delimited tokens.
    - **NSFW flag** — `<body class="mybody adult-content">` triggers
      `is_nsfw=True`.
    - **Chapter list** — `<li class="myfut"><a href="/manhwa/<slug>/
      chapter-N/" title="..."><span class="chapter-name">Chapter N</span>`,
      newest-first.  Page lists 105 chapters for the test series in a
      single fetch.
- **Reader-page parse:** every page is a `<img class="loading"
  data-src="https://imgNN.manhwabuddy.com/chapters/<manga_id>/<chap>/<page>-XYZ.jpg"
  src="...">`. We read `data-src` (lazy-load attribute; safer than
  `src` which can be blank on first paint), filter to anything with
  `/chapters/` in the path to skip site-chrome / "popular cards" /
  app banners.
- **Per-chapter URL suffix is randomised** (`-ee1` for chapter 1,
  `-ccb` for chapter 50, etc.) — looks like cache-busting. We don't
  reconstruct URLs, just scrape them, so the suffix is irrelevant.
- **Cloudflare-protected** but the default `get_session()` (curl_cffi
  chrome120 impersonation) passes through fine, same as toonily.
- `Chapter.volume` carries the absolute reader URL (same convention as
  toonily / manhwaread / comix) so the GUI bridge's lossy chapter-dict
  serialisation can re-fetch images after a fresh provider instance.
- `image_referer = "https://manhwabuddy.com/"` — the CDN
  (`imgNN.manhwabuddy.com`) checks referer on image requests.

### 2026-05-10 — Multi-job download UI
- **Each download is a "job".** ``DownloadBridge`` mints a unique
  ``job_id`` per ``startDownload`` call (timestamp + monotonic seq +
  safe-title slug) and tracks workers in ``self._workers: dict[str,
  DownloadWorker]`` instead of a single ``self._worker``. Workers
  self-evict via ``finished/error`` handlers so completed
  ``QThreads`` aren't kept alive by stale refs.
- **Bridge signals carry ``job_id`` first.** Every per-job signal
  (``chapterStarted``, ``chapterProgress``, ``chapterComplete``,
  ``overallProgress``, ``downloadFinished``) gained a leading
  ``job_id`` argument; new signal ``jobStarted(jobId, title,
  posterUrl, totalChapters)`` fires once per startDownload so the
  panel can create a card before any chapter starts. ``LibraryView``'s
  ``onDownloadFinished`` updated to match the new arity.
- **``ProgressPanel.qml`` is now a multi-job container.** The old
  per-job UI (header + overall bar + active chapter rows) was
  factored into ``JobProgressCard.qml`` (with a small cover-thumbnail
  + title header). The panel maintains a JS ``cardsByJobId`` map and
  exposes ``registerJob(...)`` + ``route*(...)`` slots that route
  signals to the right card. Cards stay visible after finishing
  until the user clicks "Clear Finished".
- **"Clear Finished" enables on ANY finished job** (not "all jobs
  finished"), so a completed download can be dismissed without
  waiting for parallel ones.
- **``downloadStarted`` no longer resets the panel** — that would
  clobber other in-flight downloads. It still switches the tab.
- **Cancel button is process-wide.** ``cancelDownload()`` calls
  ``cancel_downloads()`` (which sets the module-level
  ``threading.Event`` in ``src.core.downloader``) and terminates
  every worker. Per-job cancellation would require plumbing the
  cancel signal per-worker; deferred until there's UI demand.
- **Why no UI demand for per-job cancel yet:** there's no cancel
  button in any QML view today (the slot exists on the bridge but
  isn't wired). When that changes, a per-worker ``threading.Event``
  on ``DownloadWorker`` is the cleanest evolution.

### 2026-05-10 — comix.to v1 API + Playwright DOM-scrape fallback
- **Comix.to rebuilt as a SPA on `/api/v1`** with camelCase fields
  (`hid`, `latestChapter`, `originalLanguage`, `altTitles`, `synopsis`,
  `contentRating`, `poster.large`, …). Old `/api/v2` endpoints return
  404 across the board. `ComixAPI.get_manga_info` rewritten to call
  `/api/v1/manga/{hid}` and parse the new shape — works without any
  token.
- **Chapter list + per-chapter pages now require a path-signed `_=`
  token** AND **return encrypted JSON bodies** (`{"e": "<long blob>"}`)
  even when the token is valid. The signing keys (and presumably the
  cipher) live in a 248 KB VMProtect-virtualised JS chunk
  (`secure-tes1em-…js`), and the upstream HaruNeko maintainer
  acknowledged on issue #1683 that the site changes "every day" with
  "no ETA" and recommended using a different site.
- **Two-tier strategy:**
    1. **Fast path** — `src/utils/hash.py` rewritten to HaruNeko's
       latest port (new keys, new mutation table, round structure
       inverted: mutate-then-RC4 instead of RC4-then-mutate; the
       `body_size`/`time` parameters are now ignored — path alone is
       hashed). Verified against HaruNeko's TS output byte-for-byte.
       Currently rejected by the live server but kept in place so a
       single keys-array swap brings it back online when comix walks
       the cipher back.
    2. **Slow path** — new `src/utils/comix_capture.py`. Modeled on
       `mangafire_vrf.py`: dedicated worker thread owning a Chromium
       instance, queue-of-futures for cross-thread submissions.
       Doesn't try to decrypt — it just drives a real browser, lets
       the SPA decrypt client-side, and reads the rendered DOM.
- **Process-wide latch (`_FAST_PATH_BROKEN`):** the fast path either
  works site-wide or doesn't — there's no per-endpoint variation. So
  after the first encrypted body / token-rejection, we skip the fast
  path for the rest of the process. Stops the rate limiter from
  halving itself with a 403 storm on every per-chapter call.
  Re-flips on a fresh process; when comix walks the cipher back, the
  fast path is picked up automatically without code changes.
- **Chapter list scraping (`get_chapter_list`):** navigates to
  `/title/{hid}-{slug}`, scrapes `<ul class="mchap-list">
  <li class="mchap-item">…` rows. Each row's `<a class="mchap-row__primary"
  href=".../<id>-chapter-<n>">` gives id + number; the sibling
  `<a class="mchap-row__group">` gives scanlation group. Walks
  pagination by clicking the next-numbered `button.npager__num`
  (need `force=True` to bypass an `<a target="_blank">` ad anchor
  that intercepts pointer events; also remove `.rpage-hint`
  gestures-tutorial overlay first).
- **Per-chapter pages — URL reconstruction trick.** The reader is
  paginated single-page only (no long-strip mode in this build) and
  pre-mounts only ~3 images at a time, with the rest as
  `<div class="rpage-page__loader-inner">N / TOTAL</div>` placeholders.
  Scrolling does NOT trigger more loads, but we don't need it: one
  observed image URL `https://<host>/ii/<key>/NN.<ext>` plus the
  total page count from any placeholder is enough to reconstruct
  every page. Padding width is `max(observed_width, len(str(total)))`
  so a chapter with `01.webp` rendered for page 1 and 210 total
  pages correctly produces `001.webp … 210.webp` (verified live —
  HEAD returns 200 with `image/webp` body).
- **`Chapter.volume` carries the reader URL** for the Playwright
  fallback path (per CLAUDE.md "volume = per-provider stash field"
  convention used by toomics / mangafire / manhwaread / toonily).
  This means comix CBZ files now write the reader URL into the
  ComicInfo.xml `<Volume>` tag — same cosmetic regression those other
  providers already accepted.
- **`ComixProvider` caches slug per hid.** The slug is needed to
  build chapter reader URLs; we extract it during `extract_code` and
  again during `get_manga_info`, then read from cache in
  `get_chapters`. Bridge re-instantiates the provider for downloads
  and re-runs `extract_code(source_url)`, which restores the cache —
  same pattern as the toomics/mangafire providers.
- **Setup:** mangafire users already have Playwright installed; comix
  reuses the same Chromium. New users:
  ```
  pip install playwright
  python -m playwright install chromium
  ```
- **Diagnostic:** `python scripts/comix_test.py [<url>]` walks every
  pipeline stage (hid/slug parse → manga info → chapter list fast +
  slow → page list fast + slow → sample image HEAD) and prints what
  each saw. Run when the next site update breaks something.
- **References:** HaruNeko upstream connector
  (`manga-download/haruneko` → `web/src/engine/websites/ComixTo.ts`
  on master); open issue #1683 documents the current breakage and
  the maintainer's "use another website" advice.

### 2026-05-04 — GUI polish: URL field readability + dedupe Settings
- **URL field text was nearly invisible under Fusion.** The
  `UrlInput` `TextField` only set `color: textPrimary`. Qt's Fusion
  style (which `gui/main.py` forces via `QT_QUICK_CONTROLS_STYLE`)
  ignores that property and reads from the palette instead, so the
  URL rendered in Fusion's default near-black text on our dark
  card. Fix: set both `color` AND `palette.text` /
  `palette.placeholderText`, plus `palette.highlight`,
  `palette.highlightedText`, `selectionColor`, `selectedTextColor`
  so a mouse-drag selection stays readable too. Bumped the URL
  text to `Font.Medium` while we were in there. Same fix would
  apply to any future `TextField` in this app — Fusion's text
  rendering always needs the palette overrides.
- **Removed the duplicate Settings button** in `DownloadControls.qml`
  (the gear-icon pill that sat next to "Scanlator Preference").
  The left-sidebar Settings button is the single entry point now.
  Also removed the bridging `settingsClicked` signal on
  `DownloadControls` and the `onSettingsClicked` handler in
  `BrowseView.qml`. SideBar's `settingsClicked` signal is unaffected.

### 2026-05-04 — manhwaread.com provider (multi-chapter, mangomic theme)
- New `ManhwareadProvider` for `manhwaread.com`. URL pattern is
  `/manhwa/<slug>/`; the slug is the canonical code (numeric
  `manga_id` is parsed off the page from the bookmark button's
  `data-manga-id` but isn't in any user-visible URL).
- **Same WordPress "mangomic" theme as hentairead.com**, just
  configured for serial chapters instead of single galleries.
  Series-page DOM is identical (same `.manga-titles`, same
  `<a rel="tag">` metadata grid), but the chapter list lives in a
  different element (`<a class="chapter-item" href=".../chapter-NN/"
  data-id="<chapter_id>">`) and the reader page uses a base64-encoded
  `chapterData` blob instead of preview thumbs.
- **Image URL pipeline (per chapter):**
    1. Fetch the reader page.
    2. Extract `var chapterData = {"data":"<b64>","base":"https://manread.xyz/<manga_id>"};`.
    3. Base64-decode `data` → list of
       `{"src":"<chapter_id>/mr_NNN.jpg","w":...,"h":...}`.
    4. Image URLs = `<base>/<src>`. Verified live (first / middle /
       last page on `close-as-neighbors-uncensored` chapter 1, all
       return real bytes).
- **Two parsing gotchas worth flagging:**
    - **Chapter URLs sometimes have suffix slugs**
      (`/chapter-52-the-end/`). The number regex is anchored to
      `chapter-(\d+(?:\.\d+)?)` so the suffix is ignored — without
      this, "52-the-end" sorted as non-numeric and ended up at
      position 0 of the chapter list.
    - **The base64 blob is emitted unpadded**, but Python's
      `base64.b64decode` is strict by default. Pad with
      `b64 += "=" * (-len(b64) % 4)` before decoding.
- `Chapter.volume` carries the absolute reader URL (same pattern as
  toonily) so `get_chapter_images` works after the GUI bridge's
  lossy chapter-dict serialisation.
- `image_referer = "https://manhwaread.com/"` — set defensively;
  manread.xyz doesn't strictly require it today but the other
  mangomic-themed sites do.
- No CF challenge in practice — plain `get_session()` works.

### 2026-05-04 — toonily.com provider (multi-chapter manhwa)
- New `ToonilyProvider` for `toonily.com`. Accepts both URL forms:
    - `https://toonily.com/serie/<slug>/`        — series page
    - `https://toonily.com/serie/<slug>/chapter-N/` — reader page
  `extract_code` pulls the slug out of either via `/serie/<slug>` regex.
- **Multi-chapter** unlike most of the recent additions (nhentai /
  hitomi / hentaifc / hentairead / hentaifox are all single-gallery).
  One HTTP call to the series page returns the chapter list (35
  chapters in the test `cctv-91d81bf9` series), each as a
  `<li class="wp-manga-chapter"><a href="/serie/<slug>/chapter-N/">`.
  Image URLs are fetched per-chapter at download time (same lazy
  pattern as comix.to / mangafire.to).
- **`Chapter.volume` carries the absolute reader URL.** Avoids the
  bridge having to reconstruct it from slug+number, and survives the
  GUI's lossy chapter-dict serialization untouched.
- Image extraction is straightforward HTML — `<img id="image-N"
  src="https://data.tnlycdn.com/chapters/.../NN.jpg">` inside
  `<div class="page-break no-gaps">`. Sorted by the integer index in
  `image-N` to be safe against minor reordering. The `image-999`
  Discord-server decoration is filtered by checking for
  `/wp-content/` in the src.
- Metadata harvest: title from `<div class="post-title"><h1>`, cover
  from `og:image`, description from `og:description`, tags from
  `<a href="/tag/X/">#X</a>`, plus structured `<div
  class="post-content_item"><div class="summary-heading"><h5>FIELD</h5>
  </div><div class="summary-content">...` blocks for Alt Name, Writer,
  Artist, Genre, Status. Values literally equal to "Updating" are
  treated as missing (toonily's placeholder for unset fields).
- **Cloudflare**: toonily fronts everything with CF, but the project's
  shared `get_session()` (curl_cffi Chrome 120 impersonation) sails
  through. No Playwright / FlareSolverr needed at the time of writing.
  If that breaks, the fix is the same as mangafire (drop a Playwright
  shim in front).
- **Image CDN referer**: `data.tnlycdn.com` returns 403 without
  `Referer: https://toonily.com/`. `image_referer` handles that —
  the chapter downloader passes it through `headers={}` on every
  image request, same as the other providers.
- Verified live with `cctv-91d81bf9`: 35 chapters parsed, chapter 1
  yields 16 images, first / middle / last image URLs all return real
  bytes (521 KB / 531 KB / 728 KB).

### 2026-05-04 — hentaifox.com provider
- New `HentaifoxProvider` for `hentaifox.com`. URL pattern is
  `/gallery/<id>/`; numeric id is the canonical code (also surfaces in
  reader URLs as `/g/<id>/<page>/`).
- **Two HTTP calls per gallery**, each with a different role:
    1. **`/gallery/<id>/`** — title (`<div class="info"><h1>`),
       cover (`<div class="cover"><img src>`), page count
       (`<span class="i_text pages">Pages: N`), and three hidden
       form inputs (`load_id`, `load_dir`, plus the gallery title)
       used to construct image URLs. Tag-style metadata is bucketed
       by the `<ul class="<bucket>">` it lives under
       (`tags/parodies/characters/groups/categories/languages` →
       tags, `artists` → artists). **Critical:** scope the link
       sweep to those ULs only — the related-gallery cards lower
       on the page emit duplicate category labels (e.g. ten copies
       of "Doujinshi") that would otherwise pollute every entry's
       tags.
    2. **`/g/<id>/1/`** — the reader. Contains
       `var g_th = $.parseJSON('{"1":"w,1280,1790", ...}')` whose
       value's first letter is the per-page extension (`j`=jpg,
       `p`=png, `g`=gif, `w`=webp — same convention nhentai uses).
       We only need the first reader page because g_th lists every
       page in the gallery.
- **Image URL formula** (verified live with first / middle / last
  page on gallery 162323):
  `https://<host>/<load_dir>/<load_id>/<N>.<ext>` — host comes from
  any thumbnail (e.g. `i3.hentaifox.com`; hentaifox shards across
  i / i2 / i3 per-gallery). When `g_th` parsing fails, default
  every page to `webp` and rely on the image downloader's
  extension fallback (webp/jpg/png/gif).
- Single-chapter gallery shape (same as nhentai / hitomi / hentaifc /
  hentairead). `Chapter.volume` carries the gallery id so
  `get_chapter_images` can re-derive everything from disk-only state
  if needed.
- `image_referer = "https://hentaifox.com/"`.
- Why parse the `g_th` JSON instead of synthesizing a `.webp` for
  every page? Some galleries are genuinely mixed-extension; the JSON
  is authoritative and only costs one extra HTTP call. Per-image
  fallback would still work but would burn one wasted GET per
  non-webp page on those galleries.

### 2026-05-04 — Show supported sites + live URL validation
- New `Provider.example_url` class attribute (defaults to `""`). Each
  concrete provider sets it to a placeholder-style example
  (`https://hentairead.com/hentai/<slug>/` etc.). Used purely as a
  hint in the GUI; the router still uses `matches()` for actual
  dispatch.
- `MangaBridge` gains two QML-callable slots:
    - `supportedSites()` — returns
      `[{name, label, domains, example_url, auth_required}, ...]`
      derived from the provider registry. `auth_required` is currently
      hard-coded to true only for toomics; if more paywalled providers
      land, lift this onto a `Provider` class attribute.
    - `classifyUrl(url)` — synchronous, no network. Returns the
      matching provider name or `""`. Powers the input field's live
      ✓ / ✗ indicator.
- `UrlInput.qml` redesigned: input row + a `Flow` of site chips
  underneath. Each chip shows the domain (lock icon for paywalled
  sites) and a tooltip with the example URL. The chip whose provider
  matches the current input lights green. Fetch button greys out
  until the URL is recognised — no more "you typed an unsupported
  URL, hope you guess correctly which sites work."
- Browse view bumped from 56 px to 92 px to fit the chip row.
- **Why surface the list everywhere instead of in Settings only?**
  The user is most likely to need the answer at the moment they're
  about to paste — putting it inline removes a tab-switch and
  prevents the "I'll just try it and see" failure mode that wastes a
  fetch round-trip and shows a confusing error.

### 2026-05-04 — Library tab + persistent download registry
- New `src/utils/library.py` — `LibraryManager` singleton that keeps
  `library.json` (gitignored) at project root. Records every manga
  we've downloaded keyed by normalized `source_url`, plus a
  per-chapter dict (`{number: {title, downloaded_at}}`) so the
  GUI's "Update" flow is a trivial set-difference against the live
  chapter list. URL normalization (lowercase host, trailing-slash
  strip) prevents the same gallery from ending up as two entries.
- **Recorded from both front-ends.** `DownloadWorker.run` (GUI) calls
  `upsert_manga` before any chapter starts so the entry exists even
  if every chapter fails; `_download_single_chapter` calls
  `record_chapter` after each success. `MangaDownloader.download_chapters`
  (CLI) does the same. All library calls are wrapped in try/except —
  a library failure must never break a download.
- New GUI bridge `gui/bridge/library_bridge.py` exposing three QML
  slots:
    - `listEntries()` — newest-first list of entries (with a
      `chapter_count` annotation).
    - `updateEntry(url)` — runs an `UpdateProbeWorker` (QThread)
      that re-fetches manga + chapters via the provider router,
      computes `set(remote_numbers) - set(known_numbers)`, and hands
      the new chapters to `DownloadBridge.startDownload(...)` (reusing
      the user's original `output_format`). Emits one of three
      signals: `updateStarted(url, title, count)`,
      `noUpdatesAvailable(url, title)`, `updateFailed(url, error)`.
    - `removeEntry(url)` — drops the entry; does NOT touch on-disk
      artifacts.
    - `openFolder(url)` — reveals the manga folder in Finder /
      Explorer / `xdg-open`.
- New QML: `gui/qml/views/LibraryView.qml` + `LibraryCard.qml`. Nav
  button added to `SideBar.qml` (📚 Library). The view auto-refreshes
  on `DownloadBridge.downloadFinished` so a brand-new download lands
  immediately, and on `LibraryBridge.entriesChanged`.
- Cross-bridge wiring lives in `gui/main.py` —
  `library_bridge.attach_download_bridge(download_bridge)` so QML
  doesn't need to know that "Update" eventually triggers a download.
- **Why no artifact verification at update time?** If the user
  renamed a parent folder or deleted a single CBZ manually, treating
  that as "not downloaded" would re-pull every chapter. The library
  is the source of truth; "Remove + re-download" is the recovery
  path. Same trade-off as `_failed.txt`: simple, predictable, no
  accidental work.
- `library.json` is **gitignored** alongside `secrets.json` — it
  contains URLs of NSFW galleries the user has downloaded.

### 2026-05-04 — hentairead.com provider
- New `HentaireadProvider` for `hentairead.com`. URL pattern is
  `/hentai/<slug>/`; we use the slug as the canonical code (the
  numeric `#NNNNNN` id is parsed off the page but never appears in
  user-visible URLs).
- **Single HTTP call per gallery.** The gallery page already contains
  every per-page preview thumb as
  `<img src="https://hencover.xyz/preview/<gid>/<cid>/hr_NNNN.jpg">`
  inside `<li class="chapter-image-item" data-page="N">`. We parse all
  of them, sort by `data-page`, and produce the full-resolution URL
  by swapping host + dropping the `preview/` segment:
  `https://henread.xyz/<gid>/<cid>/hr_NNNN.jpg`. Verified with
  spot-checks (first / middle / last page) against the live CDN.
- Title comes from `<h1>` inside `div.manga-titles`; alt titles from
  the immediately-following `<h2>` (multi-language alts are
  pipe-delimited, e.g.
  `Adventurer-chan and her Lewd Adventure Vol. 1 | 冒険者ちゃんとえっちな冒険1`).
  Cover URL via `<meta property="og:image">`. Tags / artists /
  parodies harvested from `<a href=".../tag|artist|parody/...">` rel
  links. Numeric gallery id from `data-clipboard-text="#NNNNNN"`.
- Single-chapter gallery shape (same as nhentai / hitomi / hentaifc):
  one `Chapter` with all `image_urls` pre-attached, so the chapter
  selector skips itself. `Chapter.volume` carries the slug so
  `get_chapter_images` can re-fetch the gallery page if it ever needs
  to (the GUI bridge's lossy chapter-dict serialization preserves
  `volume`).
- `image_referer = "https://hentairead.com/"` — full images on
  `henread.xyz` 403 without it.
- **Why preview→full host swap rather than a synthesized
  `hr_NNNN.jpg` loop?** The gallery page is the source of truth for
  page count and per-page extension. If a future gallery uses a
  different naming convention or a sparse range, we still get the
  right URLs because we parse them out of the rendered HTML — the
  transform is purely host-level.
- No JS execution, no anti-bot challenge, no auth — fastest provider
  in the matrix after comix.

### 2026-05-04 — mangafire stabilisation + GUI polish
This collects everything that landed after the initial mangafire MVP.
Treat as one unit; individually they're a death-by-1000-cuts.

- **Dedicated Playwright thread.** Initial implementation called
  `sync_playwright().start()` from Qt's `ThreadPoolExecutor` worker
  threads → `RuntimeError: There is no current event loop in thread`.
  Refactored `MangafireVRFGenerator` so a single `mangafire-playwright`
  thread owns Chromium; everyone else submits work via a `queue.Queue`
  + `concurrent.futures.Future`. Side benefit: Playwright operations
  serialise naturally (matches AIO-Webtoon-Downloader's CLI model).
- **`RLock` instead of `Lock`.** Playwright drains queued `request`
  events between sync calls; `_on_request` fires re-entrantly on the
  same thread that already holds the lock. Non-reentrant lock
  deadlocked instantly after the first navigate.
- **Public chapter-list endpoint.** Switched `get_chapters` to
  `/ajax/manga/<hid>/chapter/<lang>` (no VRF, no extra Playwright
  navigation) — chapter list now appears as soon as CF cookies are
  loaded. Per-chapter id is recovered at download time by snooping
  `/ajax/read/chapter/<id>?vrf=…` via the new
  `capture_ajax_url(regex, navigate_to=...)` helper, so we get id +
  vrf from a single navigation.
- **30 s capture timeout + 3-attempt retry with backoff.** 15 s
  timed out on ~30 % of chapters when CF was throttling; 30 s
  catches the slow tail and retries handle the burst-failure pattern.
  Capture failures don't earn 1015s because they're navigation
  timeouts, not body-status 403s.
- **Per-chapter cookie refresh.** After every `capture_ajax_url`,
  pull live cookies from the Playwright context (`get_cf_state(force=True)`)
  and pass them as the `cookies=` kwarg to the AJAX `requests.get` —
  per-request rather than mutating the shared session, so concurrent
  download workers don't race on `cookies.clear()` / `cookies.set()`.
- **`/read/manga.<hid>/<lang>/chapter-1` for warm-up nav.** A reader
  page fires the chapter-list AJAX automatically; the manga info page
  often doesn't in headless mode. AIO uses the literal `manga.`
  placeholder in the slug position because the trailing `<hid>` is all
  the server cares about. We do the same.
- **Removed mangafire settings UI.** With Playwright handling cookies
  and vrf automatically, the manual cookie textarea was vestigial.
  Removed from `SettingsDrawer.qml` and `SettingsBridge`. The
  fallback-cookie code path in the provider stays — manual edit of
  `secrets.json["mangafire"].cookie` still works as an emergency
  escape hatch if Playwright ever breaks.

#### GUI: chapter visibility during slow capture
- New `chapterStarted(name)` signal on `DownloadWorker` + `DownloadBridge`,
  emitted the moment a worker picks up a chapter (before VRF capture,
  before any HTTP). `ProgressPanel.qml` registers a `Preparing…` row
  with a thin grey sliver bar so the user sees what's being processed
  during the 10-30 s VRF window. Status flips to `Downloading` →
  `Complete`/`Failed` as real progress / completion arrives.

#### Per-run failure log
- `src/core/failure_log.py`: `FailureLog(manga, config)` collects
  failures during a session; `.write()` at the end writes
  `<download>/<safe_title>/_failed.txt` (or removes a stale one on a
  clean run). Tab-separated `number\ttitle\treason`. Wired into both
  `MangaDownloader.download_chapters` (CLI) and `DownloadWorker.run`
  (GUI). Re-running the same selection skips successes via existing
  on-disk resume logic, so the natural recovery pattern is "select
  all → Download again."

#### Logging fix
- `gui/main.py` now imports `setup_logging` and calls it with
  `enable_logs` from config. Previously the GUI never wired the
  logger, so `logger.info`/`warning`/`debug` calls in providers were
  silently swallowed even with the toggle on. CLI was already correct
  (`src/cli/app.py`). Diagnostic-only `print(..., flush=True)` calls
  remain in mangafire / mangafire_vrf for unconditional visibility.

### 2026-05-03 — mangafire.to provider (English chapters only)
- New `MangafireProvider` for `mangafire.to`. URL pattern is
  `/manga/<slug>.<hid>` — we cache both the slug (e.g.
  `youkai-izakaya-nonberekee.l3k53`) and the trailing hid (`l3k53`).
- Three-call flow:
    1. `GET /manga/<slug>` (HTML) → title, cover, synopsis, body
       `data-hid` confirmation.
    2. `GET /ajax/read/<hid>/chapter/en?vrf=<token>` (JSON wrapping HTML)
       → chapter list. Each `<a>` has `data-number` and `data-id`.
    3. `GET /ajax/read/chapter/<chapter_id>?vrf=<token>` (JSON) →
       `result.images` is a list of `[url, …]` entries; `entry[0]` is
       the URL.
- **Anti-bot bypass — TWO things needed**:
    1. **Cloudflare cookies** (`cf_clearance`, `__cf_bm`) — minted by
       a real Chromium browser passing the CF challenge. Without them,
       all mangafire AJAX returns the CF block page regardless of vrf.
       `src/utils/mangafire_vrf.py` launches headless Chromium once
       per session, navigates to `mangafire.to`, lets CF run, then
       extracts the live cookies + the navigator.userAgent. We attach
       both to a private `requests.Session` on the provider. Cached
       for 25 min (cf_clearance lasts ~30).
    2. **VRF token** — both AJAX endpoints reject requests without a
       per-path `vrf=` query param computed by obfuscated client-side
       JS. We snoop the value by listening for any outbound request
       containing `vrf=` in the same Chromium tab, keyed by URL path.
       Tokens cached in-memory for 5 min.
- One shared Chromium instance handles both — single process, single
  cost. Inspired by `zzyil/AIO-Webtoon-Downloader` which uses
  `zendriver` for the CF step + Playwright for the VRF step; we use
  Playwright for both since it's already installed for VRF.
- **Setup (mangafire only)**:
    ```
    pip install playwright
    python -m playwright install chromium
    ```
    Without Playwright the provider falls back to a bare AJAX call,
    which only works if the user has manually pasted a fresh
    `cf_clearance` cookie via Settings → MANGAFIRE COOKIE.
- `_LANG = "en"` is hard-pinned per user request.
- `Chapter.volume` carries the alphanumeric `chapter_id` (since
  `Chapter.chapter_id` is typed as int in the model). Bridge already
  preserves `volume` end-to-end.
- **No retry on body-status 403**: mangafire's anti-bot 403 isn't
  transient; retrying earns a Cloudflare 1015 IP rate-limit. The
  provider fails fast with a clear remediation message.
- API + vrf approach learned from inspecting open-source scrapers
  (read-only, no code copied):
    - https://github.com/shafat-96/mangafire (Node/TS) — endpoint shape
    - https://github.com/artur-oliveira/manga-fire-scraper (Python) — same
    - https://github.com/zzyil/AIO-Webtoon-Downloader (Python) — Playwright
      vrf-capture pattern

### 2026-05-02 — toomics.com provider (auth-gated, cookie-paste)
- New `ToomicsProvider` for `global.toomics.com`. Toomics is a paid
  webtoon platform: every viewer page only renders comic image URLs
  for an authenticated paying member, so the provider reads a session
  cookie + matching User-Agent from a new `secrets.json` file at
  project root and attaches them to every request.
- `secrets.json` is gitignored (mode 600). Loader lives in
  `src/utils/secrets.py`; providers look themselves up by name via
  `get_provider_secrets("toomics")`.
- Listing parser (`_iter_accessible_episodes`) filters by the
  visible tier *label* on each episode, not by onclick or
  `cointypeNN`. Two surprising findings drove this:
    1. Toomics emits `Base.popupForStat('modal-login', ...)` even on
       VIP episodes a logged-in member can read — onclick is unreliable.
    2. The `cointype05` CSS class is **overloaded** — both `VIP ONLY`
       and `N COINS` entries use it. Only the visible label
       (`"FREE" / "VIP ONLY" / "N COINS"`) actually distinguishes
       member-included content from per-episode purchases.
  We accept only `FREE` and `VIP ONLY`. Anything containing `"COIN"`
  is per-episode-purchase content; we never attempt it, even for VIP
  members, because Coin episodes are sold separately from the
  membership and the viewer page would bounce. The episode URL is
  extracted from either `location.href='…'` (FREE) or the third
  argument of `Base.popupForStat('modal-login','login','…',…)` (VIP).
- Image URLs are pulled from the viewer page in document order
  (regex over `https?://toon-g\d+\.toomics\.com/toon-[^\s"'<>]+`).
  These URLs are pre-signed with a `?time=...&code=...&tri=...` TTL
  (~24h), so `get_chapters` returns chapters with empty
  `image_urls`; `get_chapter_images` re-fetches the viewer page at
  download time. Don't cache them across runs.
- The `volume` field on each `Chapter` carries the toon id so
  `get_chapter_images` can rebuild `/code/{c}/ep/{n}/toon/{toon}` even
  after the GUI's lossy chapter-dict serialization (which drops most
  fields). The provider also keeps `_toon_id` as a fallback.
- A `ToomicsAuthError` is raised with a clear remediation message
  when the viewer page comes back without the `id="toon_idx"` hidden
  input — that's the canonical "session expired / IP changed / UA
  mismatch" signal.
- **Cookie-binding caveats (read these — the cookie format itself
  encodes them):**
  - Toomics binds the session to your *IP address*. Running the
    downloader from a different network than your browser invalidates
    the session.
  - Toomics binds the session to your *User-Agent* string. Always
    paste the UA from the same browser the cookie came from
    (`secrets.json` → `toomics.user_agent`).
  - These are the server's choices, not ours; we just send what
    matches.
- **Setup (preferred path — credential login):**
  1. Open the GUI, click ⚙️ Settings → scroll to TOOMICS LOGIN.
  2. Enter your email + password → click 🔐 **Login**.
     `src/utils/toomics_login.py` POSTs `/en/auth/layer_login` with
     `user_id` + `user_pw` + `keep_login=Y`, then GETs `/en` to let
     toomics finalise the session cookie. Resulting cookies +
     credentials + UA all land in `secrets.json` (mode 0600).
  3. Click **Test** to confirm: a green "saw 52 accessible episodes"
     means good. The next time the cookie expires (toomics typically
     rotates it daily) hit Login again — credentials stay stored, no
     re-typing.
- **Fallback (manual cookie paste):** if toomics ever wraps the login
  form in a captcha or MFA, the credential flow throws
  `ToomicsLoginError` and you paste a fresh cookie from DevTools →
  Network → click the document request → copy the `cookie:` header
  value into the cookie textarea below the credential fields.
- Why credential storage on disk is acceptable here: this is a
  single-user personal-use tool; the user explicitly chose this
  trade-off. Threat model is "if my laptop is owned, I have bigger
  problems than my toomics password." If the cost-benefit ever
  changes, the same `secrets.json` shape can be backed by macOS
  Keychain / Secret Service via the `keyring` library.

### 2026-05-02 — hentaifc.com provider
- New `HentaiFCProvider` fetches two pages: the gallery landing
  (`/e/{id}`) for title / alt name / page count / cover / artists /
  parodies / tags, and the reader (`/e/{id}/c0`) for the image URLs.
- Image URLs on hentaifc are obfuscated: the reader page emits a
  `var X = ['104 116 116 …', …];` array of space-separated decimal
  char-codes that JS decodes via `String.fromCharCode`. Variable name
  rotates per request, so we scan every `var X = [...]` array in the
  page and accept the first one whose first entry decodes to an
  absolute URL.
- A "gallery" maps to a single chapter with all pages pre-attached
  (same shape as nhentai / hitomi); the chapter selector skips itself.
- Image referer is `https://hentaifc.com/`.
- Why: thumbnails on the landing page are ~21KB and only 400px tall;
  the actual full-resolution images (1080px+) are reachable only via
  the encoded reader array, so we have to mimic the reader's decode.

### 2026-05-01 — hitomi.la provider
- New `HitomiProvider` reads gallery info from
  `ltn.gold-usergeneratedcontent.net/galleries/{id}.js` (a JS payload
  prefixed with `var galleryinfo =`) and parses `gg.js` for the
  per-deploy routing values (`gg.b`, the integer whitelist used by
  `gg.m`).
- Image URL is computed as
  `https://{a|w}{1|2}.gold-usergeneratedcontent.net/{gg.b}{gg.s(hash)}/{hash}.{avif|webp}`.
  Letter is `a` for AVIF and `w` for WEBP; suffix is `2` when `gg.m`
  whitelists the hash, `1` otherwise. `gg.s(hash)` rearranges the last
  3 hex chars and parses them as a hex int → decimal string.
- A "gallery" maps to a single chapter with all pages pre-attached, so
  the chapter selector skips itself (same shape as nhentai).
- Image referer is `https://hitomi.la/`.
- Why: hitomi serves images from a CDN whose subdomain depends on the
  hash (and changes per deploy via `gg.b`), so URLs have to be
  reconstructed in-process from the same JS hitomi's reader runs.

### 2026-04-29 — Resume + skip already-downloaded
- `ChapterDownloader._is_chapter_complete()` skips a chapter wholesale
  when its artifact (CBZ with N entries / non-empty PDF / full image
  folder) is already present.
- `_scan_existing_pages()` finds `NNN.ext` files on disk and the
  downloader fetches only the missing indices when resuming an
  interrupted IMAGES or `keep_images=true` run.
- `download_indexed_images()` reports progress relative to total
  chapter pages, not the subset being fetched, so the GUI bar stays
  accurate during resumes.
- Why: closing the app or having the IP throttled mid-job no longer
  costs the previous progress.

### 2026-04-29 — Use inline gallery JSON for nhentai pages
- `NhentaiProvider._extract_gallery_json()` parses
  `window._gallery = JSON.parse("…")` (and bare-object / loose
  variants). Per-page extensions come from `images.pages[].t` codes
  (`j/p/w/g`). Thumbnail scraping stays as a fallback.
- Image downloader rewritten to fail fast on universal 404 and only
  retry-with-backoff on transient errors. Saves ~14s per missing
  image.
- Why: nhentai galleries lazy-load thumbnails, so the previous parser
  only learned extensions for the first few pages and defaulted the
  rest to `.webp` → most pages 404'd on a 929-page gallery.

### 2026-04-29 — Single config.json (fix duplicate-config drift)
- `ConfigManager` anchors `config.json` to the project root regardless
  of CWD. `gui/config.json` deleted.
- Why: the GUI was reading/writing a different config than the CLI
  depending on launch directory, which made `keep_images` (and other
  settings) appear broken.

### 2026-04-29 — curl_cffi + adaptive rate limiter (no more FlareSolverr-by-default)
- `SessionManager` rewritten to use `curl_cffi` (Chrome 120
  impersonation) as the primary HTTP client. Real TLS / HTTP-2 /
  `Sec-Ch-Ua` fingerprints in-process — defeats most Cloudflare
  fingerprint blocks without an external service.
- Per-host adaptive rate limiter (token bucket, MD on 429/403,
  gradual recovery on streaks of success) so steady downloading
  doesn't trip per-IP throttles.
- FlareSolverr kept as a fallback for hard JS challenges, but logs
  quietly at info-level when not running.
- Added `verify_ssl` knob for users with broken local CA stores.
- Why: user was running FlareSolverr separately and using a VPN to
  avoid IP blocks. Both are now usually unnecessary.

### 2026-04-29 — Multi-site provider abstraction + nhentai.to
- New `src/providers/` package with `Provider` ABC, URL-based router,
  and providers for `comix.to` (wraps existing API) and `nhentai.to`
  (HTML scraper).
- `MangaInfo` gains `source`, `source_url`, `artists`, `tags`.
  `Chapter` gains `image_urls` for providers that learn pages
  alongside the gallery (nhentai gives everything in one fetch).
- `ChapterDownloader` / `MangaDownloader` take a `Provider`; image
  downloads use the provider's `image_referer`.
- CLI and GUI bridges route via `get_provider_for_url` instead of
  hard-coding comix.to.
- Why: enable multi-site support without forking the pipeline.
