#!/usr/bin/env python3
"""
refresh_icloud.py — one-shot wrapper that runs the full iCloud → library
pipeline end-to-end.

Order matters (each step depends on the previous one's output):

  1. ``icloud_inventory.py``       Walk the iCloud Manga folder. Detects
                                   new folders and preserves Phase-2
                                   match data for existing ones.
  2. ``icloud_match.py            Cross-site search for entries still
     --unknowns-only``             tagged ``unknown``. New folders fall
                                   into this bucket automatically.
  3. ``icloud_to_library.py``      Append newly matched entries into
                                   library.json (dedupes by URL).
  4. ``enrich_alternatives.py``    Fill in each library entry's
                                   ``alternative_sources`` list so the
                                   GUI's "Also on:" chips refresh.

Run this whenever you add manga to iCloud. The cache + prior-inventory
merging means each step skips work it's already done — incremental
runs are fast.

Flags:
  --skip-match   Skip step 2 (use when you only changed library code,
                 not the iCloud folder).
  --skip-import  Skip step 3.
  --skip-enrich  Skip step 4.

Each step's stdout is forwarded with a section header. If any step
exits non-zero, the wrapper bails — partial output is fine to inspect.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Import each step's main() rather than shelling out — saves Python
# startup time × 4 and keeps tracebacks intact across the chain.
import icloud_inventory
import icloud_match
import icloud_to_library
import enrich_alternatives


def banner(step: int, total: int, label: str) -> None:
    bar = "─" * 70
    print()
    print(bar)
    print(f"  Step {step}/{total} — {label}")
    print(bar)


def main(argv: list[str]) -> int:
    skip_match = "--skip-match" in argv
    skip_import = "--skip-import" in argv
    skip_enrich = "--skip-enrich" in argv

    steps: list[tuple[str, callable]] = []
    steps.append(("Inventory iCloud (read-only)",
                  lambda: icloud_inventory.main()))
    if not skip_match:
        # icloud_match.main takes argv-style list. Pass --unknowns-only
        # so the run is cheap when most entries are already resolved.
        steps.append(("Cross-site match (unknowns only)",
                      lambda: icloud_match.main(
                          ["icloud_match.py", "--unknowns-only"])))
    if not skip_import:
        steps.append(("Import into library.json",
                      lambda: icloud_to_library.main()))
    if not skip_enrich:
        steps.append(("Enrich library with alternative sources",
                      lambda: enrich_alternatives.main()))

    total = len(steps)
    t0 = time.time()
    for i, (label, fn) in enumerate(steps, 1):
        banner(i, total, label)
        t_step = time.time()
        rc = fn() or 0
        elapsed = time.time() - t_step
        print(f"\n  ↳ {label}: rc={rc} in {elapsed:.1f}s")
        if rc != 0:
            print(f"\nStep {i} failed (rc={rc}); aborting.", file=sys.stderr)
            return rc

    total_elapsed = time.time() - t0
    print()
    print("═" * 70)
    print(f"  ✓ Pipeline complete in {total_elapsed:.1f}s")
    print("═" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
