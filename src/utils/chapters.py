"""
Chapter-number helpers shared by the Update flow, the update checker
and source detection.

The library.json "chapters" dict is advisory only — what's actually ON
DISK in the user's iCloud (or wherever ``download_path/folder`` points)
is the ground truth for what they have. These helpers read chapter
numbers out of CBZ filenames and normalise them so that
``Chapter_62.5.cbz`` (iCloud's dot convention) and ``chapter-62-5``
(Madara's hyphen convention) count as the same chapter.
"""

import re
from pathlib import Path
from typing import Optional


# Match "Chapter 62", "Chapter_62", "ch 62.5", "Chapter_68_1.cbz", "Chapter_82-5",
# "Chapter 4.1". The fraction separator can be ``.``, ``-``, or ``_`` —
# users encode sub-chapters all three ways in filenames (``68.5`` /
# ``68-5`` / ``68_5``). The normaliser below collapses them.
FILENAME_CHAPTER_RE = re.compile(
    r"(?:chapter|chap|episode|ep|ch)[_\s\.\-]*(\d+(?:[-._]\d+)?)",
    re.IGNORECASE,
)


def norm_chapter_number(n: str) -> str:
    """
    Canonicalise a chapter-number string for cross-site comparison.

    - Collapses fraction separators (``62-5`` ⇄ ``62.5`` ⇄ ``62_5``)
      so the same chapter compares equal regardless of which site's
      or filename's convention it came from. Three separators are in
      common use:
        * dot — comix and most providers' canonical
        * hyphen — Madara URL slugs (``chapter-62-5``)
        * underscore — some iCloud filenames (``Chapter_62_5.cbz``)
          where the user replaced reserved chars manually
    - Strips leading zeros from the integer part (``007`` → ``7``)
      so padded filenames compare equal to unpadded site numbers.
    """
    s = str(n).replace("-", ".").replace("_", ".")
    if "." in s:
        head, tail = s.split(".", 1)
        try:
            head = str(int(head))
        except ValueError:
            pass
        return f"{head}.{tail}" if tail else head
    try:
        return str(int(s))
    except ValueError:
        return s


def chapter_number_from_filename(name: str) -> Optional[str]:
    """Normalised chapter number parsed from a filename stem, or None."""
    m = FILENAME_CHAPTER_RE.search(name)
    return norm_chapter_number(m.group(1)) if m else None


def chapter_numbers_on_disk(folder: Path) -> set[str]:
    """
    Return the set of normalised chapter numbers found as ``.cbz``
    files directly under ``folder``. Empty set if the folder doesn't
    exist or contains nothing recognisable.

    Only looks at directory entries — never opens a file, so it's safe
    on iCloud folders whose contents are cloud-only (no downloads are
    triggered). Doesn't recurse — chapters are flat in every format we
    support.
    """
    out: set[str] = set()
    try:
        if not folder.is_dir():
            return out
    except OSError:
        return out
    try:
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() != ".cbz":
                continue
            n = chapter_number_from_filename(entry.stem)
            if n:
                out.add(n)
    except OSError:
        pass
    return out


def chapter_float(n: str) -> Optional[float]:
    """Numeric value of a (normalised) chapter number, or None."""
    try:
        return float(norm_chapter_number(n))
    except (TypeError, ValueError):
        return None


def max_chapter(numbers) -> float:
    """Largest numerically-parseable chapter number, or -1 if none."""
    best = -1.0
    for n in numbers:
        try:
            best = max(best, float(n))
        except ValueError:
            continue
    return best
