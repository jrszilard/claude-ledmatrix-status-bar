# Triple-Bonnet Provider Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt the LED display from a daisy-chained 96×16 strip to three parallel-chain panels (vertical 32×48 stack) on the Adafruit triple bonnet, replacing the single-metric cycler with a provider-page dashboard driven by an extensible, shape-based registry.

**Architecture:** A new `src/dashboard.py` rendering engine draws one provider's page at a time on a 32×48 stack of three 32×16 tiles. A `registry.py` declares providers and their metrics by *shape* (`quota`/`capped`/`spend`/`balance`); the renderer dispatches on shape, so adding a provider is a data entry. A two-level `Cycler` advances the outer provider page and each page's inner sub-rotation. Geometry is derived once from config via `layout.configure()`. The old `renderer.py` stays untouched (and tested) until a final cleanup task swaps `main.py` over and deletes it.

**Tech Stack:** Python 3, `rpi-rgb-led-matrix` (GPIO, Pi-only — imported only inside `main.run_led_mode`), `pytest` with `unittest.mock.MagicMock` canvases (no hardware in tests), PyYAML config.

---

## Design Notes (read once before starting)

- **rgbmatrix is never imported in tests.** `layout`, `registry`, and `dashboard` are pure Python that take a `graphics`/`canvas`/`fonts` object as arguments. Tests pass `MagicMock`s. Only `main.run_led_mode` imports `rgbmatrix`, and no test imports `run_led_mode`.
- **Test doubles (established pattern, mirror exactly):**
  ```python
  canvas = MagicMock()                       # canvas.SetPixel auto-records calls
  gfx = MagicMock()
  gfx.Color = lambda r, g, b: (r, g, b)      # Color() returns the tuple
  gfx.DrawText = MagicMock(return_value=0)   # signature: DrawText(canvas, font, x, y, color, text)
  fonts = {"main": MagicMock(), "small": MagicMock()}
  # To read drawn text:   [c.args[5] for c in gfx.DrawText.call_args_list]
  # To read drawn color:  [c.args[4] for c in gfx.DrawText.call_args_list]
  ```
- **`layout.configure()` mutates module globals.** Test files that call it MUST reset geometry afterward. Each new test file gets an `autouse` fixture that restores the hardware defaults (`rows=16, cols=32, parallel=3`).
- **State dot-paths:** metrics address the shared `state` dict by dotted key, e.g. `subscription.session_pct`, `api.total_spend`. `registry.resolve(key, state)` walks them, returning `None` if any segment is missing.
- **Deterministic time:** every cycling/countdown function accepts a `now` argument (defaulting to `time.time()`), so tests inject time instead of sleeping.
- **Commit discipline:** each task ends with a commit on the existing branch `feat/triple-bonnet-provider-dashboard`.

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/layout.py` | + tile geometry constants & `configure()` (additive; old constants stay until Task 8) | 1 |
| `tests/test_geometry.py` | *(new)* tile-geometry unit tests | 1 |
| `src/registry.py` | *(new)* `Metric`/`TilesPage`/`HeroPage`/`Provider` dataclasses, `PROVIDERS`, `resolve()`, `enabled_providers()` | 2 |
| `tests/test_registry.py` | *(new)* registry + resolve tests | 2 |
| `src/dashboard.py` | *(new)* value formatting, `draw_tile` + shape rendering | 3 |
| `tests/test_dashboard.py` | *(new)* dashboard tests (grown across tasks 3–6) | 3–6 |
| `src/dashboard.py` | + `Cycler`, `format_countdown`, countdown alternation | 4 |
| `src/dashboard.py` | + `draw_accent`, `draw_hero`, `draw_page` | 5 |
| `src/dashboard.py` | + `Dashboard` (top-level update/draw) | 6 |
| `src/config.py` | + `resolve_geometry(display)` pure helper | 7 |
| `tests/test_config.py` | + geometry-resolution tests | 7 |
| `src/main.py` | parallel options, `layout.configure()`, load 4×6 font, render via `Dashboard` | 7 |
| `config.example.yaml` | `chain_length`/`parallel`/`show_countdown`/`page_dwell_seconds` | 7 |
| `src/renderer.py` | *(deleted)* | 8 |
| `tests/test_renderer.py` | *(deleted)* | 8 |
| `tests/test_layout.py` | trimmed to surviving helpers (formatters, `scale_color`, `compute_bar_width`) | 8 |
| `README.md` / `install.sh` | note the 4×6 font requirement | 8 |

---

### Task 1: Tile geometry + `configure()` (additive)

**Files:**
- Modify: `src/layout.py` (append a new section; do not remove existing constants yet)
- Test: `tests/test_geometry.py` *(create)*

- [ ] **Step 1: Write the failing test**

Create `tests/test_geometry.py`:
```python
import pytest

from src import layout


@pytest.fixture(autouse=True)
def restore_geometry():
    """Reset tile geometry to hardware defaults after each test."""
    yield
    layout.configure(rows=16, cols=32, parallel=3)


def test_default_tile_geometry():
    assert layout.TILE_WIDTH == 32
    assert layout.TILE_HEIGHT == 16
    assert layout.NUM_TILES == 3
    assert layout.TILE_Y_OFFSETS == [0, 16, 32]


def test_within_tile_element_positions():
    # text baseline and bar sit inside a 16px-tall tile
    assert 0 < layout.TILE_TEXT_Y < layout.TILE_HEIGHT
    assert layout.TILE_BAR_Y + layout.TILE_BAR_H <= layout.TILE_HEIGHT


def test_configure_derives_offsets_for_three_panels():
    layout.configure(rows=16, cols=32, parallel=3)
    assert layout.TILE_WIDTH == 32
    assert layout.TILE_HEIGHT == 16
    assert layout.NUM_TILES == 3
    assert layout.TILE_Y_OFFSETS == [0, 16, 32]


