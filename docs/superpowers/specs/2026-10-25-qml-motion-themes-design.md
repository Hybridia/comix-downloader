# Qt GUI — themes + motion redesign

Date: 2026-10-25
Status: approved direction (mockups), awaiting sign-off on this document

## Intent

The user likes the Qt app and wants it to *look and feel* better: richer
colour, and lots of smooth, playful animation. They briefly considered an
HTML front-end because "HTML can do visuals better"; we agreed QML can do
the same effects natively, so the existing PyQt6 + QML app stays and gets
restyled in place. **No new front-end, no behaviour changes** to
downloading, library, updates or settings logic.

Reference mockups (interactive, the source of truth for look and motion):

- `.superpowers/brainstorm/17191-1792952226/content/animations.html` —
  colour moods, Library / Updates / Downloads behaviour, 12-effect gallery
- `.superpowers/brainstorm/17191-1792952226/content/browse-settings-v2.html` —
  Browse and Settings

The user approved **all** of it: all three themes and every effect shown.

## Goals

1. **Theme system with three switchable themes**, chosen in Settings:
   - **Ink & Sakura** — bg `#0B0F1A`, surface `#111726`, card `#172033`,
     elevated `#1F2A42`, border `#2A3652`, accent `#FF7A93`, accent2
     `#E8506E`, highlight `#FFC2CF`, cool `#8FD3FF`, text `#F3EFE6` /
     `#9AA3B8` / `#5F6880`.
   - **Neon Tokyo** — bg `#07060E`, surface `#100E1C`, card `#17142A`,
     elevated `#211C3A`, border `#2D2650`, accent `#FF3DA8`, accent2
     `#B03CFF`, highlight `#FF9BE0`, cool `#35F0FF`, text `#F4F0FF` /
     `#9A90C0` / `#5E5680`.
   - **Ember** — today's palette (bg `#0A0A0C`, surface `#141419`, card
     `#1C1C24`, elevated `#252530`, border `#2A2A33`, accent `#E8A54B`,
     accent2 `#D4873A`, highlight `#FFD93D`, cool `#4ECDC4`, text
     `#F5F5F0` / `#8B8B99` / `#5C5C66`).
   - Status colours (success / error / warning / info) stay shared across
     themes. Each theme also defines a `glow` colour = accent at ~45 %
     alpha.
   - Switching is live (no restart) and persisted in `config.json`.
2. **Every effect from the mockups**, in the real app:
   - App-wide: drifting background glow blobs; view transitions (slide +
     fade + un-blur) with the sidebar indicator springing to the active
     tab; springy buttons (lift on hover, squish on press) with a click
     ripple; toast notifications (slide in, stack, auto-dismiss);
     counting numbers; skeleton shimmer while loading; "working" pulse
     rings; celebration particle burst.
   - Library: staggered card entrance; 3D hover tilt + cover shine sweep;
     cover flip showing chapter count / site / status on the back;
     status-pill menu that scales open from its origin with staggered
     items; "Check for new" morph (button → spinner → "✦ N new" with
     count-up) → Download → progress ring → drawn checkmark + "Downloaded
     N new chapters" + burst + toast.
   - Updates: staggered rows; chapter chips pop on toggle; total in the
     Download button rolls to the new number; sidebar badge bounces when
     a check finds updates.
   - Downloads: job cards rise in; progress bar with flowing gradient +
     shimmer + glow; chapter rows slide in and tick to done; finished job
     flashes, bursts, and raises a toast.
   - Browse: URL box focus glow, green "match" glow + ✓ pop + matching
     site chip lights (others dim) + Fetch pulses when ready; shake on
     Enter with an unsupported URL; skeleton manga card while fetching;
     cover blur-up + shine, title letters rise in, tags pop staggered,
     stats count up, description expands smoothly; chapter rows slide
     in, animated checkbox tick, shift-click range select with a ripple
     "wave", Select All cascade, filter field widens on focus, selected
     counter ticks; format selector with a spring-sliding highlight;
     Download button sheen; on Download, a bubble with the chapter count
     flies in an arc to the sidebar Downloads entry and its badge
     bounces; drag-a-URL drop zone glow.
   - Settings drawer: springs in from the right with a blurred, dimmed
     backdrop; sections slide in staggered; theme cards; circular colour
     wipe from the click point when switching theme; springy toggle
     switches; sliders with a value bubble; Toomics login button morphs
     to a spinner then success text, failure shakes the section red;
     "Hold to reset to defaults" fills while held, drains back on early
     release; close button rotates on hover.
3. **Two new Settings toggles**: "Animations" (master switch) and
   "Drifting background glow". With Animations off, durations collapse to
   ~0 and decorative effects (blobs, particles, tilt, shimmer loops,
   pulses) are not created — the app must stay fully usable.

## Non-goals

- No HTML / browser front-end.
- No changes to providers, downloader, library, update-check or bridge
  *logic*. Bridges may gain small read/write accessors needed by the UI
  (theme name, animation toggles) and signals the UI needs to trigger
  effects; nothing else.
