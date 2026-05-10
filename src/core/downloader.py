"""
Main downloader with threading support for concurrent downloads.
"""

import re
import time
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import Optional, Callable
from rich.progress import Progress, TaskID, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

from .models import MangaInfo, Chapter, DownloadConfig, OutputFormat
from ..providers.base import Provider
from ..formats.images import save_images, cleanup_images
from ..formats.pdf import create_pdf
from ..formats.cbz import create_cbz
from ..utils.retry import RetryableDownloader
from ..utils.logger import get_logger
from ..utils.session import get_session

logger = get_logger(__name__)

# Global event to signal cancellation across all downloaders
_cancel_event = threading.Event()

def cancel_downloads():
    """Signal all active downloaders to stop."""
    _cancel_event.set()
    logger.warning("Cancellation signal received. Stopping downloads...")

def is_cancelled():
    """Check if cancellation has been signaled."""
    return _cancel_event.is_set()


def reset_cancel():
    """Clear the cancellation flag before starting a new session."""
    _cancel_event.clear()


class ImageDownloader:
    """Downloads images with threading and retry logic."""

    # Used as fallback extensions when a primary image URL 404s. nhentai
    # mirrors don't always agree per-page on jpg/png/webp.
    _EXT_FALLBACKS = ("webp", "jpg", "png", "gif")

    def __init__(self, config: DownloadConfig, headers: dict | None = None):
        self.config = config
        self.headers = headers or {}
        self.retrier = RetryableDownloader(
            max_retries=config.retry_count,
            base_delay=config.retry_delay
        )

    def _candidate_urls(self, url: str) -> list[str]:
        """Generate fallback URLs by swapping the file extension."""
        m = re.match(r"^(.*)\.([A-Za-z0-9]{2,4})$", url)
        if not m:
            return [url]
        base, ext = m.group(1), m.group(2).lower()
        candidates = [url]
        for cand_ext in self._EXT_FALLBACKS:
            if cand_ext != ext:
                candidates.append(f"{base}.{cand_ext}")
        return candidates

    def download_image(self, url: str, index: int) -> tuple[int, bytes | None, str | None]:
        """
        Download a single image. Tries the primary URL plus extension
        fallbacks once each. Retries with exponential backoff only for
        transient errors — a 404 on every candidate is permanent.
        """
        candidates = self._candidate_urls(url)
        max_attempts = max(1, self.config.retry_count + 1)
        last_error: str | None = None

        for attempt in range(max_attempts):
            if is_cancelled():
                return index, None, "Download cancelled"

            transient_seen = False
            permanent_404 = True  # flips false if we get any non-404
            attempt_error: str | None = None

            for cand in candidates:
                if is_cancelled():
                    return index, None, "Download cancelled"
                try:
                    logger.debug(f"Image {index}: GET {cand}")
                    response = get_session().get(
                        cand, timeout=30, stream=True, headers=self.headers or None
                    )
                    if response.status_code == 404:
                        attempt_error = "HTTP Error 404"
                        continue  # try next extension
                    permanent_404 = False
                    response.raise_for_status()

                    # Stream into bytes
                    content = bytearray()
                    for chunk in response.iter_content(chunk_size=8192):
                        if is_cancelled():
                            return index, None, "Download cancelled"
                        if chunk:
                            content.extend(chunk)
                    return index, bytes(content), None

                except Exception as e:
                    permanent_404 = False
                    transient_seen = True
                    attempt_error = str(e)
                    logger.debug(f"Image {index}: {cand} failed ({e}); trying next")

            # All candidates exhausted for this attempt
            last_error = attempt_error or "unknown error"

            if permanent_404:
                # Every URL returned 404 — there's nothing to retry to
                return index, None, last_error

            if attempt < max_attempts - 1 and transient_seen:
                delay = self.config.retry_delay * (2 ** attempt)
                logger.warning(
                    f"Image {index} - Attempt {attempt + 1}/{max_attempts} failed: "
                    f"{last_error}. Retrying in {delay}s..."
                )
                time.sleep(delay)

        return index, None, last_error
    
    def download_indexed_images(
        self,
        indexed_urls: list[tuple[int, str]],
        total_for_progress: int | None = None,
        already_done: int = 0,
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[tuple[int, bytes]]:
        """Download a specific list of (index, url) pairs concurrently.

        ``already_done`` and ``total_for_progress`` let resume callers
        report progress relative to the chapter as a whole rather than
        the subset of pages we're actually fetching.
        """
        results: list[tuple[int, bytes]] = []
        failed: list[tuple[int, str | None]] = []

        if not indexed_urls:
            if on_progress and total_for_progress is not None:
                on_progress(already_done, total_for_progress)
            return results

        total = total_for_progress or len(indexed_urls)
        logger.info(f"Downloading {len(indexed_urls)} images concurrently...")

        with ThreadPoolExecutor(max_workers=self.config.max_image_workers) as executor:
            futures = {
                executor.submit(self.download_image, url, idx): idx
                for idx, url in indexed_urls
            }

            for future in as_completed(futures):
                if is_cancelled():
                    break
                idx = futures[future]
                try:
                    index, data, error = future.result()
                    if data:
                        results.append((index, data))
                    else:
                        failed.append((index, error))
                        logger.error(f"Failed to download image {index}: {error}")
                except Exception as e:
                    failed.append((idx, str(e)))
                    logger.error(f"Exception downloading image {idx}: {e}")

                if progress and task_id:
                    progress.advance(task_id)

                if on_progress:
                    on_progress(already_done + len(results) + len(failed), total)

        if failed:
            logger.warning(f"{len(failed)} images failed to download")

        return sorted(results, key=lambda x: x[0])

    def download_all_images(
        self,
        image_urls: list[str],
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[tuple[int, bytes]]:
        """Backward-compatible wrapper that fetches every URL in order."""
        indexed = list(enumerate(image_urls, 1))
        return self.download_indexed_images(
            indexed,
            total_for_progress=len(indexed),
            already_done=0,
            progress=progress,
            task_id=task_id,
            on_progress=on_progress,
        )


_IMG_FILE_RE = re.compile(r"^(\d+)\.(jpg|jpeg|png|webp|gif)$", re.IGNORECASE)


class ChapterDownloader:
    """Downloads a single chapter with all its images."""

    def __init__(self, config: DownloadConfig, manga: MangaInfo, provider: Provider):
        self.config = config
        self.manga = manga
        self.provider = provider
        self.image_downloader = ImageDownloader(
            config,
            headers=provider.chapter_request_headers(),
        )

    @staticmethod
    def _scan_existing_pages(chapter_dir: Path, max_idx: int) -> dict[int, Path]:
        """Map page index -> Path for non-empty image files already on disk."""
        if not chapter_dir.exists():
            return {}
        found: dict[int, Path] = {}
        for p in chapter_dir.iterdir():
            if not p.is_file():
                continue
            m = _IMG_FILE_RE.match(p.name)
            if not m:
                continue
            idx = int(m.group(1))
            if not (1 <= idx <= max_idx):
                continue
            try:
                if p.stat().st_size > 0:
                    found[idx] = p
            except OSError:
                continue
        return found

    def _is_chapter_complete(
        self, base_path: Path, chapter_folder: str, total_pages: int
    ) -> bool:
        """True if the final artifact for this format already has all pages."""
        fmt = self.config.output_format

        if fmt == OutputFormat.IMAGES:
            chapter_dir = base_path / chapter_folder
            return len(self._scan_existing_pages(chapter_dir, total_pages)) >= total_pages

        if fmt == OutputFormat.CBZ:
            cbz_path = base_path / f"{chapter_folder}.cbz"
            if not cbz_path.exists():
                return False
            try:
                with zipfile.ZipFile(cbz_path) as z:
                    count = sum(
                        1 for n in z.namelist() if _IMG_FILE_RE.match(Path(n).name)
                    )
                    return count >= total_pages
            except (zipfile.BadZipFile, OSError):
                return False

        if fmt == OutputFormat.PDF:
            pdf_path = base_path / f"{chapter_folder}.pdf"
            try:
                return pdf_path.exists() and pdf_path.stat().st_size > 0
            except OSError:
                return False

        return False

    def download_chapter(
        self,
        chapter: Chapter,
        progress: Optional[Progress] = None,
        parent_task: Optional[TaskID] = None,
        on_image_progress: Optional[Callable[[int, int], None]] = None,
    ) -> tuple[bool, str]:
        """Download a chapter, skipping/resuming work that's already on disk."""
        manga_folder = self.manga.get_safe_title()
        chapter_folder = chapter.get_safe_folder_name()
        base_path = Path(self.config.download_path) / manga_folder
        chapter_dir = base_path / chapter_folder

        try:
            image_urls = self.provider.get_chapter_images(chapter)
            if not image_urls:
                return False, f"No images found for {chapter.get_display_name()}"

            total_pages = len(image_urls)

            # ---- whole-chapter skip ------------------------------------
            if self._is_chapter_complete(base_path, chapter_folder, total_pages):
                if on_image_progress:
                    on_image_progress(total_pages, total_pages)
                if progress:
                    tid = progress.add_task(
                        f"[green]  └─ {chapter.get_display_name()} (skipped)",
                        total=total_pages,
                        completed=total_pages,
                    )
                logger.info(
                    f"{chapter.get_display_name()}: already on disk, skipping"
                )
                return True, f"Skipped (already downloaded): {chapter.get_display_name()}"

            # ---- partial resume ---------------------------------------
            # Per-image resume is only meaningful when intermediate image
            # files exist — i.e. format=IMAGES, or format=PDF/CBZ with
            # keep_images=True. For keep_images=False we keep only the
            # final artifact, so resume is whole-chapter only.
            keeps_intermediates = (
                self.config.output_format == OutputFormat.IMAGES
                or self.config.keep_images
            )
            existing_paths: dict[int, Path] = (
                self._scan_existing_pages(chapter_dir, total_pages)
                if keeps_intermediates
                else {}
            )
            skipped_count = len(existing_paths)

            urls_to_fetch: list[tuple[int, str]] = [
                (idx, url)
                for idx, url in enumerate(image_urls, 1)
                if idx not in existing_paths
            ]

            if skipped_count > 0:
                logger.info(
                    f"{chapter.get_display_name()}: resuming "
                    f"({skipped_count}/{total_pages} pages on disk, "
                    f"{len(urls_to_fetch)} to fetch)"
                )

            task_id = None
            if progress:
                task_id = progress.add_task(
                    f"[cyan]  └─ {chapter.get_display_name()}",
                    total=total_pages,
                    completed=skipped_count,
                )
            if on_image_progress and skipped_count > 0:
                on_image_progress(skipped_count, total_pages)

            new_image_data = self.image_downloader.download_indexed_images(
                urls_to_fetch,
                total_for_progress=total_pages,
                already_done=skipped_count,
                progress=progress,
                task_id=task_id,
                on_progress=on_image_progress,
            )

            if not new_image_data and not existing_paths:
                return False, (
                    f"Failed to download any images for {chapter.get_display_name()}"
                )

            # ---- materialize artifact ----------------------------------
            if self.config.output_format == OutputFormat.IMAGES:
                save_images(new_image_data, base_path, chapter_folder)

            elif self.config.output_format == OutputFormat.PDF:
                pdf_path = base_path / f"{chapter_folder}.pdf"
                if self.config.keep_images:
                    new_paths = save_images(new_image_data, base_path, chapter_folder)
                    all_paths = sorted(
                        list(existing_paths.values()) + new_paths,
                        key=lambda p: p.name,
                    )
                    create_pdf(all_paths, pdf_path, chapter.get_display_name())
                else:
                    from ..formats.pdf import create_pdf_from_bytes
                    create_pdf_from_bytes(
                        new_image_data, pdf_path, chapter.get_display_name()
                    )

            elif self.config.output_format == OutputFormat.CBZ:
                cbz_path = base_path / f"{chapter_folder}.cbz"
                if self.config.keep_images:
                    new_paths = save_images(new_image_data, base_path, chapter_folder)
                    all_paths = sorted(
                        list(existing_paths.values()) + new_paths,
                        key=lambda p: p.name,
                    )
                    create_cbz(all_paths, cbz_path, self.manga, chapter)
                else:
                    from ..formats.cbz import create_cbz_from_bytes
                    create_cbz_from_bytes(
                        new_image_data, cbz_path, self.manga, chapter
                    )

            if progress and task_id is not None:
                progress.update(task_id, completed=total_pages)

            new_count = len(new_image_data)
            if skipped_count > 0:
                msg = (
                    f"Downloaded {chapter.get_display_name()} "
                    f"({new_count} new + {skipped_count} resumed = "
                    f"{new_count + skipped_count}/{total_pages} pages)"
                )
            else:
                msg = (
                    f"Downloaded {chapter.get_display_name()} "
                    f"({new_count} pages)"
                )
            return True, msg

        except Exception as e:
            logger.error(f"Error downloading chapter {chapter.number}: {e}")
            return False, f"Error: {str(e)}"


class MangaDownloader:
    """Main downloader orchestrating concurrent chapter downloads."""

    def __init__(self, config: DownloadConfig, provider: Provider):
        self.config = config
        self.provider = provider

    def download_chapters(
        self,
        manga: MangaInfo,
        chapters: list[Chapter],
        progress: Progress,
        on_chapter_complete: Optional[Callable[[Chapter, bool, str], None]] = None
    ) -> tuple[int, int]:
        """
        Download multiple chapters concurrently.

        Returns:
            Tuple of (successful_count, failed_count)
        """
        from .failure_log import FailureLog
        from ..utils.library import shared as _library

        successful = 0
        failed = 0
        failure_log = FailureLog(manga, self.config)

        # Persist a library entry up front so the GUI's Library tab
        # picks the manga up even if every chapter ends up failing.
        try:
            _library().upsert_manga(
                manga,
                self.config.output_format.value,
                self.config.download_path,
            )
        except Exception as exc:
            logger.warning("library upsert_manga failed: %s", exc)

        chapter_downloader = ChapterDownloader(self.config, manga, self.provider)
        
        # Create main progress task
        main_task = progress.add_task(
            f"[bold green]Downloading {manga.title}",
            total=len(chapters)
        )
        
        with ThreadPoolExecutor(max_workers=self.config.max_chapter_workers) as executor:
            futures = {
                executor.submit(
                    chapter_downloader.download_chapter,
                    chapter,
                    progress,
                    main_task
                ): chapter
                for chapter in chapters
            }
            
            for future in as_completed(futures):
                if is_cancelled():
                    break
                chapter = futures[future]
                try:
                    success, message = future.result()
                    if success:
                        successful += 1
                        try:
                            _library().record_chapter(
                                manga,
                                chapter,
                                self.config.output_format.value,
                                self.config.download_path,
                            )
                        except Exception as exc:
                            logger.warning(
                                "library record_chapter failed: %s", exc
                            )
                    else:
                        failed += 1
                        failure_log.record(chapter, message or "unknown error")

                    if on_chapter_complete:
                        on_chapter_complete(chapter, success, message)

                except Exception as e:
                    failed += 1
                    failure_log.record(chapter, str(e))
                    logger.error(f"Exception downloading chapter {chapter.number}: {e}")
                    if on_chapter_complete:
                        on_chapter_complete(chapter, False, str(e))

                progress.advance(main_task)

        log_path = failure_log.write()
        if log_path is not None:
            logger.warning(
                "Failed chapters written to %s — re-run to retry "
                "(successful chapters will skip).", log_path,
            )
        return successful, failed