def test_configure_two_panels():
    layout.configure(rows=16, cols=32, parallel=2)
    assert layout.NUM_TILES == 2
    assert layout.TILE_Y_OFFSETS == [0, 16]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_geometry.py -v`
Expected: FAIL with `AttributeError: module 'src.layout' has no attribute 'TILE_WIDTH'`

- [ ] **Step 3: Add the geometry section to `src/layout.py`**

Append at the end of `src/layout.py` (after `scale_color`):
```python
# --- Vertical tile geometry (triple-bonnet parallel stack) -------------------
# Three stacked 32x16 tiles -> a 32x48 framebuffer. Defaults match the current
# hardware so tests and dry-run work without calling configure().
TILE_WIDTH = 32
TILE_HEIGHT = 16
NUM_TILES = 3
TILE_Y_OFFSETS = [0, 16, 32]

# Element positions WITHIN a single tile, relative to the tile's top row.
TILE_TEXT_Y = 8   # text baseline inside the tile
TILE_BAR_Y = 11   # bar top inside the tile
TILE_BAR_H = 3    # bar thickness
TILE_BAR_X = 1    # left inset for text and bar (leaves col 0 for the accent)


def configure(rows: int, cols: int, parallel: int) -> None:
    """Derive tile geometry from hardware config. Call once at startup.

    rows/cols are a single panel's dimensions; parallel is the number of
    stacked panels (parallel chains on the bonnet).
    """
    global TILE_WIDTH, TILE_HEIGHT, NUM_TILES, TILE_Y_OFFSETS
    TILE_WIDTH = cols
    TILE_HEIGHT = rows
    NUM_TILES = parallel
    TILE_Y_OFFSETS = [i * rows for i in range(parallel)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_geometry.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Confirm nothing else broke**

Run: `pytest -q`
Expected: PASS — the old `tests/test_layout.py` still passes because the original constants are untouched.

- [ ] **Step 6: Commit**

```bash
git add src/layout.py tests/test_geometry.py
git commit -m "feat(layout): add vertical tile geometry and configure()"
```

---

### Task 2: Provider/metric registry

**Files:**
- Create: `src/registry.py`
- Test: `tests/test_registry.py` *(create)*

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry.py`:
```python
from src import registry


def test_resolve_nested():
    state = {"api": {"total_spend": 12.47}}
    assert registry.resolve("api.total_spend", state) == 12.47


def test_resolve_missing_returns_none():
    assert registry.resolve("api.nope", {"api": {}}) is None
    assert registry.resolve("x.y.z", {}) is None
    assert registry.resolve("a.b", {"a": 5}) is None  # non-dict mid-path


def test_only_anthropic_enabled_by_default():
    assert [p.id for p in registry.enabled_providers()] == ["anthropic"]


def test_claude_page_two_fixed_three_rotating():
    claude = next(p for p in registry.PROVIDERS if p.id == "anthropic")
    assert isinstance(claude.page, registry.TilesPage)
    assert [m.label for m in claude.page.fixed] == ["SES", "WK"]
    assert [m.label for m in claude.page.rotating] == ["SNT", "EXT", "API"]


def test_balance_providers_use_hero_pages():
    for pid in ("opencode", "xai"):
        p = next(pp for pp in registry.PROVIDERS if pp.id == pid)
        assert isinstance(p.page, registry.HeroPage)
        assert p.page.metric.shape == "balance"


def test_every_metric_has_valid_shape():
    valid = {"quota", "capped", "spend", "balance"}
    for p in registry.PROVIDERS:
        metrics = (
            p.page.fixed + p.page.rotating
            if isinstance(p.page, registry.TilesPage)
            else [p.page.metric]
        )
        for m in metrics:
            assert m.shape in valid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.registry'`

- [ ] **Step 3: Create `src/registry.py`**

```python
from dataclasses import dataclass, field
from typing import Optional

from src import layout

# Provider accent colors (R, G, B)
COLOR_CLAUDE = (255, 106, 85)
COLOR_OPENAI = (25, 195, 154)
COLOR_OPENCODE = (217, 164, 65)
COLOR_XAI = (138, 147, 163)

_VALID_SHAPES = {"quota", "capped", "spend", "balance"}


@dataclass
class Metric:
    label: str            # short tile label, e.g. "SES"
    shape: str            # one of _VALID_SHAPES — picks the renderer
    key: str              # dot-path into state, e.g. "subscription.session_pct"
    color: tuple          # RGB
    limit_key: Optional[str] = None   # capped: dot-path to the dollar limit
    reset_key: Optional[str] = None   # quota: dot-path to reset ISO timestamp
    sub_key: Optional[str] = None     # balance: dot-path to a sub-line string


@dataclass
class TilesPage:
    fixed: list                                    # list[Metric], one per fixed tile
    rotating: list = field(default_factory=list)   # list[Metric] cycled in the last tile


@dataclass
class HeroPage:
    metric: Metric


@dataclass
class Provider:
    id: str
    label: str            # full name for hero pages, e.g. "OPENCODE"
    tag: str              # 2-char abbreviation, e.g. "OC"
    color: tuple          # accent RGB
    page: object          # TilesPage | HeroPage
    enabled: bool = False


def resolve(key: str, state: dict):
    """Resolve a dot-path like 'api.total_spend' against a nested dict."""
    cur = state
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


PROVIDERS = [
    Provider(
        id="anthropic", label="CLAUDE", tag="CL", color=COLOR_CLAUDE, enabled=True,
        page=TilesPage(
            fixed=[
                Metric("SES", "quota", "subscription.session_pct", layout.COLOR_SESSION,
                       reset_key="subscription.session_reset_utc"),
                Metric("WK", "quota", "subscription.week_all_pct", layout.COLOR_WEEK_ALL,
                       reset_key="subscription.week_all_reset_utc"),
            ],
            rotating=[
                Metric("SNT", "quota", "subscription.week_sonnet_pct", layout.COLOR_WEEK_SONNET,
                       reset_key="subscription.week_sonnet_reset_utc"),
                Metric("EXT", "capped", "subscription.extra_spent", layout.COLOR_EXTRA,
                       limit_key="subscription.extra_limit"),
                Metric("API", "spend", "api.total_spend", layout.COLOR_API),
            ],
        ),
    ),
    Provider(
        id="openai", label="CHATGPT", tag="OA", color=COLOR_OPENAI, enabled=False,
        page=TilesPage(fixed=[
            Metric("GPT", "quota", "openai.quota_pct", COLOR_OPENAI,
                   reset_key="openai.quota_reset_utc"),
        ]),
    ),
    Provider(
        id="opencode", label="OPENCODE", tag="OC", color=COLOR_OPENCODE, enabled=False,
        page=HeroPage(metric=Metric("OPC", "balance", "opencode.spent_period", COLOR_OPENCODE,
                                    sub_key="opencode.autoreload")),
    ),
    Provider(
        id="xai", label="XAI", tag="XA", color=COLOR_XAI, enabled=False,
        page=HeroPage(metric=Metric("XAI", "balance", "xai.spent_period", COLOR_XAI,
                                    sub_key="xai.autoreload")),
    ),
]


def enabled_providers() -> list:
    """Providers whose pages should be shown (Phase 1: the enabled flag)."""
    return [p for p in PROVIDERS if p.enabled]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_registry.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/registry.py tests/test_registry.py
git commit -m "feat(registry): add shape-based provider/metric registry"
```

---

### Task 3: Value formatting + `draw_tile` shape rendering

**Files:**
- Create: `src/dashboard.py`
- Test: `tests/test_dashboard.py` *(create)*

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard.py`:
```python
import pytest
from unittest.mock import MagicMock

from src import layout, registry, dashboard


@pytest.fixture(autouse=True)
def restore_geometry():
    yield
    layout.configure(rows=16, cols=32, parallel=3)


@pytest.fixture
def gfx():
    g = MagicMock()
    g.Color = lambda r, g_, b: (r, g_, b)
    g.DrawText = MagicMock(return_value=0)
    return g


@pytest.fixture
def canvas():
    return MagicMock()


def texts(gfx):
    return [c.args[5] for c in gfx.DrawText.call_args_list]


STATE = {
    "subscription": {"session_pct": 45, "week_all_pct": 62, "week_sonnet_pct": 38,
                     "extra_spent": 12.0, "extra_limit": 50.0},
    "api": {"total_spend": 4.20, "total_tokens": 1_200_000},
    "opencode": {"spent_period": 18.40, "autoreload": "auto @ $5"},
}

SES = registry.Metric("SES", "quota", "subscription.session_pct", layout.COLOR_SESSION)
EXT = registry.Metric("EXT", "capped", "subscription.extra_spent", layout.COLOR_EXTRA,
                      limit_key="subscription.extra_limit")
API = registry.Metric("API", "spend", "api.total_spend", layout.COLOR_API)


def test_format_value_quota():
    assert dashboard.format_value(SES, STATE) == "45%"


def test_format_value_capped_shows_spent_dollars():
    assert dashboard.format_value(EXT, STATE) == "$12"


def test_format_value_spend():
    assert dashboard.format_value(API, STATE) == "$4.20"


def test_metric_pct_quota_is_the_percentage():
    assert dashboard.metric_pct(SES, STATE) == 45.0


def test_metric_pct_capped_is_spent_over_limit():
    assert dashboard.metric_pct(EXT, STATE) == pytest.approx(24.0)


def test_metric_pct_spend_has_no_bar():
    assert dashboard.metric_pct(API, STATE) is None


def test_draw_tile_draws_label_and_value(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 0, SES, STATE, now=0)
    assert "SES" in texts(gfx)
    assert "45%" in texts(gfx)


def test_draw_tile_value_is_right_aligned(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 0, SES, STATE, now=0)
    # value "45%" is 3 chars * CHAR_WIDTH(5) = 15px -> x = 32 - 15 = 17
    value_call = next(c for c in gfx.DrawText.call_args_list if c.args[5] == "45%")
    assert value_call.args[2] == 17


def test_draw_tile_quota_draws_bar(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 0, SES, STATE, now=0)
    assert canvas.SetPixel.called


def test_draw_tile_spend_draws_no_bar(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 0, API, STATE, now=0)
    assert not canvas.SetPixel.called


def test_draw_tile_applies_vertical_offset(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 16, SES, STATE, now=0)
    # label baseline = y_offset + TILE_TEXT_Y = 16 + 8 = 24
    label_call = next(c for c in gfx.DrawText.call_args_list if c.args[5] == "SES")
    assert label_call.args[3] == 24
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.dashboard'`

- [ ] **Step 3: Create `src/dashboard.py`**

```python
import time

from src import layout, registry


def format_value(metric, state) -> str:
    """Short, tile-width-friendly value string for a metric."""
    raw = registry.resolve(metric.key, state)
    if metric.shape == "quota":
        return f"{int(raw or 0)}%"
    if metric.shape == "capped":
        return f"${float(raw or 0):.0f}"
    if metric.shape in ("spend", "balance"):
        return layout.format_dollars(float(raw or 0))
    return ""


def metric_pct(metric, state):
    """Bar fill percentage for a metric, or None if the shape has no bar."""
    if metric.shape == "quota":
        return float(registry.resolve(metric.key, state) or 0)
    if metric.shape == "capped":
        spent = float(registry.resolve(metric.key, state) or 0)
        limit = float(registry.resolve(metric.limit_key, state) or 0)
        return (spent / limit * 100) if limit > 0 else 0.0
    return None  # spend / balance: no in-tile bar


def _draw_bar(canvas, x, y, width, height, percentage, fg_color, bg_color):
    filled = layout.compute_bar_width(percentage, width)
    for row in range(height):
        for col in range(width):
            color = fg_color if col < filled else bg_color
            canvas.SetPixel(x + col, y + row, *color)


def draw_tile(canvas, gfx, font, y_offset, metric, state, brightness=1.0, now=None):
    """Draw one metric in a 32x16 tile at the given vertical offset.

    Justified layout: label hugs the left, value hugs the right, bar (if any) below.
    """
    color = layout.scale_color(metric.color, brightness)
    c = gfx.Color(*color)

    value = format_value(metric, state)
    text_y = y_offset + layout.TILE_TEXT_Y

    # Label left, value right-aligned.
    gfx.DrawText(canvas, font, layout.TILE_BAR_X, text_y, c, metric.label)
    value_x = max(layout.TILE_BAR_X, layout.TILE_WIDTH - len(value) * layout.CHAR_WIDTH)
    gfx.DrawText(canvas, font, value_x, text_y, c, value)

    pct = metric_pct(metric, state)
    if pct is not None:
        bg = layout.scale_color(layout.COLOR_BAR_BG, brightness)
        bar_w = layout.TILE_WIDTH - 2 * layout.TILE_BAR_X
        _draw_bar(canvas, layout.TILE_BAR_X, y_offset + layout.TILE_BAR_Y,
                  bar_w, layout.TILE_BAR_H, pct, color, bg)
```

(`now` is accepted now for signature stability; Task 4 uses it for countdown alternation.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add src/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): value formatting and justified tile rendering"
```

---

### Task 4: `Cycler` + countdown alternation

**Files:**
- Modify: `src/dashboard.py`
- Test: `tests/test_dashboard.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard.py`:
```python
def test_cycler_single_item_never_advances():
    cy = dashboard.Cycler(total=1, cycle_seconds=1, fade_frames=2)
    cy.update(now=1000)
    cy.update(now=2000)
    assert cy.current == 0
    assert cy.brightness() == 1.0


def test_cycler_enters_fade_after_cycle_seconds():
    cy = dashboard.Cycler(total=3, cycle_seconds=4, fade_frames=2)
    cy.last_cycle_time = 100.0
    cy.update(now=105.0)            # 5s elapsed > 4s -> start fade
    assert cy.fade_progress is not None


def test_cycler_advances_through_fade():
    cy = dashboard.Cycler(total=3, cycle_seconds=4, fade_frames=2)
    cy.last_cycle_time = 100.0
    cy.update(now=105.0)           # start fade
    for _ in range(10):            # pump frames to finish the fade
        cy.update(now=105.0)
    assert cy.current == 1


def test_cycler_brightness_dips_at_midpoint():
    cy = dashboard.Cycler(total=2, cycle_seconds=1, fade_frames=10)
    cy.fade_progress = 0.5
    assert cy.brightness() == pytest.approx(0.0)
    cy.fade_progress = 0.0
    assert cy.brightness() == pytest.approx(1.0)


def test_format_countdown_hours():
    # 2.5h in the future from a fixed reference
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=30)).isoformat()
    assert dashboard.format_countdown(future).endswith("m")


