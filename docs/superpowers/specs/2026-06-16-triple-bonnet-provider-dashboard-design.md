# Triple-Bonnet Provider Dashboard — Design

**Date:** 2026-06-16
**Status:** Approved (pending spec review)
**Author:** brainstorming session (Justin + Claude)

## 1. Context & Problem

The display was built for **three 16×32 HUB75 panels daisy-chained** into a single
`chain_length=3, parallel=1` strip — a **96 wide × 16 tall** canvas. The renderer cycles
through one metric at a time because a long thin strip can only show one line of text + one bar.

The hardware has now changed: an **Adafruit triple LED-matrix bonnet** drives the three panels
as **3 independent parallel chains** (one ribbon per bonnet port → one panel each), mounted in a
**vertical stack**. In `rpi-rgb-led-matrix` terms this is `chain_length=1, parallel=3`, which
produces a **32 wide × 48 tall** framebuffer arranged as three stacked 32×16 tiles
(chain 0 → rows 0–15, chain 1 → rows 16–31, chain 2 → rows 32–47). Because the panels are
physically stacked top-to-bottom, this matches the framebuffer's natural order — **no pixel
remapping is required.**

Separately, the project is expanding from Claude-only to **multi-provider** AI usage tracking:
Claude (Anthropic), ChatGPT/OpenAI, opencode, xAI, and others over time. These providers expose
**heterogeneous metric shapes** (percentage quotas, capped dollar spend, auto-reload balances,
uncapped spend), so the rendering and data model must be extensible by *data*, not by editing
render code per provider.

## 2. Goals & Non-Goals

### Goals (this spec)
- Drive the three panels correctly as parallel chains (topology + config change).
- Derive all display geometry from config — eliminate the hardcoded `96`/`16` literals so width
  and panel count can never drift apart again.
- Replace the single-screen cycler with a **provider-page architecture**: one provider owns the
  full 32×48 screen at a time, with a per-provider page layout.
- Introduce a **provider/metric registry** keyed by metric **shape**, so adding a provider is a
  data entry, not a code change.
- Render the **Claude/Anthropic page** correctly from the *existing* data sources (subscription
  push + Anthropic Admin API).
- Keep dry-run mode and the test suite working.

### Non-Goals (future phases)
- Data **collectors/ingestion** for OpenAI, opencode, and xAI (their usage/billing/balance APIs).
  This spec defines the registry slots and renderers those providers will use, and ships them
  **disabled** until their data exists — but wiring the live data is out of scope here.
- Any pixel remapper (not needed for a vertical stack).
- Web/remote configuration UI.

## 3. Locked Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Topology = `chain_length=1, parallel=3`; config gains explicit `chain_length` / `parallel` keys (fallback to legacy `panels`). | The one change that lights all three panels; explicit keys remove the daisy-chain assumption. |
| D2 | Physical = vertical stack → 32×48, **no remapper**. | Matches framebuffer's natural top-to-bottom parallel order. |
| D3 | Geometry derived once via `layout.configure(rows, cols, parallel)`. | Kills the 96-vs-32 dual-source-of-truth bug already latent in the code. |
| D4 | Layout architecture = **Provider pages** (one provider per screen, cycling). | On a 32px-wide display, provider identity is the costly signal; isolating one provider per page makes "whose number is this?" free and lets each provider customize its own tile layout. |
| D5 | Per-tile micro-layout = **justified** label (left) + value (right), 5×7 font, full-width bar below. | Justifying lets the crisp big font fit in 32px ("SES 45%" centered would overflow). |
| D6 | Four metric **shapes**, each with its own renderer: `quota`, `capped`, `balance`, `spend`. | Render by shape, not provider → 4 small routines instead of an ever-growing if/elif. |
| D7 | Provider identity = **persistent provider color theme + short corner tag** (no title-card animation). | Simpler to build; always-on identity. |
| D8 | Balance hero number = **spent this period** (remaining/rate available as sub-line). | Auto-reload makes "remaining" a meaningless sawtooth; spend reflects real burn. |
| D9 | Claude page composition = session + week-all fixed on tiles 0–1, **week-sonnet → extra → API sub-rotating** on tile 2. | Preserves the earlier "2 fixed + 1 rotating" preference, now scoped inside the Claude page. |
| D10 | Disabled / no-data provider pages are **skipped**; with only Claude enabled there is no outer rotation. | Enables incremental rollout — today the display shows just the Claude page. |

### Tunable defaults (set now, easy to flip during review)
- **Countdown** ("2h30m" to reset): quota tiles **alternate** their value between `45%` and the
  reset countdown on a slow cadence, behind a `show_countdown` config toggle (default **on**).
  Reuses the existing `format_countdown()`. There is no room for both on a 32px line.
- **Anthropic API spend** lives on the Claude/Anthropic page as one of the sub-rotating items
  (`SNT · EXT · API`), rather than its own page (same provider). Could be split into a separate
  page later via the registry.
