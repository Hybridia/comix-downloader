# Qt GUI Themes + Motion Implementation Plan

> **Status (2026-10-31): done.** All 10 tasks shipped 2026-10-25 (commits `7c90881` … `0eaa1c7`, app icon `b146dd4`); see the CLAUDE.md changelog entry "GUI themes + motion". Kept as the record of how it was built.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the existing PyQt6/QML GUI three live-switchable themes and every animation from the approved mockups, without changing app behaviour.

**Architecture:** A registered QML singleton module `Style` (`Theme` + `Fx`) becomes the single colour/motion source; every file's duplicated `readonly property color …` is rebound to it. Reusable effect components live in `gui/qml/fx/`. Pure UI logic (chapter filter, range select, Downloads badge, stagger delays, palettes) lives in `.pragma library` JS files so it can be unit-tested from Python via `QJSEngine`. A headless smoke test loads the real `main.qml` and fails on any QML warning.

**Tech Stack:** PyQt6 / Qt 6.11, QtQuick, QtQuick.Controls (Fusion), QtQuick.Effects (MultiEffect), QtQuick.Particles, QtQuick.Shapes; stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-25-qml-motion-themes-design.md`
**Look/motion reference:** `.superpowers/brainstorm/17191-1792952226/content/animations.html`, `.superpowers/brainstorm/17191-1792952226/content/browse-settings-v2.html` — open them in a browser; match their feel.

## Global Constraints

- Palettes, exact (from spec):
  - `ink`: bg `#0B0F1A`, surface `#111726`, card `#172033`, elevated `#1F2A42`, border `#2A3652`, accent `#FF7A93`, accent2 `#E8506E`, highlight `#FFC2CF`, cool `#8FD3FF`, textPrimary `#F3EFE6`, textSecondary `#9AA3B8`, textTertiary `#5F6880`.
  - `neon`: bg `#07060E`, surface `#100E1C`, card `#17142A`, elevated `#211C3A`, border `#2D2650`, accent `#FF3DA8`, accent2 `#B03CFF`, highlight `#FF9BE0`, cool `#35F0FF`, textPrimary `#F4F0FF`, textSecondary `#9A90C0`, textTertiary `#5E5680`.
  - `ember`: bg `#0A0A0C`, surface `#141419`, card `#1C1C24`, elevated `#252530`, border `#2A2A33`, accent `#E8A54B`, accent2 `#D4873A`, highlight `#FFD93D`, cool `#4ECDC4`, textPrimary `#F5F5F0`, textSecondary `#8B8B99`, textTertiary `#5C5C66`.
  - Shared status colours (all themes): success `#7CB342`, error `#E57373`, warning `#FFB74D`, info `#64B5F6`. `glow` = accent at alpha 0.45.