def test_tile_value_alternates_to_countdown():
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    state = {"subscription": {"session_pct": 45, "session_reset_utc": future}}
    m = registry.Metric("SES", "quota", "subscription.session_pct", layout.COLOR_SESSION,
                        reset_key="subscription.session_reset_utc")
    # phase 0..5 shows the percentage, 5..7 shows the countdown
    assert dashboard.tile_value(m, state, now=0, show_countdown=True) == "45%"
    assert dashboard.tile_value(m, state, now=6, show_countdown=True) != "45%"


def test_tile_value_no_countdown_when_disabled():
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    state = {"subscription": {"session_pct": 45, "session_reset_utc": future}}
    m = registry.Metric("SES", "quota", "subscription.session_pct", layout.COLOR_SESSION,
                        reset_key="subscription.session_reset_utc")
    assert dashboard.tile_value(m, state, now=6, show_countdown=False) == "45%"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py -k "cycler or countdown or tile_value" -v`
Expected: FAIL with `AttributeError: module 'src.dashboard' has no attribute 'Cycler'`

- [ ] **Step 3: Add `Cycler`, `format_countdown`, `tile_value` to `src/dashboard.py`**

Add these imports at the top of `src/dashboard.py` (replace the existing `import time` line):
```python
import time
from datetime import datetime, timezone
```

Add to `src/dashboard.py`:
```python
COUNTDOWN_PHASE_SECONDS = 7   # ~5s value, then ~2s countdown


