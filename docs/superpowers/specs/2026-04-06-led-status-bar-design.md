# Claude LED Matrix Status Bar — Design Spec

## Overview

A Raspberry Pi 3B drives a 3-panel HUB75 LED matrix (32x192 pixels, horizontal strip) displaying Claude subscription usage and Anthropic API spend in real time. The display updates every 2-5 minutes and runs as a systemd service.

## Hardware

- **Board:** Raspberry Pi 3B, WiFi-connected
- **Display:** 3x 32x64 HUB75 LED panels, daisy-chained horizontally (total: 32 rows x 192 columns)
- **Wiring:** Direct GPIO from Pi to Panel 1 HUB75 input, panels chained via ribbon cables
- **Power:** Panels powered separately via 5V power strip (not through the Pi)
- **GPIO mapping:** `"regular"` (configurable — may need tuning to match existing wiring)
- **GPIO slowdown:** 2 (typical for Pi 3B, configurable)

No hardware changes needed from the existing crypto ticker setup.

## Display Layout

```
Row 0  ┌──── Panel 1 (64px) ────┬──── Panel 2 (64px) ────┬──── Panel 3 (64px) ────┐
       │                        │                         │                        │
       │      SESSION           │       WEEKLY            │      API TOTAL         │
       │       10%              │  ALL ████░░░░░░ 22%     │       $12.47           │
       │  ██░░░░░░░░░░░░        │  SNT ██░░░░░░░░  9%     │     1.2M tokens        │
       │    Resets 7pm          │  EXT ██░░░░░░░░ $7/$79  │                        │
Row 21 ├────────────────────────┴─────────────────────────┴────────────────────────┤
       │              tastytrade-bot          diy-helper                           │
       │              $3.20 · 410K tk         $1.80 · 230K tk                      │
Row 31 └──────────────────────────────────────────────────────────────────────────┘
```

### Top Dashboard (Rows 0-21)

Three zones spanning the full width:

**Panel 1 — Session (red):**
- Label: "SESSION"
- Large percentage (7x13 font)
- Progress bar (full panel width minus padding)
- Reset time below bar (e.g., "Resets 7pm")

**Panel 2 — Weekly + Extra (yellow/green/blue):**
- Label: "WEEKLY"
- Three horizontal bars with labels and percentages:
  - ALL — yellow `(255, 217, 61)` — weekly usage across all models
  - SNT — green `(107, 203, 119)` — weekly Sonnet-only usage
  - EXT — blue `(77, 150, 255)` — extra usage with dollar amounts ($spent/$limit)

**Panel 3 — API Total (purple):**
- Label: "API TOTAL"
- Large dollar amount (7x13 font)
- Token count below (e.g., "1.2M tokens")

### Bottom Ticker (Rows 22-31)

- Displays 2 API projects side-by-side (configurable: 2 or 3)
- Each project shows:
  - Line 1: project name (purple)
  - Line 2: dollar spend + token count (gray)
- Cycles through pages every 4 seconds with a fade transition
- 7 projects = 4 pages (last page shows 1 project)
- Fade: ~0.5 seconds (15 frames), linear brightness interpolation

### Color Scheme

| Element        | Color Name | RGB             |
|----------------|-----------|-----------------|
| Session        | Red       | (255, 107, 107) |
| Week All       | Yellow    | (255, 217, 61)  |
| Week Sonnet    | Green     | (107, 203, 119) |
| Extra Usage    | Blue      | (77, 150, 255)  |
| API            | Purple    | (201, 160, 255) |
| Labels/dimmed  | Gray      | (128, 128, 128) |
| Bar background | Dark gray | (51, 51, 51)    |

### Fonts

- Labels (SESSION, WEEKLY, etc.): 4x6 pixel font (built into rpi-rgb-led-matrix)
- Large percentages / dollar amounts: 7x13 font
- Ticker text: 4x6 or 5x7 font
- Fonts symlinked from rpi-rgb-led-matrix install

## System Architecture

Single Python process, two threads:

```
┌─────────────────────────────────────────────────────┐
│                   Pi 3B (systemd service)            │
│                                                      │
│  ┌──────────────────┐     ┌───────────────────────┐ │
│  │  Data Collector   │     │   Display Renderer    │ │
│  │  (bg thread)      │     │   (main thread)       │ │
│  │                   │     │                       │ │
│  │  ┌─────────────┐ │     │  ┌─────────────────┐  │ │
│  │  │ Claude Code  │ │     │  │ Top Dashboard   │  │ │
│  │  │ /usage parse │ │     │  │ - Session %     │  │ │
│  │  └──────┬──────┘ │     │  │ - Weekly bars   │  │ │
│  │         │        │     │  │ - API total     │  │ │
│  │  ┌──────▼──────┐ │     │  └─────────────────┘  │ │
│  │  │  Shared     │─┼─────┤                       │ │
│  │  │  State Dict │ │     │  ┌─────────────────┐  │ │
│  │  └──────▲──────┘ │     │  │ Bottom Ticker   │  │ │
│  │         │        │     │  │ - 2 projects    │  │ │
│  │  ┌──────┴──────┐ │     │  │ - fade cycle    │  │ │
│  │  │ Anthropic   │ │     │  └─────────────────┘  │ │
│  │  │ Admin API   │ │     │                       │ │
│  │  └─────────────┘ │     │  rgbmatrix (C++)      │ │
│  └──────────────────┘     └───────────────────────┘ │
│                                                      │
│  config.yaml                                         │
└─────────────────────────────────────────────────────┘
```

