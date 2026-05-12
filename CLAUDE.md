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
hentairead.com, hentaifox.com, toonily.com, manhwaread.com, toomics
(paid VIP), and mangafire.to are all supported sources.

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
| `manhwaread.com`        | none                | mangomic theme; b64 chapterData   | **Multi-chapter**; same theme as hentairead |
| `manhwabuddy.com`       | Cloudflare only     | plain HTML; `data-src` reader imgs | **Multi-chapter**; simplest provider in the matrix |
| `manhwa18.com`          | Cloudflare only     | plain HTML; `data-src` lazy imgs; rotating CDN | Multi-chapter NSFW manhwa; chapters use multiple CDN hosts |
| `mangadistrict.com`     | Cloudflare only     | Madara theme; eager `src` reader imgs | Multi-chapter NSFW manhwa; same theme as webtoonscan but no FlareSolverr needed |
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
│   ├── bridge/                   Python ↔ QML bridges
│   │   ├── manga_bridge.py       Fetches manga info via the provider router
│   │   ├── download_bridge.py    Drives concurrent chapter downloads + per-run failure log + library recording
│   │   ├── library_bridge.py     Library tab: list / update (diff vs remote) / remove / open folder
│   │   └── settings_bridge.py    Exposes ConfigManager + toomics auth to QML
│   └── qml/                      Views + components (SettingsDrawer, ProgressPanel, LibraryView, …)
├── scripts/                      Local diagnostic scripts (run from user's machine)
│   ├── toomics_test.py           End-to-end probe for the toomics provider
│   ├── mangafire_test.py         End-to-end probe for the mangafire provider
│   └── comix_test.py             End-to-end probe for the comix provider (fast + Playwright paths)
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
    │   ├── mangadistrict.py      MangadistrictProvider (multi-chapter; Madara; plain HTTP, no FlareSolverr)
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
  is a dict keyed by `Chapter.number` (string) so the Library tab's
  "Update" flow is a one-line set-difference against
  `provider.get_chapters(...)`. New numbers get queued via
  `DownloadBridge.startDownload`; the existing per-chapter resume
  logic transparently re-skips anything that somehow ended up on
  disk twice.
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
- The GUI's `LibraryBridge` (`gui/bridge/library_bridge.py`) exposes
  three slots to QML: `listEntries`, `updateEntry(url)` (worker
  thread → diff → hand to DownloadBridge), `removeEntry(url)`,
  `openFolder(url)`. `attach_download_bridge()` wires the
  cross-bridge call in `gui/main.py`.

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