class Cycler:
    """Advance through `total` items on a timer, with a fade across each swap.

    Ported from the original DisplayCycler. update(now) is frame-driven; pass an
    explicit `now` in tests for determinism.
    """

    def __init__(self, total, cycle_seconds=4, fade_frames=15):
        self.total = max(1, total)
        self.cycle_seconds = cycle_seconds
        self.fade_frames = fade_frames
        self.current = 0
        self.last_cycle_time = time.time()
        self.fade_progress = None
        self._fade_frame = 0
        self._pre = 0

    def update(self, now=None):
        now = time.time() if now is None else now
        if self.total <= 1:
            return
        if self.fade_progress is not None:
            self._fade_frame += 1
            self.fade_progress = self._fade_frame / (self.fade_frames * 2)
            if self.fade_progress >= 0.5 and self.current == self._pre:
                self.current = (self.current + 1) % self.total
            if self.fade_progress >= 1.0:
                self.fade_progress = None
                self._fade_frame = 0
                self.last_cycle_time = now
        elif now - self.last_cycle_time >= self.cycle_seconds:
            self.fade_progress = 0.0
            self._fade_frame = 0
            self._pre = self.current

    def brightness(self) -> float:
        if self.fade_progress is None:
            return 1.0
        p = self.fade_progress
        return 1.0 - (p * 2) if p <= 0.5 else (p - 0.5) * 2