- **Page color theming:** metric tiles keep their per-metric hues (session=coral, week-all=amber,
  sonnet=purple); provider identity is carried by the **corner tag** (provider abbreviation in the
  4×6 small font, provider accent color) plus the page's accent. Full single-color theming is an
  alternative if metric hues prove confusing.

## 4. Architecture

### 4.1 Two-level state machine (the core of D4)
```
ProviderCycler (outer)         # which provider page is on screen; fades between pages
   └── Page (self-contained)   # lays out its own tiles from its metric list
         ├── tiles layout      # ≤3 metrics → tiles; >3 → sub-rotate (Claude)
         └── hero  layout      # 1 metric → big centered readout (opencode, xAI)
```
The outer cycler is a *composite*: it does not know what is inside a page. Adding xAI registers a
page and it joins the rotation — the cycler is untouched. Each page owns its inner behavior
(static tiles, sub-rotation, or hero), so per-provider customization is an isolated unit.

### 4.2 Metric shapes → renderers (D6)
| Shape | Example | Tile rendering |
|-------|---------|----------------|
| `quota` | Claude SES/WK/SNT, ChatGPT % | bar 0–100% + `45%`; optional value↔countdown alternation |
| `capped` | Claude extra usage | bar = spent/limit + `$12` (spent), limit implied by bar |
| `balance` | opencode, xAI | **hero page**: big `spent this period` + sub-line `auto-reload @ $X` |
| `spend` | Anthropic API, future OpenAI billing | no bar; `$4.20` value only |

### 4.3 Registry (D6) — the single source of truth
A new `src/registry.py` defines providers and their pages. Sketch:

```python
PROVIDERS = [
    Provider(
        id="anthropic", label="CLAUDE", tag="CL", color=CLAUDE_ACCENT, enabled=True,
        page=TilesPage(
            fixed=[Metric("SES", "quota", key="session_pct",   color=COLOR_SESSION, reset="session_reset_utc"),
                   Metric("WK",  "quota", key="week_all_pct",   color=COLOR_WEEK_ALL, reset="week_all_reset_utc")],
            rotating=[Metric("SNT", "quota",  key="week_sonnet_pct", color=COLOR_WEEK_SONNET, reset="week_sonnet_reset_utc"),
                      Metric("EXT", "capped", key="extra_spent", limit_key="extra_limit", color=COLOR_EXTRA),
                      Metric("API", "spend",  key="api.total_spend", color=COLOR_API)],
        ),
    ),
    Provider(id="openai",   label="CHATGPT",  tag="OA", color=OPENAI_ACCENT,  enabled=False,
             page=TilesPage(fixed=[Metric("GPT", "quota", key="openai.quota_pct", color=OPENAI_ACCENT)], rotating=[])),
    Provider(id="opencode", label="OPENCODE", tag="OC", color=OPENCODE_ACCENT, enabled=False,
             page=HeroPage(metric=Metric("OPC", "balance", key="opencode.spent_period",
                                         sub_key="opencode.autoreload", color=OPENCODE_ACCENT))),
    Provider(id="xai",      label="XAI",      tag="XA", color=XAI_ACCENT,      enabled=False,
             page=HeroPage(metric=Metric("XAI", "balance", key="xai.spent_period",
                                         sub_key="xai.autoreload", color=XAI_ACCENT))),
]
```
- `enabled=False` pages are skipped by `ProviderCycler` (D10), so today only the Claude page shows.
- `key` resolves against the shared `state` dict (dot-paths for nested, e.g. `api.total_spend`).
- The collector (future work) iterates the same registry to know what to poll for each provider.

### 4.4 Geometry (D3)
`layout.configure(rows, cols, parallel)` is called once from `main()` after config load. It sets
module globals:
```
TILE_WIDTH  = cols            # 32
TILE_HEIGHT = rows            # 16
NUM_TILES   = parallel        # 3
TOTAL_WIDTH = cols            # 32
TOTAL_HEIGHT= rows * parallel # 48
TILE_Y_OFFSETS = [0, 16, 32]
```
Defaults preset to the current hardware so tests and dry-run run without config. Per-tile element
positions are relative to a tile's top: `TILE_TEXT_Y = 8`, `TILE_BAR_Y = 11`, `TILE_BAR_H = 3`,
bar spans x∈[1, TILE_WIDTH-1]. A draw routine adds the tile's `y_offset`.

The old `BAR_BORDER_*` constants and the boxed-border draw are **removed** — at 32px a box border
costs too many pixels; the bar itself is the indicator.

## 5. File-by-File Changes

- **`config.yaml` (Pi) & `config.example.yaml`** — add `chain_length: 1`, `parallel: 3`; document
  `show_countdown` and `page_dwell_seconds` (outer ProviderCycler dwell). Keep `rows: 16`,
  `cols_per_panel: 32`. The existing `ticker_cycle_seconds` / `ticker_fade_frames` are repurposed
  to drive each page's **inner sub-rotation** (and renamed in docs to `cycle_seconds`/`fade_frames`
  with the old names accepted as aliases). Legacy `panels` honored as a fallback for `parallel`.