### Main Thread (Display Renderer)

- Owns the LED matrix via rgbmatrix Python bindings
- Runs a render loop at ~30fps (vsync with `SwapOnVSync`)
- Each frame:
  1. Acquires lock, copies shared state
  2. Draws top dashboard (static content, redrawn each frame)
  3. Draws bottom ticker (manages fade timing and page cycling)
  4. Swaps canvas buffer

### Background Thread (Data Collector)

- Runs on a timer loop
- Subscription data: every 3 minutes
  - Spawns `claude` CLI as subprocess
  - Parses `/usage` output for session %, weekly %, extra usage
  - Extracts reset times
- API data: every 5 minutes
  - Calls Anthropic admin API with admin key
  - Aggregates spend and token counts per configured project
- Updates shared state dict under a threading lock

### Shared State

```python
state = {
    "subscription": {
        "session_pct": 10,
        "session_reset": "7pm",
        "week_all_pct": 22,
        "week_all_reset": "Apr 10",
        "week_sonnet_pct": 9,
        "week_sonnet_reset": "Apr 9",
        "extra_spent": 7.13,
        "extra_limit": 79.00,
    },
    "api": {
        "total_spend": 12.47,
        "total_tokens": 1_200_000,
        "projects": [
            {"name": "tastytrade-bot", "spend": 3.20, "tokens": 410_000},
            {"name": "diy-helper", "spend": 1.80, "tokens": 230_000},
            {"name": "contract-finder", "spend": 4.12, "tokens": 380_000},
            {"name": "sticker-maker", "spend": 3.35, "tokens": 180_000},
            {"name": "trading-bot", "spend": 0.00, "tokens": 0},
            {"name": "lakeshore-analytics", "spend": 0.00, "tokens": 0},
            {"name": "tradr-buildr", "spend": 0.00, "tokens": 0},
        ]
    },
    "last_updated": "2026-04-06T18:30:00"
}
```

## Configuration

### config.yaml

```yaml
display:
  panels: 3
  rows: 32
  cols_per_panel: 64
  gpio_mapping: "regular"
  gpio_slowdown: 2
  brightness: 60
  ticker_projects_per_page: 2
  ticker_cycle_seconds: 4
  ticker_fade_frames: 15

polling:
  subscription_interval_seconds: 180
  api_interval_seconds: 300

anthropic:
  admin_api_key: "${ANTHROPIC_ADMIN_KEY}"
  api_projects:
    - name: "tastytrade-bot"
      api_key_id: "key_abc123"
    - name: "diy-helper"
      api_key_id: "key_def456"
    - name: "contract-finder"
      api_key_id: "key_ghi789"
    - name: "sticker-maker"
      api_key_id: "key_jkl012"
    - name: "trading-bot"
      api_key_id: "key_mno345"
    - name: "lakeshore-analytics"
      api_key_id: "key_pqr678"
    - name: "tradr-buildr"
      api_key_id: "key_stu901"
```

Secrets (admin API key) are stored as environment variables, loaded via systemd `EnvironmentFile`, and interpolated at runtime. API keys are never stored in the config file directly.

## Deployment

### File Structure

```
claude-ledmatrix-status-bar/
├── config.yaml
├── requirements.txt
├── install.sh
├── claude-status-bar.service
├── src/
│   ├── main.py              # entry point, arg parsing, starts threads
│   ├── collector.py          # background thread: fetches subscription + API data
│   ├── renderer.py           # main thread: drives LED matrix display
│   ├── layout.py             # pixel-level layout constants and region math
│   └── config.py             # loads and validates config.yaml
└── fonts/
    └── (symlink to rpi-rgb-led-matrix fonts)
```

### systemd Service

- Unit file: `claude-status-bar.service`
- Auto-starts on boot (`WantedBy=multi-user.target`)
- Restarts on crash (`Restart=on-failure`)
- Runs as root (required for GPIO access with rpi-rgb-led-matrix)
- Loads secrets from `/etc/claude-status-bar.env`

### Install Script

`install.sh` handles:
1. Clone and build rpi-rgb-led-matrix (C++ library + Python bindings)
2. Install Python dependencies (`pip install -r requirements.txt`)
3. Symlink fonts directory
4. Copy systemd service file
5. Prompt for API keys and write environment file
6. Enable and start the service

## Open Questions (To Resolve During Implementation)

1. **Claude Code CLI parsing:** The `/usage` command renders a TUI. Need to investigate whether a `--json` flag exists or find the underlying data source. If TUI-only, we may need to parse ANSI output or call the same internal API endpoint Claude Code uses.
2. **Anthropic Admin API:** Confirm the exact endpoint and response format for per-key usage data. May need organization-level admin access.
3. **Font sizing on hardware:** The 7x13 font for large numbers may need adjustment once tested on the actual panels. Layout coordinates in `layout.py` should be easy to tune.
4. **`hardware_mapping` value:** Needs verification against the existing GPIO wiring on the Pi. Configurable in `config.yaml` so it can be changed without code edits.