def format_countdown(reset_utc) -> str:
    """UTC ISO timestamp -> compact countdown like '2h30m' or '3d5h'. '' if past/invalid."""
    if not reset_utc:
        return ""
    try:
        reset_dt = datetime.fromisoformat(reset_utc)
        delta = reset_dt - datetime.now(timezone.utc)
        total = int(delta.total_seconds())
        if total <= 0:
            return ""
        days, hours, minutes = total // 86400, (total % 86400) // 3600, (total % 3600) // 60
        if days > 0:
            return f"{days}d{hours}h"
        if hours > 0:
            return f"{hours}h{minutes:02d}m"
        return f"{minutes}m"
    except (ValueError, TypeError):
        return ""


def tile_value(metric, state, now=None, show_countdown=True) -> str:
    """The value string for a tile, alternating quota%/countdown over time."""
    now = time.time() if now is None else now
    base = format_value(metric, state)
    if not show_countdown or metric.shape != "quota" or not metric.reset_key:
        return base
    cd = format_countdown(registry.resolve(metric.reset_key, state))
    if not cd:
        return base
    return cd if (now % COUNTDOWN_PHASE_SECONDS) >= 5 else base
```

Then update `draw_tile` to use `tile_value` instead of `format_value` for the displayed string. Replace the line:
```python
    value = format_value(metric, state)
```
with:
```python
    value = tile_value(metric, state, now=now, show_countdown=show_countdown)
```
and add `show_countdown=True` to the `draw_tile` signature:
```python
def draw_tile(canvas, gfx, font, y_offset, metric, state, brightness=1.0, now=None,
              show_countdown=True):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS (all dashboard tests, ~18 passed). The Task 3 tests still pass because they pass `now=0` (phase 0 → percentage).

- [ ] **Step 5: Commit**

```bash
git add src/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): add Cycler and quota countdown alternation"
```

---

### Task 5: Page rendering — accent, hero, tiles page

**Files:**
- Modify: `src/dashboard.py`
- Test: `tests/test_dashboard.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard.py`:
```python
def _claude():
    return next(p for p in registry.PROVIDERS if p.id == "anthropic")


def _opencode():
    return next(p for p in registry.PROVIDERS if p.id == "opencode")


def test_draw_accent_paints_left_column(gfx, canvas):
    dashboard.draw_accent(canvas, _claude())
    xs = {c.args[0] for c in canvas.SetPixel.call_args_list}
    assert xs == {0}                          # only column 0
    ys = {c.args[1] for c in canvas.SetPixel.call_args_list}
    assert ys == set(range(48))               # full 3*16 height


def test_draw_page_tiles_draws_fixed_labels(gfx, canvas):
    cy = dashboard.Cycler(total=3)
    dashboard.draw_page(canvas, gfx, {"main": MagicMock(), "small": MagicMock()},
                        _claude(), STATE, cy, now=0)
    drawn = texts(gfx)
    assert "SES" in drawn and "WK" in drawn   # both fixed tiles
    assert "SNT" in drawn                      # rotating tile (cycler.current == 0)


def test_draw_page_tiles_rotating_advances(gfx, canvas):
    cy = dashboard.Cycler(total=3)
    cy.current = 1                             # EXT is rotating[1]
    dashboard.draw_page(canvas, gfx, {"main": MagicMock(), "small": MagicMock()},
                        _claude(), STATE, cy, now=0)
    assert "EXT" in texts(gfx)
    assert "SNT" not in texts(gfx)


def test_draw_page_hero_draws_provider_label_and_spend(gfx, canvas):
    cy = dashboard.Cycler(total=1)
    dashboard.draw_page(canvas, gfx, {"main": MagicMock(), "small": MagicMock()},
                        _opencode(), STATE, cy, now=0)
    drawn = texts(gfx)
    assert "OPENCODE" in drawn
    assert "$18.40" in drawn
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py -k "accent or draw_page" -v`
Expected: FAIL with `AttributeError: module 'src.dashboard' has no attribute 'draw_accent'`

- [ ] **Step 3: Add `draw_accent`, `draw_hero`, `draw_page` to `src/dashboard.py`**