- **`src/main.py`** — `options.chain_length`/`options.parallel` from config (fallback to `panels`);
  call `layout.configure(...)`; render loop draws via `ProviderCycler` + page renderers instead of
  `draw_screen`.
- **`src/layout.py`** — add `configure()` + tile geometry constants + `TILE_Y_OFFSETS`; remove
  `BAR_BORDER_*`; keep `scale_color`, `compute_bar_width`, `format_dollars`, `format_tokens`.
- **`src/renderer.py`** — replace `draw_screen`/`draw_metric` with: `draw_tile(canvas, gfx, font,
  y_offset, metric, value_state, brightness)`, the four shape renderers, `draw_page(page, ...)`,
  `draw_corner_tag(...)`, `ProviderCycler` (outer) and a per-page sub-rotation cycler (reuse the
  existing fade logic from `DisplayCycler`). Keep `format_countdown`. Drop the stale `Ticker` /
  `draw_ticker_page` / `draw_*_panel` compat cruft.
- **`src/registry.py`** *(new)* — `Provider`, `TilesPage`, `HeroPage`, `Metric` dataclasses + the
  `PROVIDERS` list + a `resolve(key, state)` helper for dot-path lookups.
- **`src/receiver.py`** — keep the in-progress reset-timestamp plumbing (`*_reset_utc`).
- **`client/push_usage.py`** — keep the in-progress reset-timestamp scraping/push.
- **`tests/`** — see §7.

## 6. Rendering & Cycling Details

- **Justified tile (D5):** label drawn at x=1; value right-aligned at `x = TILE_WIDTH -
  len(value)*CHAR_WIDTH`. Values are pre-formatted short per shape (`45%`, `$12`, `$4.20`). If a
  value still exceeds the tile width it is truncated from the right with no ellipsis (rare).
- **Countdown alternation:** for `quota` metrics with a reset timestamp and `show_countdown=true`,
  the value field shows the percentage for ~5s, then the countdown (`2h30m`) for ~2s, synchronized
  across the page. Expired/empty countdown falls back to the percentage.
- **Corner tag (D7):** provider `tag` (e.g. `CL`) in the 4×6 small font at the page's top-left,
  in the provider accent color. On `hero` pages the full `label` (e.g. `OPENCODE`) is shown (room
  available).
- **Hero page (D8):** big centered `spent this period` value (largest font that fits 32px), with a
  sub-line `auto-reload @ $X` (or remaining/rate) beneath.
- **ProviderCycler:** iterates `enabled` providers with data; fades between pages on a dwell timer
  (config `page_dwell_seconds`). With a single enabled page it simply renders that page (the page's
  own sub-rotation still runs). Providers whose backing data is absent are skipped each tick.

## 7. Testing Strategy

- **`test_layout.py`** — `configure()` yields 32×48 and `TILE_Y_OFFSETS == [0,16,32]`; justified
  value x-position math; removal of border constants.
- **`test_registry.py`** *(new)* — `resolve()` dot-paths; only `enabled` providers are cycled;
  Claude page exposes 2 fixed + 3 rotating metrics; each metric's shape maps to a renderer.
- **`test_renderer.py`** — each shape renderer paints expected pixels on a fake canvas (quota bar
  width, capped spent/limit ratio, spend has no bar, hero centers the spend value); Claude page
  sub-rotation visits exactly `[SNT, EXT, API]`; fixed tiles never change; countdown alternation
  toggles value↔countdown; corner tag drawn for the active provider.
- **`test_client.py` / `test_receiver.py`** — unchanged reset-timestamp plumbing still passes.
- **Dry-run** — still prints JSON; an optional ASCII 3-tile preview is explicitly out of scope.

## 8. Incremental Rollout

- **Phase 1 (this spec):** topology + geometry + provider-page architecture + registry + Claude
  page live; OpenAI/opencode/xAI registered but `enabled=False`. Visible result: the three stacked
  panels show the Claude page correctly.
- **Phase 2+ (future specs):** per-provider collectors populate `state` for OpenAI/opencode/xAI,
  flip `enabled=True`, and the pages light up — no renderer changes required.

## 9. Risks & Edge Cases
- **Value overflow at 32px** — mitigated by shape-specific short formatting; truncation as backstop.
- **Single enabled provider** — ProviderCycler must no-op the outer fade and just run the page.
- **Stale data** — a provider with data older than a threshold may be skipped or dimmed (Phase 2
  concern; registry leaves room via an `enabled`/freshness check).
- **Config drift** — geometry now derives from config; the legacy `panels` fallback must not be
  set simultaneously with conflicting `chain_length`/`parallel` (document precedence: explicit wins).
