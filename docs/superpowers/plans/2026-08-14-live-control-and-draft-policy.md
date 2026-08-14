# Live Control and Draft Policy Implementation Plan

> **For agentic workers:** implement inline in this session; the user explicitly requested direct iteration instead of delegated/TDD-heavy execution.

**Goal:** Start Draft Showdown from the MEmu launcher, expose live automation analysis in the GUI, and replace random draft taps with deterministic explainable decisions.

**Architecture:** A small Android app launcher owns package foregrounding. `BattleRunner` publishes bounded automation telemetry through the existing event bus. Draft perception produces structured OCR candidates and a pure policy scores them using effect value, continuity, diversity, and confidence; the runner only taps the selected available slot.

**Tech Stack:** Python 3.12, adbutils, RapidOCR, OpenCV, CustomTkinter, pytest/replay fixtures.

---

### Task 1: Android game foregrounding

**Files:** create `src/automation/game_launcher.py`; modify automation and observer assembly; cover connected, launcher, timeout and cancellation paths.

- [ ] Connect to the explicit serial, inspect the foreground package, call `app_start` only when needed, and wait boundedly until the game package is foreground.
- [ ] Publish each startup phase without sending gameplay taps.

### Task 2: Structured draft perception and policy

**Files:** create `src/vision/draft_reader.py` and `src/strategy/draft_policy.py`; modify `src/vision/context_analyzer.py` and `src/automation/battle_runner.py`.

- [ ] OCR only visually available card regions and emit normalized unit/effect/magnitude/confidence facts.
- [ ] Score every candidate deterministically; reward quantity/multipliers, useful continuity and roster diversity; retain an explicit fallback when text is unreadable.
- [ ] Record the chosen candidate and all score reasons in `actions.jsonl` and runtime telemetry.

### Task 3: GUI automation telemetry

**Files:** modify `src/gui/app.py`, `src/gui/presenter.py`, `src/core/events.py` and GUI tests.

- [ ] Add a separately confirmed one-battle control, mutually exclusive with observation.
- [ ] Display game startup, FSM phase, pending/resolved action, candidate scores, selected card and safety state.
- [ ] Keep paid offers, ads, boosts and spending disabled.

### Task 4: Verification and handoff

- [ ] Run focused replay/GUI/device tests, then the full suite, compileall and `git diff --check`.
- [ ] Update README/handoff and publish only after fresh verification.