```python
def draw_accent(canvas, provider, brightness=1.0):
    """Persistent provider identity: a 1px accent column down the left edge."""
    color = layout.scale_color(provider.color, brightness)
    height = layout.NUM_TILES * layout.TILE_HEIGHT
    for y in range(height):
        canvas.SetPixel(0, y, *color)


def draw_hero(canvas, gfx, fonts, provider, state, brightness=1.0):
    """Full-stack hero readout for a single-metric (balance) provider."""
    metric = provider.page.metric
    accent = layout.scale_color(provider.color, brightness)
    c = gfx.Color(*accent)

    # Provider name across the top (small font).
    gfx.DrawText(canvas, fonts["small"], layout.TILE_BAR_X, layout.TILE_TEXT_Y, c,
                 provider.label)

    # Hero number (spent this period) centered in the main font.
    value = layout.format_dollars(float(registry.resolve(metric.key, state) or 0))
    value_x = max(0, (layout.TILE_WIDTH - len(value) * layout.CHAR_WIDTH) // 2)
    mid_y = (layout.NUM_TILES * layout.TILE_HEIGHT) // 2 + 4
    gfx.DrawText(canvas, fonts["main"], value_x, mid_y, c, value)

    # Optional sub-line (auto-reload note), small font, dimmed.
    sub = registry.resolve(metric.sub_key, state) if metric.sub_key else None
    if sub:
        sc = gfx.Color(*layout.scale_color(layout.COLOR_GRAY, brightness))
        sub = str(sub)
        sub_x = max(0, (layout.TILE_WIDTH - len(sub) * 4) // 2)
        gfx.DrawText(canvas, fonts["small"], sub_x, mid_y + 9, sc, sub)


def draw_page(canvas, gfx, fonts, provider, state, page_cycler, now=None,
              show_countdown=True):
    """Render a provider's page. Outer caller picks which provider."""
    now = time.time() if now is None else now
    draw_accent(canvas, provider)

    page = provider.page
    if isinstance(page, registry.HeroPage):
        draw_hero(canvas, gfx, fonts, provider, state)
        return

    offsets = layout.TILE_Y_OFFSETS
    idx = 0
    for metric in page.fixed:
        if idx >= len(offsets):
            break
        draw_tile(canvas, gfx, fonts["main"], offsets[idx], metric, state,
                  brightness=1.0, now=now, show_countdown=show_countdown)
        idx += 1

    if page.rotating and idx < len(offsets):
        cur = page.rotating[page_cycler.current % len(page.rotating)]
        draw_tile(canvas, gfx, fonts["main"], offsets[idx], cur, state,
                  brightness=page_cycler.brightness(), now=now,
                  show_countdown=show_countdown)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS (~22 passed)

- [ ] **Step 5: Commit**

```bash
git add src/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): provider accent, hero page, and tiles page rendering"
```

---

### Task 6: `Dashboard` top-level orchestration

**Files:**
- Modify: `src/dashboard.py`
- Test: `tests/test_dashboard.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard.py`:
```python
def test_dashboard_uses_only_enabled_providers():
    dash = dashboard.Dashboard()
    assert [p.id for p in dash.providers] == ["anthropic"]


def test_dashboard_single_provider_does_not_rotate():
    dash = dashboard.Dashboard(page_dwell_seconds=4)
    dash.update(now=100)
    dash.update(now=200)
    assert dash.provider_cycler.current == 0   # only one provider -> no advance


def test_dashboard_draw_renders_claude_page(gfx, canvas):
    dash = dashboard.Dashboard()
    dash.draw(canvas, gfx, {"main": MagicMock(), "small": MagicMock()}, STATE, now=0)
    drawn = texts(gfx)
    assert "SES" in drawn and "WK" in drawn


def test_dashboard_draw_noop_when_no_providers(gfx, canvas, monkeypatch):
    monkeypatch.setattr(registry, "enabled_providers", lambda: [])
    dash = dashboard.Dashboard()
    dash.draw(canvas, gfx, {"main": MagicMock(), "small": MagicMock()}, STATE, now=0)
    assert not gfx.DrawText.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py -k "dashboard_" -v`
Expected: FAIL with `AttributeError: module 'src.dashboard' has no attribute 'Dashboard'`

- [ ] **Step 3: Add `Dashboard` to `src/dashboard.py`**

```python
class Dashboard:
    """Top-level: cycles enabled provider pages and draws the current one."""

    def __init__(self, cycle_seconds=4, fade_frames=15, page_dwell_seconds=8,
                 show_countdown=True):
        self.show_countdown = show_countdown
        self.providers = registry.enabled_providers()
        self.provider_cycler = Cycler(len(self.providers), page_dwell_seconds, fade_frames)
        self.page_cyclers = {}
        for p in self.providers:
            n = len(p.page.rotating) if isinstance(p.page, registry.TilesPage) else 1
            self.page_cyclers[p.id] = Cycler(n, cycle_seconds, fade_frames)

    def update(self, now=None):
        now = time.time() if now is None else now
        self.provider_cycler.update(now)
        for cy in self.page_cyclers.values():
            cy.update(now)

    def draw(self, canvas, gfx, fonts, state, now=None):
        if not self.providers:
            return
        now = time.time() if now is None else now
        provider = self.providers[self.provider_cycler.current % len(self.providers)]
        draw_page(canvas, gfx, fonts, provider, state, self.page_cyclers[provider.id],
                  now=now, show_countdown=self.show_countdown)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS (~26 passed)

- [ ] **Step 5: Commit**

```bash
git add src/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): add top-level Dashboard orchestration"
```

---

### Task 7: Config + `main.py` wiring (parallel topology)

**Files:**
- Modify: `src/config.py` (add `resolve_geometry`)
- Test: `tests/test_config.py` (append)
- Modify: `src/main.py`
- Modify: `config.example.yaml`

- [ ] **Step 1: Write the failing test for `resolve_geometry`**

Append to `tests/test_config.py`:
```python
from src.config import resolve_geometry


def test_resolve_geometry_explicit_parallel():
    g = resolve_geometry({"rows": 16, "cols_per_panel": 32,
                          "chain_length": 1, "parallel": 3})
    assert g == {"rows": 16, "cols": 32, "chain_length": 1, "parallel": 3}


def test_resolve_geometry_falls_back_to_legacy_panels():
    # Old configs only had `panels` (a daisy-chain count). Treat it as parallel
    # only if chain_length/parallel are absent.
    g = resolve_geometry({"rows": 16, "cols_per_panel": 32, "panels": 3})
    assert g["parallel"] == 3
    assert g["chain_length"] == 1


def test_resolve_geometry_defaults_single_panel():
    g = resolve_geometry({"rows": 16, "cols_per_panel": 32})
    assert g["chain_length"] == 1
    assert g["parallel"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -k resolve_geometry -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_geometry'`