- New config keys + defaults: `"theme": "ink"`, `"animations_enabled": true`, `"ambient_glow": true`. Unknown theme value → `ink`.
- No changes to providers, downloader, library, update-check, or bridge logic. Allowed bridge additions: `SettingsBridge.theme` / `animationsEnabled` / `ambientGlow` properties only. Downloads badge is derived in QML from existing `DownloadBridge` signals.
- Transitions ≤ ~600 ms; nothing blocks input; decorative loops interruptible. Spring feel = `Easing.OutBack` (overshoot ~1.2–1.6); transitions = `Easing.OutQuint`/`OutExpo`.
- Animations off ⇒ `Theme.dur(ms)` returns 0 and decorative items (ambient blobs, particles, tilt, shimmer loops, pulse rings, sheen) are not instantiated (`Loader { active: Theme.animations }`).
- Software rendering (`--cpu`, `QT_QUICK_BACKEND=software`): no MultiEffect/blur/mask; wipe degrades to a crossfade; never a QML error.
- Every `TextField` keeps the Fusion palette overrides (`palette.text`, `palette.placeholderText`, `palette.highlight`, `palette.highlightedText`, `selectionColor`, `selectedTextColor`) — now bound to `Theme`.
- Python files in `gui/bridge/` and `src/utils/config.py` use CRLF line endings — preserve them (edit in binary-safe way; `git diff --stat` must stay small).
- Test command for every task: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v`

## Review Focus

1. **`--cpu` / software backend** — app must load with zero QML warnings and the theme switch must still work (crossfade, no mask). → test in Task 2 (`test_loads_clean_software_backend`) and Task 5 (`test_theme_switch_software_backend`).
2. **Rapid theme switching** (three theme cards clicked within a second) — last click wins, no stacked wipe overlays left on screen. → Task 5 `test_rapid_theme_switch_leaves_one_overlay`.
3. **Large Library (~260 cards)** — staggered entrance must not make late cards wait: delay capped. → Task 1 `test_stagger_delay_capped`, used in Task 7.
4. **Cancelled / errored downloads** — Downloads badge drops that job's remaining chapters, never negative, never stuck. → Task 4 `test_badge_cancel_and_error`.
5. **Toggling Animations off while effects are running** — loops stop, durations become 0, no half-open drawer/half-flipped card. → Task 3 `test_animations_off_kills_decor`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `gui/app.py` (new) | `build_engine(software: bool=False) -> tuple[QQmlApplicationEngine, dict]` — engine + bridges setup, shared by `gui/main.py` and tests |
| `gui/qml/Style/qmldir` (new) | `module Style` / `singleton Theme 1.0 Theme.qml` / `singleton Fx 1.0 Fx.qml` |
| `gui/qml/Style/palettes.js` (new) | `.pragma library`; `palette(name) -> object`, `THEMES` |
| `gui/qml/Style/Theme.qml` (new; replaces unused `gui/qml/Theme.qml`) | live palette, motion helpers |
| `gui/qml/Style/Fx.qml` (new) | app-wide effect bus: `toast()`, `flyToDownloads()`, `requestThemeWipe()` signals |
| `gui/qml/logic/motion.js` | `staggerDelay(index)` |
| `gui/qml/logic/chapters.js` | filter + range-select helpers |
| `gui/qml/logic/badge.js` | Downloads badge reducer |
| `gui/qml/fx/*.qml` | reusable effects (see Task 3) |
| `tests/qmljs.py` | load a `.pragma library` JS file into `QJSEngine` and call functions |
| `tests/qmlsmoke.py` | shared offscreen app/engine fixture collecting QML warnings |
| `tests/test_*.py` | per-task tests |

---

### Task 1: Test harness + pure-logic JS libraries

**Files:**
- Create: `tests/__init__.py`, `tests/qmljs.py`, `tests/test_logic.py`
- Create: `gui/qml/logic/motion.js`, `gui/qml/logic/chapters.js`, `gui/qml/logic/badge.js`, `gui/qml/Style/palettes.js`

**Interfaces:**
- Produces:
  - `tests.qmljs.load(path: str) -> JsLib`; `JsLib.call(fn: str, *args) -> python value` (via `QJSEngine.evaluate`, stripping the `.pragma library` line; results converted with `.toVariant()`).
  - `motion.js`: `staggerDelay(index: int) -> int` — `index*45` ms for index < 12, else `540` (cap).
  - `chapters.js`: `matches(chapter: {number, title}, query: string) -> bool` (case-insensitive substring on `String(number)` or `title`; empty/whitespace query → true); `rangeIndices(anchor: int, index: int) -> int[]` (inclusive, ascending; anchor < 0 → `[index]`).
  - `badge.js` (immutable reducer over `{jobs: {jobId: remaining}}`): `empty()`, `jobStarted(s, jobId, total)`, `chapterDone(s, jobId)`, `jobEnded(s, jobId)` (finished/cancelled/error all remove the job), `count(s) -> int` (sum, never < 0).
  - `palettes.js`: `THEMES = ["ink","neon","ember"]`; `palette(name) -> {bg,surface,card,elevated,border,accent,accent2,highlight,cool,textPrimary,textSecondary,textTertiary}`; unknown name → ink.

- [x] **Step 1: Write failing tests** in `tests/test_logic.py`:

```python
class Motion(unittest.TestCase):
    def test_stagger_delay_capped(self):
        m = load("gui/qml/logic/motion.js")
        self.assertEqual(m.call("staggerDelay", 0), 0)
        self.assertEqual(m.call("staggerDelay", 3), 135)
        self.assertEqual(m.call("staggerDelay", 259), 540)

class Chapters(unittest.TestCase):
    def test_matches(self):
        c = load("gui/qml/logic/chapters.js")
        self.assertTrue(c.call("matches", {"number": "55.5", "title": "Chapter 55.5"}, "55"))
        self.assertTrue(c.call("matches", {"number": "3", "title": "The END"}, "end"))
        self.assertFalse(c.call("matches", {"number": "3", "title": "x"}, "9"))
        self.assertTrue(c.call("matches", {"number": "3", "title": "x"}, "  "))
    def test_range(self):
        c = load("gui/qml/logic/chapters.js")
        self.assertEqual(c.call("rangeIndices", 5, 2), [2, 3, 4, 5])
        self.assertEqual(c.call("rangeIndices", -1, 4), [4])

class Badge(unittest.TestCase):
    def test_counts_down(self):
        b = load("gui/qml/logic/badge.js")
        s = b.call("jobStarted", b.call("empty"), "j1", 4)
        s = b.call("jobStarted", s, "j2", 2)
        s = b.call("chapterDone", s, "j1")
        self.assertEqual(b.call("count", s), 5)
    def test_badge_cancel_and_error(self):
        b = load("gui/qml/logic/badge.js")
        s = b.call("jobStarted", b.call("empty"), "j1", 3)
        s = b.call("jobEnded", s, "j1")
        s = b.call("chapterDone", s, "j1")          # late signal after end
        s = b.call("chapterDone", s, "unknown")
        self.assertEqual(b.call("count", s), 0)

class Palettes(unittest.TestCase):
    def test_exact_values_and_fallback(self):
        p = load("gui/qml/Style/palettes.js")
        self.assertEqual(p.call("palette", "ink")["accent"].lower(), "#ff7a93")
        self.assertEqual(p.call("palette", "neon")["cool"].lower(), "#35f0ff")
        self.assertEqual(p.call("palette", "ember")["bg"].lower(), "#0a0a0c")
        self.assertEqual(p.call("palette", "bogus"), p.call("palette", "ink"))
```

- [x] **Step 2: Run** the test command. Expected: FAIL (modules missing).
- [x] **Step 3: Implement** `tests/qmljs.py` and the four JS files per the Interfaces block (all palette values from Global Constraints). JS files start with `.pragma library` so QML can import them.
- [x] **Step 4: Run** the test command. Expected: all PASS.
- [x] **Step 5: Commit** `test: add QJSEngine harness and pure UI logic libraries`.

---

### Task 2: Theme system end-to-end

**Files:**
- Create: `gui/app.py`, `gui/qml/Style/qmldir`, `gui/qml/Style/Theme.qml`, `gui/qml/Style/Fx.qml` (signals only for now), `tests/qmlsmoke.py`, `tests/test_theme.py`
- Delete: `gui/qml/Theme.qml` (unused, superseded)
- Modify: `gui/main.py` (use `build_engine`), `src/utils/config.py` (`DEFAULT_CONFIG` keys), `gui/bridge/settings_bridge.py` (3 properties), every QML file listed by `grep -rn "readonly property color" gui/qml`, plus `LibraryView.qml:485` `activeColor`.

**Interfaces:**
- Consumes: `palettes.js` (Task 1).
- Produces:
  - `gui.app.build_engine(software: bool = False) -> (engine, {"manga","download","settings","library"})` — everything `gui/main.py` does after `QApplication` creation and before `app.exec()` (bridges, context properties, import path, `engine.load(main.qml)`). `main.py` keeps arg parsing, env vars, fonts, logging.
  - `SettingsBridge.theme: str` (read: config `theme`, unknown → `"ink"`; write: validates against `ink|neon|ember`, ignores others), `animationsEnabled: bool`, `ambientGlow: bool` — all `notify=settingsChanged`.
  - `Theme` singleton (`import Style`): `name`, the 12 palette colours (same names as `palettes.js`), `success`, `error`, `warning`, `info`, `glow`; `animations: bool`, `ambient: bool`, `software: bool` (`GraphicsInfo.api === GraphicsInfo.Software`); `function dur(ms) -> int` (0 when `!animations`). Bound to `SettingsBridge`.
  - `Fx` singleton: `signal toastRequested(string text, string kind)`, `function toast(text, kind)`; `signal flyRequested(point from, int count)`; `signal themeWipeRequested(string name, point origin)`.
  - `tests.qmlsmoke.Smoke`: `setUpClass` creates one `QApplication` (offscreen) and `build_engine()` against a temp copy of `config.json` (set `ConfigManager` path via env or monkeypatch — tests must never write the real `config.json`); collects `engine.warnings`; helpers `root()`, `find(objectName)`, `pump(ms)`, `assert_no_qml_warnings()`.
- Colour rebinding map (keep each file's local property names; only the value changes): `bgDeep→Theme.bg`, `bgSurface→Theme.surface`, `bgCard→Theme.card`, `bgElevated→Theme.elevated`, `borderColor→Theme.border`, `accentPrimary→Theme.accent`, `accentGradientEnd→Theme.accent2`, `accentHighlight→Theme.highlight`, `accentSecondary→Theme.cool`, `textPrimary/Secondary/Tertiary→Theme.textPrimary/…`, `success/okColor/activeColor(green)→Theme.success`, `error/danger→Theme.error`, `warning→Theme.warning`, `info/activeColor(blue)→Theme.info`. `readonly` stays; hard-coded hex colours elsewhere in those files that equal a palette colour are rebound too.

- [x] **Step 1: Write failing tests** in `tests/test_theme.py`:

```python
class ThemeTests(Smoke):
    def test_loads_clean(self):
        self.assert_no_qml_warnings()
    def test_default_is_ink(self):
        self.assertEqual(self.bridges["settings"].theme, "ink")
        self.assertEqual(self.eval_qml("Theme.accent").name().lower(), "#ff7a93")
    def test_live_switch(self):
        self.bridges["settings"].theme = "neon"; self.pump(50)
        self.assertEqual(self.eval_qml("Theme.accent").name().lower(), "#ff3da8")
    def test_invalid_theme_ignored(self):
        self.bridges["settings"].theme = "bogus"
        self.assertIn(self.bridges["settings"].theme, ("ink", "neon", "ember"))
    def test_no_hardcoded_palette_left(self):
        # every 'readonly property color' in gui/qml binds to Theme.*, except Style/ and per-status helpers
        offenders = scan_hardcoded_colour_props("gui/qml")
        self.assertEqual(offenders, [])

class SoftwareBackend(Smoke):
    software = True
    def test_loads_clean_software_backend(self):
        self.assert_no_qml_warnings()
```

(`eval_qml(expr)` evaluates in the root context via a `QQmlExpression`; `scan_hardcoded_colour_props` is a small regex helper in `tests/qmlsmoke.py` returning `file:line` for `readonly property color X: "#…"` outside `gui/qml/Style/`.)

- [x] **Step 2: Run** the test command. Expected: FAIL.
- [x] **Step 3: Implement** `build_engine`, config defaults, `SettingsBridge` properties, `Style` module, and the rebinding across all QML files. Add `import Style` to each file.
- [x] **Step 4: Run** the test command. Expected: PASS. Also run `python gui/main.py` briefly and confirm it opens in Ink & Sakura.
- [x] **Step 5: Commit** `feat(gui): live theme system (Ink & Sakura, Neon Tokyo, Ember)`.

---

### Task 3: Motion primitives (`gui/qml/fx/`)

**Files:**
- Create: `gui/qml/fx/FxButton.qml`, `Ripple.qml`, `ToastHost.qml`, `ParticleBurst.qml`, `Skeleton.qml`, `CountUpText.qml`, `PulseRings.qml`, `AmbientGlow.qml`, `tests/qml/FxGallery.qml`, `tests/test_fx.py`
- Modify: `gui/qml/main.qml` (add `AmbientGlow` behind content, `ToastHost` on top)

**Interfaces:**
- Consumes: `Theme`, `Fx` (Task 2).
- Produces (all `import "../fx"` from components/views):
  - `FxButton { text; primary: bool=true; enabled; signal clicked() }` — gradient `accent→accent2` when primary, ghost (`card` + `border`) otherwise; hover lifts 2px + scale 1.03, press scale 0.94 (spring), `Ripple` from the press point.
  - `Ripple { function spawn(x, y) }` — clipped circle expanding ×4 and fading, 600 ms.
  - `ToastHost` — anchored bottom-right of window; listens to `Fx.toastRequested`; slide-in from right with spring, stack (max 4, oldest dropped), auto-dismiss 3.2 s with fade/slide out; `kind` ∈ `info|ok|error` sets the left border colour (accent/success/error).
  - `ParticleBurst { function burst() }` — QtQuick.Particles emitter at the item centre, ~34 particles in accent/highlight/cool/accent2, ~1.1 s; inside a `Loader { active: Theme.animations }`; `burst()` is a no-op when inactive.
  - `Skeleton { radius }` — rectangle with moving `elevated→border→elevated` shimmer (static fill when animations off).
  - `CountUpText { value: real; decimals: int=0; duration: int=1200 }` — animates displayed number to `value` (ease-out cubic), locale thousands separators.
  - `PulseRings { color }` — two rings scaling 1→2.4 and fading, staggered 1 s, infinite while `running`.
  - `AmbientGlow` — 3 large blurred accent/cool/accent2 circles drifting slowly (22–34 s cycles); visible only when `Theme.ambient && Theme.animations && !Theme.software`; uses `MultiEffect` blur.

- [x] **Step 1: Write failing tests** in `tests/test_fx.py` (loads `tests/qml/FxGallery.qml`, which instantiates each component with an `objectName`):

```python
def test_gallery_instantiates_clean(self): self.assert_no_qml_warnings()
def test_toast_stacks_and_expires(self):
    for i in range(6): self.eval_qml(f'Fx.toast("t{i}", "info")')
    self.pump(100); self.assertEqual(self.find("toastHost").property("count"), 4)
    self.pump(3800); self.assertEqual(self.find("toastHost").property("count"), 0)
def test_countup_reaches_value(self):
    self.find("count").setProperty("value", 312); self.pump(1400)
    self.assertEqual(self.find("count").property("text"), "312")
def test_animations_off_kills_decor(self):
    self.bridges["settings"].animationsEnabled = False; self.pump(50)
    self.assertEqual(self.eval_qml("Theme.dur(400)"), 0)
    self.assertFalse(self.find("ambient").property("visible"))
    self.assertFalse(self.find("burstLoader").property("active"))
```

- [x] **Step 2: Run** the test command. Expected: FAIL.
- [x] **Step 3: Implement** the components per the Interfaces block; `ToastHost` exposes `count: int`; `CountUpText` exposes its rendered `text`.
- [x] **Step 4: Run** the test command. Expected: PASS.
- [x] **Step 5: Commit** `feat(gui): reusable motion primitives (button, ripple, toasts, burst, skeleton, count-up, pulse, ambient glow)`.

---

### Task 4: App shell — sidebar, view transitions, Downloads badge, toasts

**Files:**
- Modify: `gui/qml/main.qml`, `gui/qml/components/SideBar.qml`
- Test: `tests/test_shell.py`

**Interfaces:**
- Consumes: `badge.js` (Task 1), `Fx`, `Theme`, fx components (Task 3); existing signals `DownloadBridge.jobStarted(jobId,title,poster,total)`, `chapterComplete(jobId,name,success,msg)`, `downloadFinished(jobId,ok,failed)`, `jobCancelled(jobId)`, `jobError(jobId,msg)`, `libraryJobFinished(url,ok,failed)`, `LibraryBridge.updateCheckFinished(...)`.
- Produces:
  - `SideBar.downloadsCount: int` (from badge reducer, held in `main.qml`); badges scale in/out with spring and do a bump (scale 1.7, rotate −10°, back) whenever their value increases. `SideBar.downloadsAnchor: Item` (the Downloads nav button) for the fly-to effect.
  - Sliding active indicator: one rectangle behind the nav buttons, `y` animated with `SpringAnimation`/`OutBack` to the active button; 3 px accent bar with glow on its left edge.
  - Settings gear rotates 120° on hover.
  - View switching: `StackLayout` replaced by a container where the outgoing view fades/slides left (−40 px, scale .98) and the incoming slides from +40 px, fades and un-blurs (blur only when `!Theme.software`), ~450–550 ms. Views stay instantiated (state must survive switching, as today). `viewStack.currentIndex` semantics and the existing `onLibraryClicked` refresh calls are preserved.
  - Fly-to: `Fx.flyRequested(from, count)` → an accent bubble with the count arcs from `from` (scene coords) to `downloadsAnchor`, ~900 ms, then the badge bumps.
  - Toasts: `downloadFinished` → `"Downloaded N chapters of <title>"` (`ok`; `error` kind with failed count if any); `jobError` → error toast; `updateCheckFinished` → `"Check finished — N series have new chapters"`.

- [x] **Step 1: Write failing tests** in `tests/test_shell.py`:

```python
def test_switch_views_keeps_state(self):
    # set a marker property on BrowseView, switch to Library and back
def test_downloads_badge_from_signals(self):
    d = self.bridges["download"]
    d.jobStarted.emit("j1", "T", "", 3); d.chapterComplete.emit("j1", "c1", True, "")
    self.pump(50); self.assertEqual(self.find("sideBar").property("downloadsCount"), 2)
    d.jobCancelled.emit("j1"); self.pump(50)
    self.assertEqual(self.find("sideBar").property("downloadsCount"), 0)
def test_finished_download_toasts(self):
    d = self.bridges["download"]; d.jobStarted.emit("j2", "Moby Dick", "", 1)
    d.downloadFinished.emit("j2", 1, 0); self.pump(100)
    self.assertEqual(self.find("toastHost").property("count"), 1)
```

- [x] **Step 2: Run** the test command. Expected: FAIL.
- [x] **Step 3: Implement** per the Interfaces block. Give `SideBar` `objectName: "sideBar"`.
- [x] **Step 4: Run** the test command. Expected: PASS; manual check that clicking each tab animates and Library still refreshes on open.
- [x] **Step 5: Commit** `feat(gui): animated shell — sidebar indicator, view transitions, Downloads badge, toasts`.

---

### Task 5: Settings drawer

**Files:**
- Modify: `gui/qml/components/SettingsDrawer.qml`, `gui/qml/main.qml` (wipe overlay host)
- Create: `gui/qml/fx/ThemeWipe.qml`
- Test: `tests/test_settings_ui.py`

**Interfaces:**
- Consumes: `Theme`, `Fx.themeWipeRequested`, `FxButton`, `SettingsBridge.theme/animationsEnabled/ambientGlow`, existing `SettingsBridge.toomicsStatus(level,msg)` and `resetToDefaults()`.
- Produces:
  - Drawer opens with `x` spring (`OutBack`, ~600 ms) from the right; backdrop dims to 45 % and blurs the app behind (MultiEffect, skipped in software); sections fade/slide in from +30 px staggered 80 ms; close button rotates 90° on hover.
  - **Appearance** section (first): three theme cards (mini preview of bg/card/accent/cool, name), selected card has accent border + glow ring, lift on hover; toggles "Animations" and "Drifting background glow".
  - `ThemeWipe` (in `main.qml`, `objectName: "themeWipe"`, exposes `active: bool`): on `Fx.themeWipeRequested(name, origin)` → `grabToImage` of the window content → show the image on top → set `SettingsBridge.theme = name` → reveal by growing an inverted circular `MultiEffect` mask from `origin` to the farthest corner (~750 ms) → hide. A new request while active finishes the current one instantly and starts over (one overlay at most). Software backend or animations off: crossfade the image out (~300 ms; 0 when off).
  - Toggle switches: knob springs, stretches while pressed.
  - Worker sliders show a value bubble above the handle that scales up while dragging (keep rows tall enough that the bubble doesn't overlap the row above).
  - Toomics Login: button morphs to a circular spinner while waiting; on `toomicsStatus` `ok` → green message slides in + `Fx.toast("Toomics session saved","ok")`; `err` → section shakes (±7 px, 450 ms) and the message is red.
  - "Hold to reset to defaults" replaces the click button: fill grows left→right over 1400 ms while pressed; release early → fill drains back; completion → `SettingsBridge.resetToDefaults()` + toast.
  - Existing settings controls keep working (format, keep images, logs, path, workers, toomics fields).

- [x] **Step 1: Write failing tests** in `tests/test_settings_ui.py`:

```python
def test_theme_card_switches_theme(self):  # invoke the card's click handler for "neon"; pump 900ms; theme == "neon", themeWipe.active False
def test_rapid_theme_switch_leaves_one_overlay(self):
    for n in ("neon", "ember", "ink"): self.eval_qml(f'Fx.themeWipeRequested("{n}", Qt.point(10,10))')
    self.pump(1200)
    self.assertEqual(self.bridges["settings"].theme, "ink")
    self.assertFalse(self.find("themeWipe").property("active"))
def test_hold_reset_requires_full_hold(self):  # press 500ms + release → no reset; press 1500ms → resetToDefaults called (spy via settingsChanged + a changed key)
```

and in the software-backend class: `test_theme_switch_software_backend` (switch, pump, theme changed, no warnings).

- [x] **Step 2: Run** the test command. Expected: FAIL.
- [x] **Step 3: Implement** per the Interfaces block.
- [x] **Step 4: Run** the test command. Expected: PASS; manual check of the wipe in the real app on all three themes.
- [x] **Step 5: Commit** `feat(gui): animated settings drawer, theme picker with colour wipe, hold-to-reset`.

---

### Task 6: Browse — URL box + manga card

**Files:**
- Modify: `gui/qml/components/UrlInput.qml`, `gui/qml/components/MangaCard.qml`, `gui/qml/views/BrowseView.qml`
- Test: `tests/test_browse_top.py`

**Interfaces:**
- Consumes: `MangaBridge.classifyUrl(url) -> str`, `MangaBridge.fetchManga(url)`, existing MangaBridge fetch signals (fetch started / manga loaded / error — reuse whatever `BrowseView`/`main.qml` already connect), `Skeleton`, `CountUpText`, `Theme`.
- Produces:
  - URL box: focus → accent border + 4 px glow ring; recognised URL → success border/glow, a ✓ disc pops in (spring), the matching site chip scales 1.12 and glows success while the others dim to 35 %, Fetch button pulses (glow ring loop) until clicked. Enter with an unrecognised URL → box shakes; text of ≥12 chars that doesn't start with `http` → ✕ disc in error colour.
  - `DropArea` on the URL box: dragging text/URL over → accent dashed glow + scale 1.02; drop → fills the field and runs classification (no auto-fetch).
  - Fetching: `MangaCard` shows a skeleton (cover block + 5 lines) while the fetch is in flight.
  - Loaded: cover starts blurred (MultiEffect blur 1→0, skip in software) and scale .92→1 with spring, then one light sweep across it; title letters rise in 40 ms apart (Repeater of characters); tags pop in staggered 70 ms after 600 ms; numeric stats use `CountUpText`; description collapsed to 2 lines with "Read more ▼ / Show less ▲" animating height.

- [x] **Step 1: Write failing tests:** `test_match_state_on_known_url` (set field text to `https://toonily.com/serie/x/` → url box `matched` property true, fetch button `ready` true); `test_shake_on_unknown_enter` (unknown text + Enter → `shaking` true then false within 600 ms, no fetch call — spy `MangaBridge.fetchManga` via a counting wrapper); `test_skeleton_while_fetching` (emit the fetch-started signal → `mangaCard.loading` true; emit loaded → false).
- [x] **Step 2: Run** the test command. Expected: FAIL.
- [x] **Step 3: Implement**; expose `matched`, `ready`, `shaking`, `loading` as properties with objectNames `urlInput`, `fetchButton`, `mangaCard`.
- [x] **Step 4: Run** the test command. Expected: PASS; manual fetch of a real toonily URL looks right.
- [x] **Step 5: Commit** `feat(gui): animated URL input and manga card reveal`.

---

### Task 7: Browse — chapter list + download controls

**Files:**
- Modify: `gui/qml/components/ChapterList.qml`, `gui/qml/components/ChapterDelegate.qml`, `gui/qml/components/DownloadControls.qml`, `gui/qml/views/BrowseView.qml`
- Test: `tests/test_browse_chapters.py`

**Interfaces:**
- Consumes: `chapters.js` (`matches`, `rangeIndices`), `motion.js` (`staggerDelay`), `Fx.flyRequested`, `SettingsBridge.outputFormat`, existing `ChapterList.getSelectedChapters()` / `applyFilter(scanlator)` / `getScanlators()`.
- Produces:
  - Text filter field in the chapter header (widens 150→210 px on focus with spring): rows not matching `matches()` collapse (height + opacity animate to 0) — combined with the existing scanlator filter (a row is visible only if it passes both).
  - Rows slide in from −16 px using `staggerDelay(index)`; hover tint; selected rows get an accent→transparent gradient; checkbox fills with spring and draws its tick (QtQuick.Shapes path with animated dash/trim).
  - Plain click toggles one row and sets the anchor; **shift-click** applies the clicked row's new state to `rangeIndices(anchor, index)` over **visible** rows, rippling 25 ms apart with a small right-nudge "wave". "Select All"/"None" act on visible rows only, cascading.
  - Selected counter "N / M selected" ticks (bounce) on change.
  - Format selector (CBZ / PDF / Images) with a spring-sliding highlight pill, bound two-way to `SettingsBridge.outputFormat` (`cbz|pdf|images`).
  - Download button: `FxButton` with a periodic light sheen; hint line "N chapters as CBZ" / "Select some chapters first"; with 0 selected the button shakes instead of dispatching; otherwise it dispatches exactly as today, then emits `Fx.flyRequested(buttonCentreInScene, N)`.

- [x] **Step 1: Write failing tests:** `test_filter_hides_rows` (load 10 chapters via the list's model API, set filter "1" → visible count = rows whose number/title contains "1"); `test_select_all_visible_only` (filter then Select All → `getSelectedChapters()` length == visible count); `test_shift_click_range` (click row 2, shift-click row 5 → 4 selected); `test_format_selector_writes_setting` (choose PDF → `SettingsBridge.outputFormat == "pdf"`; set setting to "images" → selector index 2); `test_download_with_none_selected_does_not_dispatch` (spy `startDownload` call count stays 0).
- [x] **Step 2: Run** the test command. Expected: FAIL.
- [x] **Step 3: Implement** per the Interfaces block.
- [x] **Step 4: Run** the test command. Expected: PASS; manual: real series with 100+ chapters scrolls smoothly.
- [x] **Step 5: Commit** `feat(gui): animated chapter list with filter and range select; format selector; fly-to download`.

---

### Task 8: Library

**Files:**
- Modify: `gui/qml/views/LibraryView.qml`, `gui/qml/components/LibraryCard.qml`
- Test: `tests/test_library_ui.py`

**Interfaces:**
- Consumes: `staggerDelay`, `ParticleBurst`, `CountUpText`, `PulseRings`, `Fx.toast`, existing `LibraryBridge.checkEntry/downloadRecommended/entryCheckFinished`, `DownloadBridge.libraryJobFinished`, `chapterComplete` (for ring progress: count completed chapters for jobs whose title matches the card being updated — or simply indeterminate spin if mapping isn't available; builder's call).
- Produces:
  - Cards rise in (+28 px, scale .94→1) with `staggerDelay(index)` whenever the view is opened or the filter/sort changes.
  - Hover: 3D tilt toward the cursor (±6° each axis, `Rotation` with `axis`), lift shadow + accent glow outline, light sweep across the cover. Tilt and sweep only when animations on.
  - ⓘ button in the cover's top-right: flips the cover (`Flipable`, 800 ms OutBack) to a back face with chapter count, site, status, last downloaded; click again or mouse leaving the card flips back. The select checkbox stays top-left.
  - Status pill click: menu scales open from its top-left (spring), items slide in staggered 40 ms.
  - "Check for new": button narrows into a circular spinner while `checkingUrls[url]`; result "✦ N new" pops in with `CountUpText`; "Download N new" → card shows a progress ring and "Downloading N new chapters…" (existing status text) → on `libraryJobFinished` a drawn checkmark + "Downloaded N new chapters" (existing message logic from the 2026-10-24 fix), `ParticleBurst.burst()`, toast.
  - "✦ Check for Updates" toolbar button uses `PulseRings` while the bulk check runs.

- [x] **Step 1: Write failing tests:** `test_library_loads_260_entries_clean` (point `LibraryBridge` at a fixture `library.json` with 260 generated entries; open Library; no warnings; all cards visible after `staggerDelay(259)+800` ms); `test_flip_and_unflip` (click ⓘ on card 0 → `flipped` true; send hover-exit → false); `test_job_finished_shows_done` (emit `libraryJobFinished(url, 3, 0)` → card status text == "Downloaded 3 new chapters").
- [x] **Step 2: Run** the test command. Expected: FAIL.
- [x] **Step 3: Implement** per the Interfaces block (`LibraryCard` exposes `flipped`).
- [x] **Step 4: Run** the test command. Expected: PASS; manual: scroll the real library — no stutter.
- [x] **Step 5: Commit** `feat(gui): animated library — staggered cards, tilt, flip, check/download morphs`.

---

### Task 9: Updates + Downloads views

**Files:**
- Modify: `gui/qml/views/UpdatesView.qml`, `gui/qml/views/DownloadsView.qml`, `gui/qml/components/ProgressPanel.qml`, `gui/qml/components/JobProgressCard.qml`
- Test: `tests/test_updates_downloads_ui.py`

**Interfaces:**
- Consumes: `staggerDelay`, `CountUpText`, `ParticleBurst`, `Skeleton`, existing Updates/Downloads signals and models.
- Produces:
  - Updates: series rows rise in staggered; chapter chips pop (scale .8→1.15→1) when toggled on, glow when selected; the "Download N chapters" button's N uses `CountUpText` (from the previous value); skeleton rows while a check is running and the list is empty.
  - Downloads: job cards rise in; progress bar fill = flowing accent2→accent→highlight gradient + moving shimmer + glow, width animated; chapter rows slide in from −8 px and their status colour animates to success on completion; on `downloadFinished` the card flashes a glow ring once and `burst()`s; "Preparing…" state uses `PulseRings` small.

- [x] **Step 1: Write failing tests:** `test_updates_counter_tracks_selection` (load a pending fixture; untoggle one chip → button count value decreases by 1); `test_job_card_finishes` (emit `jobStarted` + `chapterProgress` + `downloadFinished` → card `finished` true, no warnings).
- [x] **Step 2: Run** the test command. Expected: FAIL.
- [x] **Step 3: Implement** per the Interfaces block.
- [x] **Step 4: Run** the test command. Expected: PASS.
- [x] **Step 5: Commit** `feat(gui): animated updates review and download job cards`.

---

### Task 10: Final pass — animations off, `--cpu`, perf, docs

**Files:**
- Modify: any QML file where the pass finds issues; `CLAUDE.md` (changelog entry + "Conventions" note on `Style`/`Theme`/`Fx` and the QJSEngine tests; repo-layout lines for `gui/app.py`, `gui/qml/Style`, `gui/qml/fx`, `gui/qml/logic`, `tests/`); `.gitignore` (add `.superpowers/`)
- Test: `tests/test_final.py`

- [x] **Step 1: Write failing tests:** `test_everything_instant_when_animations_off` (animations off; open drawer → drawer `x` at final value after one `pump(16)`; switch views → incoming view opacity 1 after `pump(16)`); `test_cpu_full_walkthrough` (software backend: open each view, open drawer, switch theme, start/finish a fake job via signals — zero QML warnings).
- [x] **Step 2: Run** the test command. Expected: FAIL where gaps remain.
- [x] **Step 3: Fix** the gaps. Run the real app on all three themes, with animations on and off, and with `--cpu`; check text contrast and that nothing waits on an animation.
- [x] **Step 4: Run** the full test command. Expected: all PASS.
- [x] **Step 5: Commit** `chore(gui): animations-off + software-rendering pass; docs`.