- No new features beyond what the mockups show (e.g. drag-and-drop of a
  URL is in scope only as the drop-zone visual on the Browse URL box —
  dropping a URL fills the box; nothing more). The small interactions the
  mockups *do* show are in scope, because the user approved them as
  shown: shift-click range select and a text filter on the Browse
  chapter list, a format selector on Browse, a Downloads sidebar badge,
  the Library cover flip, and hold-to-reset in Settings (see "Builder's
  calls" for how each behaves).
- No layout overhaul. Screens keep their current structure; the mockups'
  arrangement is close to today's and where they differ, today's layout
  wins unless the effect needs the change.

## Anti-goals (would make it a failure even if it "works")

- Janky motion: dropped frames on the Library grid (~260 entries) or
  while downloads run. Effects must be cheap enough not to stutter the
  UI on a MacBook; prefer transforms/opacity over re-layout.
- Animations that slow the user down: nothing may block input or delay
  an action. Transitions ≤ ~600 ms; anything decorative must be
  interruptible.
- Losing readability: text contrast on all three themes must stay
  comfortable; Fusion palette overrides on every TextField (see the
  2026-05-04 changelog) must follow the theme.
- Regressions in existing behaviour (signals, bridges, the stale
  "Downloading…" fix from 2026-10-24).

## Constraints

- PyQt6 / Qt **6.11**; QML modules available: QtQuick.Effects
  (MultiEffect), QtQuick.Particles, QtQuick.Shapes, Controls (Fusion is
  forced via `QT_QUICK_CONTROLS_STYLE`).
- Colours are currently **duplicated** as `readonly property color …` in
  ~10 QML files; `gui/qml/Theme.qml` exists (`pragma Singleton`) but is
  not registered (no `qmldir`) and is effectively unused. The redesign
  must route every colour through one live theme source so switching
  themes recolours everything.
- Settings persist through `ConfigManager` / `SettingsBridge`
  (`config.json` at project root). New keys need defaults in
  `ConfigManager.DEFAULT_CONFIG`.
- The window is frameless with a custom TitleBar; keep that.
- macOS is the primary platform; the app also starts with `--cpu`
  (software rendering). Under software rendering, MultiEffect/shader
  effects may not work — degrade gracefully (skip blur/wipe), never
  crash.

## Decisions made in conversation

- Stay on Qt/QML (user's choice after discussing HTML).
- All three themes ship; switchable in Settings.
- All effects shown in both mockups ship.

## Builder's calls (made by me, flagged for the user)

- **Default theme for new installs: Ink & Sakura** (the user liked both
  Ink & Sakura and Neon Tokyo and didn't pick; Ink & Sakura was the
  Browse mockup's starting theme). Existing users also land on Ink &
  Sakura unless they change it.
- **Animations default on; background glow default on.**
- **Browse format selector = the global `output_format` setting**, shown
  in a second place. Changing it on Browse writes the setting, and the
  Settings drawer's format buttons stay; both stay in sync. No
  per-download override, no bridge change.
- **Chapter text filter** matches the chapter number or title
  (case-insensitive substring) and works alongside the existing
  Scanlator Filter. "Select All" / "None" and shift-click ranges act on
  the visible (filtered) rows only. Shift-click with no previous click
  behaves like a plain click.
- **Hold to reset** replaces the single-click "Reset to Defaults"
  (~1.4 s hold; releasing early cancels). Resets the same settings as
  today.
- **Downloads badge** shows the number of chapters still queued or
  downloading across all jobs. It counts down as chapters finish
  (succeeded or failed) and hides at 0. The fly-to bubble lands on it.
  Derived in QML from the existing `jobStarted` / `chapterComplete` /
  `downloadFinished` / `jobCancelled` signals; no new bridge API.
- **Library cover flip** is triggered by a small ⓘ button in the cover's
  top-right corner (the select checkbox keeps the top-left). Clicking ⓘ
  flips that card to show chapter count, site, status and last
  downloaded; clicking again or moving the mouse off the card flips it
  back. Hover keeps the tilt + shine only.
- Implementation approach is the builder's call — e.g. a registered
  theme singleton (or context-property QObject) exposing the palette,
  reusable QML components for repeated effects (button, toast host,
  particle burst, skeleton, count-up text), and a global animation-scale
  factor driven by the Animations toggle.

## Left to the builder

- Exact durations/easings (match the mockups' feel: springy overshoot on
  interactive elements, ease-out ~400–600 ms on transitions).
- Which existing components are refactored vs rewritten.
- How the circular theme wipe is done (e.g. grab old frame to an image
  and reveal the new theme through an animated circular mask), and its
  fallback under software rendering (plain crossfade).
- Where toasts are triggered from (bridge signals that already exist,
  e.g. `downloadFinished`, `libraryJobFinished`, `updateCheckFinished`,
  settings login result).
- Verification approach (offscreen launch, screenshots, manual run).