- [ ] **Step 3: Add `resolve_geometry` to `src/config.py`**

Append to `src/config.py`:
```python
def resolve_geometry(display: dict) -> dict:
    """Resolve panel geometry from the [display] config.

    Prefers explicit chain_length/parallel. Falls back to the legacy `panels`
    key (treated as a parallel-chain count for the triple bonnet). Defaults to a
    single panel.
    """
    parallel = display.get("parallel")
    if parallel is None:
        parallel = display.get("panels", 1)
    return {
        "rows": display["rows"],
        "cols": display["cols_per_panel"],
        "chain_length": display.get("chain_length", 1),
        "parallel": parallel,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -k resolve_geometry -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire `main.py` to the new geometry + dashboard**

In `src/main.py`, replace the body of `run_led_mode` (lines 71–119) with:
```python
def run_led_mode(config, state, lock):
    """Main render loop driving the LED matrix."""
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
    from src.dashboard import Dashboard
    from src.config import resolve_geometry

    disp = config["display"]
    geo = resolve_geometry(disp)
    layout.configure(rows=geo["rows"], cols=geo["cols"], parallel=geo["parallel"])

    options = RGBMatrixOptions()
    options.rows = geo["rows"]
    options.cols = geo["cols"]
    options.chain_length = geo["chain_length"]
    options.parallel = geo["parallel"]
    options.hardware_mapping = disp["gpio_mapping"]
    options.gpio_slowdown = disp["gpio_slowdown"]
    options.brightness = disp["brightness"]
    options.pwm_bits = disp.get("pwm_bits", 11)
    options.pwm_lsb_nanoseconds = disp.get("pwm_lsb_nanoseconds", 130)
    options.scan_mode = disp.get("scan_mode", 0)
    options.limit_refresh_rate_hz = disp.get("limit_refresh_hz", 0)
    options.disable_hardware_pulsing = disp.get("no_hardware_pulse", False)
    options.drop_privileges = False

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()

    font_main = graphics.Font()
    font_main.LoadFont("fonts/5x7.bdf")
    font_small = graphics.Font()
    font_small.LoadFont("fonts/4x6.bdf")
    fonts = {"main": font_main, "small": font_small}

    dash = Dashboard(
        cycle_seconds=disp.get("ticker_cycle_seconds", 4),
        fade_frames=disp.get("ticker_fade_frames", 15),
        page_dwell_seconds=disp.get("page_dwell_seconds", 8),
        show_countdown=disp.get("show_countdown", True),
    )

    logger.info("LED matrix initialized. Starting render loop.")
    try:
        while True:
            canvas.Clear()
            with lock:
                snapshot = copy.deepcopy(state)
            now = time.time()
            dash.update(now)
            dash.draw(canvas, graphics, fonts, snapshot, now)
            canvas = matrix.SwapOnVSync(canvas)
    except KeyboardInterrupt:
        logger.info("Shutting down LED matrix.")
        matrix.Clear()
```

- [ ] **Step 6: Update `config.example.yaml`**

Replace the `display:` block in `config.example.yaml` with:
```yaml
display:
  rows: 16              # one panel's pixel height
  cols_per_panel: 32    # one panel's pixel width
  chain_length: 1       # panels daisy-chained per port (triple bonnet: 1)
  parallel: 3           # parallel chains = number of stacked panels
  gpio_mapping: "adafruit-hat-pwm"
  gpio_slowdown: 2
  brightness: 60
  ticker_cycle_seconds: 4      # inner page sub-rotation seconds
  ticker_fade_frames: 15       # fade frames across a swap
  page_dwell_seconds: 8        # seconds each provider page stays on screen
  show_countdown: true         # alternate quota tiles between % and reset countdown
```

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS — new tests green; old `test_renderer.py`/`test_layout.py` still green (renderer.py untouched).

- [ ] **Step 8: Commit**

```bash
git add src/config.py tests/test_config.py src/main.py config.example.yaml
git commit -m "feat(main): drive parallel topology and the provider Dashboard"
```

---

### Task 8: Cleanup — remove the old renderer and finalize

**Files:**
- Delete: `src/renderer.py`, `tests/test_renderer.py`
- Modify: `tests/test_layout.py` (drop dead-geometry/border/ticker tests)
- Modify: `src/layout.py` (remove old strip constants + `ticker_pages`)
- Modify: `README.md`, `install.sh` (note the 4×6 font)

- [ ] **Step 1: Delete the dead renderer and its tests**

```bash
git rm src/renderer.py tests/test_renderer.py
```

- [ ] **Step 2: Trim `tests/test_layout.py` to the surviving helpers**

Replace the entire contents of `tests/test_layout.py` with:
```python
from src.layout import (
    COLOR_SESSION, COLOR_WEEK_ALL, COLOR_WEEK_SONNET,
    COLOR_EXTRA, COLOR_API, COLOR_GRAY, COLOR_BAR_BG,
    format_tokens, format_dollars, compute_bar_width, scale_color,
)


def test_colors_are_rgb_tuples():
    for color in [COLOR_SESSION, COLOR_WEEK_ALL, COLOR_WEEK_SONNET,
                  COLOR_EXTRA, COLOR_API, COLOR_GRAY, COLOR_BAR_BG]:
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)


def test_format_tokens():
    assert format_tokens(1_200_000) == "1.2M"
    assert format_tokens(410_000) == "410K"
    assert format_tokens(500) == "500"


def test_format_dollars():
    assert format_dollars(12.47) == "$12.47"
    assert format_dollars(100.5) == "$100"


def test_compute_bar_width():
    assert compute_bar_width(50, 100) == 50
    assert compute_bar_width(0, 100) == 0
    assert compute_bar_width(25, 200) == 50


def test_scale_color():
    assert scale_color((255, 100, 50), 1.0) == (255, 100, 50)
    assert scale_color((255, 100, 50), 0.5) == (127, 50, 25)
    assert scale_color((255, 100, 50), 0.0) == (0, 0, 0)
```

- [ ] **Step 3: Remove the old strip constants from `src/layout.py`**

In `src/layout.py`, delete these now-dead lines:
- `PANEL_WIDTH = 32`
- `TOTAL_WIDTH = 96  # 3 panels x 32`
- `TOTAL_HEIGHT = 16`
- the entire `# Text positions (5x7 font)` block: `CHAR_WIDTH`/`TEXT_Y` stay, but delete `BAR_BORDER_X/Y/W/H`, `BAR_X`, `BAR_Y`, `BAR_WIDTH`, `BAR_HEIGHT`
- the `# Ticker ...` block: `TICKER_PROJECT_Y_NAME`, `TICKER_PROJECT_Y_DETAIL`
- the `ticker_pages(...)` function

Keep: `CHAR_WIDTH = 5`, all `COLOR_*`, `format_tokens`, `format_dollars`, `compute_bar_width`, `scale_color`, and the entire Task 1 tile-geometry section. Then add the spec's canonical aliases at the end of the tile-geometry section:
```python
# Canonical full-canvas dimensions (derived from tile geometry).
TOTAL_WIDTH = TILE_WIDTH
TOTAL_HEIGHT = TILE_HEIGHT * NUM_TILES
```

Note: `CHAR_WIDTH` and `TEXT_Y` are referenced by `dashboard.draw_tile` via `layout.TILE_TEXT_Y` (not `TEXT_Y`), so `TEXT_Y` may also be deleted; keep `CHAR_WIDTH`.

- [ ] **Step 4: Verify nothing imports the removed names**

Run: `grep -rn "renderer\|BAR_BORDER\|ticker_pages\|PANEL_WIDTH\|DisplayCycler" src/ tests/`
Expected: no matches (empty output). If any appear, they are bugs — fix before continuing.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS, with `test_renderer.py` gone and `test_layout.py` trimmed. Note the passing count.

- [ ] **Step 6: Note the 4×6 font requirement**

In `README.md`, in the build/setup section where `fonts/5x7.bdf` is mentioned, add a line:
> The dashboard also uses `fonts/4x6.bdf` for provider labels. Copy both BDF files from the `rpi-rgb-led-matrix/fonts/` directory into the project's `fonts/` directory.

In `install.sh`, wherever `5x7.bdf` is copied, copy `4x6.bdf` alongside it (mirror the existing copy command for the second file).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove old renderer/strip layout, finalize dashboard"
```

---

## Deployment Verification (manual, on the Pi — not a unit test)

The render loop imports `rgbmatrix`, which is Pi-only, so it cannot be smoke-tested locally. After merging, on the Pi:

1. Copy `fonts/4x6.bdf` next to `fonts/5x7.bdf`.
2. Update the Pi's `config.yaml` `display:` block to `chain_length: 1`, `parallel: 3` (per Task 7 example).
3. Run `sudo venv/bin/python3 -m src.main -c config.yaml`.
4. Confirm the three stacked panels show the Claude page: SES and WK fixed on the top two panels, the bottom panel rotating SNT → EXT → API, with the left-edge accent column. Push fresh data with `client/push_usage.py` and confirm values update.

`--dry-run` still works for verifying data flow (it prints JSON and does not render).

---

## Self-Review

**Spec coverage:**
- D1 topology/config → Task 7 (`resolve_geometry`, `main.py` options). ✔
- D2 vertical stack / no remapper → no remapper code anywhere; geometry stacks via `TILE_Y_OFFSETS`. ✔
- D3 geometry single-source → Task 1 `configure()`; Task 8 canonical `TOTAL_*` aliases. ✔
- D4 provider pages → Tasks 5–6 (`draw_page`, `Dashboard`). ✔
- D5 justified tiles → Task 3 (`draw_tile` right-aligned value, test asserts x=17). ✔
- D6 four shapes → Task 3 `format_value`/`metric_pct` (quota/capped/spend), Task 5 hero (balance). ✔
- D7 color+tag identity → Task 5 `draw_accent` (color column) + hero label; per-tile text tag deferred (documented in spec §3 tunables). ✔ (conscious, documented narrowing)
- D8 balance hero = spent this period → Task 5 `draw_hero` renders `metric.key = *.spent_period`. ✔
- D9 Claude page 2 fixed + 3 rotating → Task 2 registry, Task 5 `draw_page`. ✔
- D10 skip disabled pages → Task 2 `enabled_providers()`, Task 6 `Dashboard.providers`. ✔
- Tunable: countdown alternation → Task 4 `tile_value`. ✔
- Tunable: Anthropic API on Claude page → Task 2 (`API` in rotating). ✔
- Testing strategy (spec §7) → test_geometry/test_registry/test_dashboard/test_config. ✔

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to" — every code step shows full code. ✔

**Type/name consistency:** `Cycler` (`.current`, `.brightness()`, `.update(now)`), `Metric(label, shape, key, color, limit_key, reset_key, sub_key)`, `TilesPage(fixed, rotating)`, `HeroPage(metric)`, `draw_tile(canvas, gfx, font, y_offset, metric, state, brightness, now, show_countdown)`, `draw_page(...)`, `Dashboard(cycle_seconds, fade_frames, page_dwell_seconds, show_countdown)` — names match across Tasks 2–7. `fonts` dict keys `{"main","small"}` consistent in Tasks 5–7. ✔

**Known conscious narrowing (not a gap):** Phase 1 ships only the Claude page live (others `enabled=False`); per-tile *text* tags on tiles pages are deferred in favor of the accent column because 32px can't fit tag+label+value — recorded in spec §3 and Task 5.
