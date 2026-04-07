# Claude LED Matrix Status Bar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python service that displays Claude subscription usage and API spend on a 3-panel 32x192 HUB75 LED matrix driven by a Raspberry Pi 3B.

**Architecture:** Single Python process with two threads — a background data collector (tmux-based Claude CLI scraping + Anthropic Admin API) and a main-thread LED renderer using rpi-rgb-led-matrix Python bindings. Config-driven with systemd deployment.

**Tech Stack:** Python 3.9+, rpi-rgb-led-matrix (C++ with Python bindings), PyYAML, requests, tmux (for CLI scraping)

**Design Spec:** `docs/superpowers/specs/2026-04-06-led-status-bar-design.md`

---

## File Structure

```
claude-ledmatrix-status-bar/
├── .gitignore
├── config.example.yaml
├── requirements.txt
├── install.sh
├── claude-status-bar.service
├── claude-status-bar.env.example
├── src/
│   ├── __init__.py
│   ├── main.py              # entry point, arg parsing, thread orchestration
│   ├── config.py             # loads and validates config.yaml
│   ├── collector.py          # background thread: subscription + API data fetching
│   ├── renderer.py           # main thread: LED matrix rendering
│   └── layout.py             # pixel-level layout constants and helpers
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # shared fixtures (sample state, fake canvas)
│   ├── test_config.py
│   ├── test_layout.py
│   ├── test_collector.py
│   └── test_renderer.py
└── fonts/ -> (symlink to rpi-rgb-led-matrix/fonts at install time)
```

**Responsibilities:**
- `config.py` — load YAML, interpolate env vars, validate required fields, return typed config dict
- `layout.py` — all pixel coordinates, region boundaries, color constants, and helper functions (format_tokens, format_dollars, compute bar widths)
- `collector.py` — two collection functions (subscription via tmux/CLI scraping, API via Anthropic Admin API) plus a thread runner that updates shared state on intervals
- `renderer.py` — render loop that reads shared state and draws to LED matrix canvas (top dashboard + bottom ticker with fade transitions)
- `main.py` — parse CLI args, load config, initialize matrix, start collector thread, run render loop, handle graceful shutdown

---

### Task 1: Project Scaffolding

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `config.example.yaml`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create .gitignore**

```gitignore
__pycache__/
*.pyc
*.pyo
.pytest_cache/
config.yaml
*.env
.superpowers/
fonts/
venv/
```

- [ ] **Step 2: Create requirements.txt**

```
pyyaml>=6.0
requests>=2.28.0
```

Note: `rgbmatrix` is installed from the rpi-rgb-led-matrix build, not pip.

- [ ] **Step 3: Create config.example.yaml**

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
    - name: "my-project"
      api_key_id: "apikey_01EXAMPLE"
```

- [ ] **Step 4: Create src/__init__.py and tests/__init__.py**

Both files are empty.

- [ ] **Step 5: Create tests/conftest.py with shared fixtures**

```python
import pytest


@pytest.fixture
def sample_state():
    return {
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
            ],
        },
        "last_updated": "2026-04-06T18:30:00",
    }


@pytest.fixture
def sample_config():
    return {
        "display": {
            "panels": 3,
            "rows": 32,
            "cols_per_panel": 64,
            "gpio_mapping": "regular",
            "gpio_slowdown": 2,
            "brightness": 60,
            "ticker_projects_per_page": 2,
            "ticker_cycle_seconds": 4,
            "ticker_fade_frames": 15,
        },
        "polling": {
            "subscription_interval_seconds": 180,
            "api_interval_seconds": 300,
        },
        "anthropic": {
            "admin_api_key": "sk-ant-admin-test-key",
            "api_projects": [
                {"name": "tastytrade-bot", "api_key_id": "apikey_01ABC"},
                {"name": "diy-helper", "api_key_id": "apikey_02DEF"},
            ],
        },
    }
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt config.example.yaml src/__init__.py tests/__init__.py tests/conftest.py
git commit -m "feat: project scaffolding with config template and test fixtures"
```

---

### Task 2: Config Module

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config loading**

```python
# tests/test_config.py
import os
import pytest
import tempfile
import yaml

from src.config import load_config


@pytest.fixture
def valid_config_file(sample_config):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_config, f)
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def config_with_env_var():
    raw = {
        "display": {
            "panels": 3, "rows": 32, "cols_per_panel": 64,
            "gpio_mapping": "regular", "gpio_slowdown": 2, "brightness": 60,
            "ticker_projects_per_page": 2, "ticker_cycle_seconds": 4,
            "ticker_fade_frames": 15,
        },
        "polling": {
            "subscription_interval_seconds": 180,
            "api_interval_seconds": 300,
        },
        "anthropic": {
            "admin_api_key": "${TEST_ADMIN_KEY}",
            "api_projects": [],
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(raw, f)
        yield f.name
    os.unlink(f.name)


def test_load_valid_config(valid_config_file, sample_config):
    config = load_config(valid_config_file)
    assert config["display"]["panels"] == 3
    assert config["display"]["rows"] == 32
    assert config["display"]["brightness"] == 60
    assert config["polling"]["subscription_interval_seconds"] == 180
    assert len(config["anthropic"]["api_projects"]) == 2


def test_env_var_interpolation(config_with_env_var):
    os.environ["TEST_ADMIN_KEY"] = "sk-ant-admin-real-key"
    try:
        config = load_config(config_with_env_var)
        assert config["anthropic"]["admin_api_key"] == "sk-ant-admin-real-key"
    finally:
        del os.environ["TEST_ADMIN_KEY"]


def test_missing_env_var_raises(config_with_env_var):
    os.environ.pop("TEST_ADMIN_KEY", None)
    with pytest.raises(ValueError, match="TEST_ADMIN_KEY"):
        load_config(config_with_env_var)


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")


def test_missing_required_section():
    raw = {"display": {"panels": 3}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(raw, f)
        path = f.name
    try:
        with pytest.raises(ValueError, match="polling"):
            load_config(path)
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/justin/lakeshore-studio/ai-projects/claude-ledmatrix-status-bar && python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Implement config.py**

```python
# src/config.py
import os
import re

import yaml


_REQUIRED_SECTIONS = ["display", "polling", "anthropic"]


def _interpolate_env_vars(value):
    """Replace ${VAR_NAME} patterns with environment variable values."""
    if not isinstance(value, str):
        return value

    def replacer(match):
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            raise ValueError(
                f"Environment variable {var_name} is not set "
                f"(referenced in config as ${{{var_name}}})"
            )
        return env_val

    return re.sub(r"\$\{(\w+)\}", replacer, value)


def _interpolate_recursive(obj):
    """Walk a nested dict/list and interpolate all string values."""
    if isinstance(obj, dict):
        return {k: _interpolate_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate_recursive(item) for item in obj]
    return _interpolate_env_vars(obj)


def load_config(path: str) -> dict:
    """Load and validate config from a YAML file.

    Interpolates ${VAR} references with environment variables.
    Raises FileNotFoundError if path doesn't exist.
    Raises ValueError if required sections are missing or env vars unset.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    for section in _REQUIRED_SECTIONS:
        if section not in raw:
            raise ValueError(f"Missing required config section: {section}")

    return _interpolate_recursive(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/justin/lakeshore-studio/ai-projects/claude-ledmatrix-status-bar && python -m pytest tests/test_config.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: config module with YAML loading and env var interpolation"
```

---

### Task 3: Layout Module

**Files:**
- Create: `src/layout.py`
- Create: `tests/test_layout.py`

- [ ] **Step 1: Write failing tests for layout helpers and constants**

```python
# tests/test_layout.py
from src.layout import (
    TOTAL_WIDTH,
    TOTAL_HEIGHT,
    DASHBOARD_BOTTOM,
    TICKER_TOP,
    PANEL_WIDTH,
    COLOR_SESSION,
    COLOR_WEEK_ALL,
    COLOR_WEEK_SONNET,
    COLOR_EXTRA,
    COLOR_API,
    COLOR_GRAY,
    COLOR_BAR_BG,
    format_tokens,
    format_dollars,
    compute_bar_width,
    ticker_pages,
    scale_color,
)


def test_display_dimensions():
    assert TOTAL_WIDTH == 192
    assert TOTAL_HEIGHT == 32
    assert PANEL_WIDTH == 64


def test_dashboard_ticker_boundary():
    assert DASHBOARD_BOTTOM == 22
    assert TICKER_TOP == 22


def test_colors_are_rgb_tuples():
    for color in [COLOR_SESSION, COLOR_WEEK_ALL, COLOR_WEEK_SONNET,
                  COLOR_EXTRA, COLOR_API, COLOR_GRAY, COLOR_BAR_BG]:
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)


def test_format_tokens_millions():
    assert format_tokens(1_200_000) == "1.2M"
    assert format_tokens(2_500_000) == "2.5M"


def test_format_tokens_thousands():
    assert format_tokens(410_000) == "410K"
    assert format_tokens(1_500) == "2K"


def test_format_tokens_small():
    assert format_tokens(500) == "500"
    assert format_tokens(0) == "0"


def test_format_dollars():
    assert format_dollars(12.47) == "$12.47"
    assert format_dollars(3.20) == "$3.20"
    assert format_dollars(0.00) == "$0.00"
    assert format_dollars(100.5) == "$101"


def test_compute_bar_width():
    assert compute_bar_width(50, 100) == 50
    assert compute_bar_width(0, 100) == 0
    assert compute_bar_width(100, 100) == 100
    assert compute_bar_width(25, 200) == 50


def test_ticker_pages_even():
    projects = [{"name": f"p{i}"} for i in range(4)]
    pages = ticker_pages(projects, per_page=2)
    assert len(pages) == 2
    assert len(pages[0]) == 2
    assert len(pages[1]) == 2


def test_ticker_pages_odd():
    projects = [{"name": f"p{i}"} for i in range(7)]
    pages = ticker_pages(projects, per_page=2)
    assert len(pages) == 4
    assert len(pages[3]) == 1


def test_ticker_pages_empty():
    assert ticker_pages([], per_page=2) == []


def test_ticker_pages_three_per_page():
    projects = [{"name": f"p{i}"} for i in range(7)]
    pages = ticker_pages(projects, per_page=3)
    assert len(pages) == 3
    assert len(pages[2]) == 1


def test_scale_color():
    assert scale_color((255, 100, 50), 1.0) == (255, 100, 50)
    assert scale_color((255, 100, 50), 0.5) == (127, 50, 25)
    assert scale_color((255, 100, 50), 0.0) == (0, 0, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_layout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.layout'`

- [ ] **Step 3: Implement layout.py**

```python
# src/layout.py
import math

# Display dimensions
PANEL_WIDTH = 64
TOTAL_WIDTH = 192  # 3 panels x 64
TOTAL_HEIGHT = 32

# Region boundaries
DASHBOARD_BOTTOM = 22
TICKER_TOP = 22
TICKER_HEIGHT = TOTAL_HEIGHT - TICKER_TOP  # 10 rows

# Panel X offsets
PANEL1_X = 0
PANEL2_X = 64
PANEL3_X = 128

# Session panel (Panel 1) layout
SESSION_LABEL_X = 14
SESSION_LABEL_Y = 7
SESSION_PCT_X = 12
SESSION_PCT_Y = 17
SESSION_BAR_X = 4
SESSION_BAR_Y = 18
SESSION_BAR_WIDTH = 56
SESSION_BAR_HEIGHT = 2
SESSION_RESET_X = 4
SESSION_RESET_Y = 21

# Weekly panel (Panel 2) layout
WEEKLY_LABEL_X = PANEL2_X + 14
WEEKLY_LABEL_Y = 6
WEEKLY_BAR_LABEL_X = PANEL2_X + 2
WEEKLY_BAR_X = PANEL2_X + 16
WEEKLY_BAR_WIDTH = 32
WEEKLY_BAR_HEIGHT = 2
WEEKLY_PCT_X = PANEL2_X + 50
WEEKLY_ROW_ALL_Y = 10
WEEKLY_ROW_SNT_Y = 14
WEEKLY_ROW_EXT_Y = 18

# API panel (Panel 3) layout
API_LABEL_X = PANEL3_X + 12
API_LABEL_Y = 7
API_SPEND_X = PANEL3_X + 8
API_SPEND_Y = 15
API_TOKENS_X = PANEL3_X + 6
API_TOKENS_Y = 21

# Ticker layout
TICKER_PROJECT_Y_NAME = TICKER_TOP + 4
TICKER_PROJECT_Y_DETAIL = TICKER_TOP + 9
TICKER_DIVIDER_Y = TICKER_TOP
TICKER_COL_WIDTH = 96  # 192 / 2 projects

# Colors (R, G, B)
COLOR_SESSION = (255, 107, 107)
COLOR_WEEK_ALL = (255, 217, 61)
COLOR_WEEK_SONNET = (107, 203, 119)
COLOR_EXTRA = (77, 150, 255)
COLOR_API = (201, 160, 255)
COLOR_GRAY = (128, 128, 128)
COLOR_BAR_BG = (51, 51, 51)
COLOR_DIVIDER = (68, 68, 68)


def format_tokens(tokens: int) -> str:
    """Format token count for display: 1200000 -> '1.2M', 410000 -> '410K'."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{math.ceil(tokens / 1_000)}K"
    return str(tokens)


def format_dollars(amount: float) -> str:
    """Format dollar amount: 12.47 -> '$12.47', 100.5 -> '$101'."""
    if amount >= 100:
        return f"${amount:.0f}"
    return f"${amount:.2f}"


def compute_bar_width(percentage: int, max_width: int) -> int:
    """Compute pixel width of a progress bar given percentage and max width."""
    return int(max_width * percentage / 100)


def ticker_pages(projects: list, per_page: int) -> list:
    """Split project list into pages of per_page items each."""
    if not projects:
        return []
    return [
        projects[i : i + per_page]
        for i in range(0, len(projects), per_page)
    ]


def scale_color(color: tuple, brightness: float) -> tuple:
    """Scale an RGB color tuple by a brightness factor (0.0 to 1.0)."""
    return tuple(int(c * brightness) for c in color)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_layout.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/layout.py tests/test_layout.py
git commit -m "feat: layout module with display constants, colors, and helpers"
```

---

### Task 4: Subscription Collector

**Files:**
- Create: `src/collector.py`
- Create: `tests/test_collector.py`

This task implements the subscription usage collector that spawns a headless Claude Code session via tmux, sends the `/usage` command, and parses the TUI output.

- [ ] **Step 1: Write failing tests for usage output parsing**

```python
# tests/test_collector.py
import pytest

from src.collector import parse_usage_output


# Simulated /usage TUI output after ANSI stripping
SAMPLE_USAGE_OUTPUT = """
 Status  Config  Usage  Stats

 Current session                         10% used
 ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 Resets 7pm (America/New_York)

 Current week (all models)               22% used
 ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░
 Resets Apr 10, 10am (America/New_York)

 Current week (Sonnet only)              9% used
 ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 Resets Apr 9, 3pm (America/New_York)

 Extra usage                             9% used
 ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 $7.13 / $79.00 spent · Resets May 1 (America/New_York)

 Esc to cancel
"""


def test_parse_session_percentage():
    result = parse_usage_output(SAMPLE_USAGE_OUTPUT)
    assert result["session_pct"] == 10


def test_parse_session_reset():
    result = parse_usage_output(SAMPLE_USAGE_OUTPUT)
    assert result["session_reset"] == "7pm"


def test_parse_week_all():
    result = parse_usage_output(SAMPLE_USAGE_OUTPUT)
    assert result["week_all_pct"] == 22
    assert result["week_all_reset"] == "Apr 10, 10am"


def test_parse_week_sonnet():
    result = parse_usage_output(SAMPLE_USAGE_OUTPUT)
    assert result["week_sonnet_pct"] == 9
    assert result["week_sonnet_reset"] == "Apr 9, 3pm"


def test_parse_extra_usage():
    result = parse_usage_output(SAMPLE_USAGE_OUTPUT)
    assert result["extra_spent"] == 7.13
    assert result["extra_limit"] == 79.00


def test_parse_with_ansi_codes():
    """Test that ANSI escape codes are stripped before parsing."""
    ansi_output = (
        "\x1b[1m Current session\x1b[0m"
        "                         \x1b[33m10% used\x1b[0m\n"
        " ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░\n"
        " Resets 7pm (America/New_York)\n"
    )
    result = parse_usage_output(ansi_output)
    assert result["session_pct"] == 10
    assert result["session_reset"] == "7pm"


def test_parse_empty_returns_defaults():
    result = parse_usage_output("")
    assert result["session_pct"] == 0
    assert result["session_reset"] == "--"
    assert result["week_all_pct"] == 0
    assert result["extra_spent"] == 0.0
    assert result["extra_limit"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.collector'`

- [ ] **Step 3: Implement parse_usage_output in collector.py**

```python
# src/collector.py
import re
import subprocess
import time
import logging

logger = logging.getLogger(__name__)

# Default state when data is unavailable
_DEFAULT_SUBSCRIPTION = {
    "session_pct": 0,
    "session_reset": "--",
    "week_all_pct": 0,
    "week_all_reset": "--",
    "week_sonnet_pct": 0,
    "week_sonnet_reset": "--",
    "extra_spent": 0.0,
    "extra_limit": 0.0,
}


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def parse_usage_output(raw_text: str) -> dict:
    """Parse Claude Code /usage TUI output into a structured dict.

    Handles ANSI codes, progress bar characters, and various formatting.
    Returns defaults for any fields that cannot be parsed.
    """
    text = _strip_ansi(raw_text)
    result = dict(_DEFAULT_SUBSCRIPTION)

    # Parse "Current session ... NN% used"
    m = re.search(r"Current session\s+(\d+)%\s+used", text)
    if m:
        result["session_pct"] = int(m.group(1))

    # Parse "Resets TIME (TIMEZONE)" after "Current session"
    m = re.search(
        r"Current session.*?Resets\s+(.+?)\s*\(",
        text,
        re.DOTALL,
    )
    if m:
        result["session_reset"] = m.group(1).strip()

    # Parse "Current week (all models) ... NN% used"
    m = re.search(r"Current week \(all models\)\s+(\d+)%\s+used", text)
    if m:
        result["week_all_pct"] = int(m.group(1))

    m = re.search(
        r"Current week \(all models\).*?Resets\s+(.+?)\s*\(",
        text,
        re.DOTALL,
    )
    if m:
        result["week_all_reset"] = m.group(1).strip()

    # Parse "Current week (Sonnet only) ... NN% used"
    m = re.search(r"Current week \(Sonnet only\)\s+(\d+)%\s+used", text)
    if m:
        result["week_sonnet_pct"] = int(m.group(1))

    m = re.search(
        r"Current week \(Sonnet only\).*?Resets\s+(.+?)\s*\(",
        text,
        re.DOTALL,
    )
    if m:
        result["week_sonnet_reset"] = m.group(1).strip()

    # Parse "Extra usage ... NN% used"
    # and "$X.XX / $Y.YY spent"
    m = re.search(
        r"\$(\d+\.?\d*)\s*/\s*\$(\d+\.?\d*)\s+spent",
        text,
    )
    if m:
        result["extra_spent"] = float(m.group(1))
        result["extra_limit"] = float(m.group(2))

    return result


def fetch_subscription_usage() -> dict:
    """Fetch subscription usage by spawning a Claude Code session in tmux.

    Launches a headless tmux session, runs claude, sends /usage,
    captures the TUI output, parses it, and cleans up.

    Returns parsed usage dict or defaults on failure.
    """
    session_name = f"claude_status_{int(time.time())}"
    tmp_capture = f"/tmp/{session_name}_capture.txt"

    try:
        # Create detached tmux session with large terminal
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name,
             "-x", "200", "-y", "50"],
            check=True,
            timeout=5,
        )

        # Start claude CLI
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "claude", "Enter"],
            check=True,
            timeout=5,
        )

        # Wait for claude to initialize
        time.sleep(8)

        # Send /usage command (Escape dismisses autocomplete, then Enter)
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "/usage", "Escape", "Enter"],
            check=True,
            timeout=5,
        )

        # Wait for usage panel to render
        time.sleep(5)

        # Capture pane output
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        return parse_usage_output(result.stdout)

    except Exception as e:
        logger.error(f"Failed to fetch subscription usage: {e}")
        return dict(_DEFAULT_SUBSCRIPTION)

    finally:
        # Clean up tmux session
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True,
            timeout=5,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_collector.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/collector.py tests/test_collector.py
git commit -m "feat: subscription collector with tmux-based CLI scraping and output parser"
```

---

### Task 5: API Collector

**Files:**
- Modify: `src/collector.py` (add API collection functions)
- Modify: `tests/test_collector.py` (add API tests)

Uses the Anthropic Admin API:
- `GET /v1/organizations/usage_report/messages` — per-key token counts
- `GET /v1/organizations/cost_report` — total org cost

- [ ] **Step 1: Write failing tests for API data fetching**

Add to `tests/test_collector.py`:

```python
from unittest.mock import patch, MagicMock
from src.collector import fetch_api_usage, parse_usage_response, parse_cost_response


SAMPLE_USAGE_RESPONSE = {
    "data": [
        {
            "bucket_start_time": "2026-04-01T00:00:00Z",
            "api_key_id": "apikey_01ABC",
            "input_tokens": 200_000,
            "output_tokens": 150_000,
            "cache_creation_input_tokens": 10_000,
            "cache_read_input_tokens": 50_000,
        },
        {
            "bucket_start_time": "2026-04-01T00:00:00Z",
            "api_key_id": "apikey_02DEF",
            "input_tokens": 100_000,
            "output_tokens": 80_000,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        {
            "bucket_start_time": "2026-04-02T00:00:00Z",
            "api_key_id": "apikey_01ABC",
            "input_tokens": 30_000,
            "output_tokens": 20_000,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    ],
    "has_more": False,
}


SAMPLE_COST_RESPONSE = {
    "data": [
        {
            "bucket_start_time": "2026-04-01T00:00:00Z",
            "cost_usd": "8.50",
        },
        {
            "bucket_start_time": "2026-04-02T00:00:00Z",
            "cost_usd": "3.97",
        },
    ],
    "has_more": False,
}


def test_parse_usage_response_aggregates_by_key():
    result = parse_usage_response(SAMPLE_USAGE_RESPONSE)
    assert result["apikey_01ABC"] == 200_000 + 150_000 + 10_000 + 50_000 + 30_000 + 20_000
    assert result["apikey_02DEF"] == 100_000 + 80_000


def test_parse_cost_response_sums_total():
    result = parse_cost_response(SAMPLE_COST_RESPONSE)
    assert abs(result - 12.47) < 0.01


def test_fetch_api_usage_combines_data(sample_config):
    mock_usage_resp = MagicMock()
    mock_usage_resp.status_code = 200
    mock_usage_resp.json.return_value = SAMPLE_USAGE_RESPONSE

    mock_cost_resp = MagicMock()
    mock_cost_resp.status_code = 200
    mock_cost_resp.json.return_value = SAMPLE_COST_RESPONSE

    with patch("src.collector.requests.get") as mock_get:
        mock_get.side_effect = [mock_usage_resp, mock_cost_resp]
        result = fetch_api_usage(sample_config["anthropic"])

    assert result["total_spend"] == pytest.approx(12.47, abs=0.01)
    assert result["total_tokens"] == 200_000 + 150_000 + 10_000 + 50_000 + 30_000 + 20_000 + 100_000 + 80_000
    assert len(result["projects"]) == 2
    assert result["projects"][0]["name"] == "tastytrade-bot"
    assert result["projects"][0]["tokens"] == 200_000 + 150_000 + 10_000 + 50_000 + 30_000 + 20_000


def test_fetch_api_usage_allocates_cost_proportionally(sample_config):
    mock_usage_resp = MagicMock()
    mock_usage_resp.status_code = 200
    mock_usage_resp.json.return_value = SAMPLE_USAGE_RESPONSE

    mock_cost_resp = MagicMock()
    mock_cost_resp.status_code = 200
    mock_cost_resp.json.return_value = SAMPLE_COST_RESPONSE

    with patch("src.collector.requests.get") as mock_get:
        mock_get.side_effect = [mock_usage_resp, mock_cost_resp]
        result = fetch_api_usage(sample_config["anthropic"])

    total_tokens = result["total_tokens"]
    for project in result["projects"]:
        expected_spend = result["total_spend"] * project["tokens"] / total_tokens
        assert project["spend"] == pytest.approx(expected_spend, abs=0.01)


def test_fetch_api_usage_handles_error(sample_config):
    with patch("src.collector.requests.get") as mock_get:
        mock_get.side_effect = Exception("Connection error")
        result = fetch_api_usage(sample_config["anthropic"])

    assert result["total_spend"] == 0.0
    assert result["total_tokens"] == 0
    assert result["projects"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_collector.py -v -k "api"`
Expected: FAIL — `ImportError: cannot import name 'fetch_api_usage'`

- [ ] **Step 3: Implement API collector functions in collector.py**

Add the following to `src/collector.py`:

```python
import requests
from datetime import datetime, timedelta, timezone


_DEFAULT_API = {
    "total_spend": 0.0,
    "total_tokens": 0,
    "projects": [],
}

_ANTHROPIC_API_BASE = "https://api.anthropic.com/v1/organizations"


def parse_usage_response(response_data: dict) -> dict:
    """Parse usage API response into per-key total token counts.

    Returns dict mapping api_key_id -> total_tokens (sum of all token types).
    """
    key_tokens = {}
    for bucket in response_data.get("data", []):
        key_id = bucket.get("api_key_id")
        if key_id is None:
            continue
        tokens = (
            bucket.get("input_tokens", 0)
            + bucket.get("output_tokens", 0)
            + bucket.get("cache_creation_input_tokens", 0)
            + bucket.get("cache_read_input_tokens", 0)
        )
        key_tokens[key_id] = key_tokens.get(key_id, 0) + tokens
    return key_tokens


def parse_cost_response(response_data: dict) -> float:
    """Parse cost API response into total USD spend.

    Returns total cost as a float.
    """
    total = 0.0
    for bucket in response_data.get("data", []):
        total += float(bucket.get("cost_usd", "0"))
    return total


def fetch_api_usage(anthropic_config: dict) -> dict:
    """Fetch API usage and cost data from Anthropic Admin API.

    Calls the usage endpoint (grouped by api_key_id) for per-key token counts,
    and the cost endpoint for total org spend. Per-project spend is estimated
    proportionally by token count.

    Returns dict with total_spend, total_tokens, and projects list.
    """
    admin_key = anthropic_config["admin_api_key"]
    projects_config = anthropic_config["api_projects"]
    headers = {
        "anthropic-version": "2023-06-01",
        "x-api-key": admin_key,
    }

    now = datetime.now(timezone.utc)
    # Query the current month's data
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    starting_at = start_of_month.strftime("%Y-%m-%dT%H:%M:%SZ")
    ending_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        # Fetch per-key usage
        usage_resp = requests.get(
            f"{_ANTHROPIC_API_BASE}/usage_report/messages",
            headers=headers,
            params={
                "starting_at": starting_at,
                "ending_at": ending_at,
                "group_by[]": "api_key_id",
                "bucket_width": "1d",
                "limit": 31,
            },
            timeout=30,
        )
        usage_resp.raise_for_status()
        key_tokens = parse_usage_response(usage_resp.json())

        # Fetch total cost
        cost_resp = requests.get(
            f"{_ANTHROPIC_API_BASE}/cost_report",
            headers=headers,
            params={
                "starting_at": starting_at,
                "ending_at": ending_at,
                "bucket_width": "1d",
                "limit": 31,
            },
            timeout=30,
        )
        cost_resp.raise_for_status()
        total_spend = parse_cost_response(cost_resp.json())

        # Map API key IDs to project names and compute proportional spend
        total_tokens = sum(key_tokens.values())
        projects = []
        for proj in projects_config:
            tokens = key_tokens.get(proj["api_key_id"], 0)
            spend = (
                total_spend * tokens / total_tokens
                if total_tokens > 0
                else 0.0
            )
            projects.append({
                "name": proj["name"],
                "spend": round(spend, 2),
                "tokens": tokens,
            })

        return {
            "total_spend": round(total_spend, 2),
            "total_tokens": total_tokens,
            "projects": projects,
        }

    except Exception as e:
        logger.error(f"Failed to fetch API usage: {e}")
        return dict(_DEFAULT_API)
```

- [ ] **Step 4: Run all collector tests**

Run: `python -m pytest tests/test_collector.py -v`
Expected: All 12 tests PASS (8 subscription + 4 API)

- [ ] **Step 5: Commit**

```bash
git add src/collector.py tests/test_collector.py
git commit -m "feat: API collector with Anthropic Admin API usage and cost fetching"
```

---

### Task 6: Collector Thread Manager

**Files:**
- Modify: `src/collector.py` (add thread runner)
- Modify: `tests/test_collector.py` (add thread tests)

- [ ] **Step 1: Write failing tests for the collector thread**

Add to `tests/test_collector.py`:

```python
import threading
from unittest.mock import patch
from src.collector import CollectorThread


def test_collector_thread_updates_state():
    state = {}
    lock = threading.Lock()

    sub_data = {
        "session_pct": 15,
        "session_reset": "8pm",
        "week_all_pct": 30,
        "week_all_reset": "Apr 11",
        "week_sonnet_pct": 12,
        "week_sonnet_reset": "Apr 10",
        "extra_spent": 10.0,
        "extra_limit": 79.0,
    }
    api_data = {
        "total_spend": 5.0,
        "total_tokens": 500_000,
        "projects": [{"name": "test", "spend": 5.0, "tokens": 500_000}],
    }

    with patch("src.collector.fetch_subscription_usage", return_value=sub_data), \
         patch("src.collector.fetch_api_usage", return_value=api_data):
        config = {
            "polling": {
                "subscription_interval_seconds": 180,
                "api_interval_seconds": 300,
            },
            "anthropic": {"admin_api_key": "test", "api_projects": []},
        }
        thread = CollectorThread(config, state, lock)
        thread.daemon = True
        thread.start()
        # Wait for first collection cycle
        time.sleep(1)
        thread.stop()
        thread.join(timeout=5)

    with lock:
        assert state["subscription"]["session_pct"] == 15
        assert state["api"]["total_spend"] == 5.0
        assert "last_updated" in state


def test_collector_thread_stops_cleanly():
    state = {}
    lock = threading.Lock()

    with patch("src.collector.fetch_subscription_usage", return_value=_DEFAULT_SUBSCRIPTION), \
         patch("src.collector.fetch_api_usage", return_value=_DEFAULT_API):
        config = {
            "polling": {
                "subscription_interval_seconds": 180,
                "api_interval_seconds": 300,
            },
            "anthropic": {"admin_api_key": "test", "api_projects": []},
        }
        thread = CollectorThread(config, state, lock)
        thread.daemon = True
        thread.start()
        time.sleep(0.5)
        thread.stop()
        thread.join(timeout=5)

    assert not thread.is_alive()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_collector.py -v -k "thread"`
Expected: FAIL — `ImportError: cannot import name 'CollectorThread'`

- [ ] **Step 3: Implement CollectorThread in collector.py**

Add to `src/collector.py`:

```python
from datetime import datetime


class CollectorThread(threading.Thread):
    """Background thread that periodically fetches usage data."""

    def __init__(self, config: dict, state: dict, lock: threading.Lock):
        super().__init__(name="collector")
        self.config = config
        self.state = state
        self.lock = lock
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        sub_interval = self.config["polling"]["subscription_interval_seconds"]
        api_interval = self.config["polling"]["api_interval_seconds"]

        last_sub_fetch = 0.0
        last_api_fetch = 0.0

        while not self._stop_event.is_set():
            now = time.time()

            # Fetch subscription data if interval elapsed
            if now - last_sub_fetch >= sub_interval or last_sub_fetch == 0:
                logger.info("Fetching subscription usage...")
                sub_data = fetch_subscription_usage()
                last_sub_fetch = now

                with self.lock:
                    self.state["subscription"] = sub_data
                    self.state["last_updated"] = datetime.now().isoformat()

            # Fetch API data if interval elapsed
            if now - last_api_fetch >= api_interval or last_api_fetch == 0:
                logger.info("Fetching API usage...")
                api_data = fetch_api_usage(self.config["anthropic"])
                last_api_fetch = now

                with self.lock:
                    self.state["api"] = api_data
                    self.state["last_updated"] = datetime.now().isoformat()

            # Sleep in short increments so stop() is responsive
            self._stop_event.wait(timeout=5)
```

- [ ] **Step 4: Run all collector tests**

Run: `python -m pytest tests/test_collector.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/collector.py tests/test_collector.py
git commit -m "feat: collector thread manager with interval-based data fetching"
```

---

### Task 7: Renderer — Top Dashboard

**Files:**
- Create: `src/renderer.py`
- Create: `tests/test_renderer.py`

The renderer drives the LED matrix. For testability, drawing functions accept a canvas-like object and a mock graphics module.

- [ ] **Step 1: Write failing tests for renderer setup and dashboard drawing**

```python
# tests/test_renderer.py
import pytest
from unittest.mock import MagicMock, call

from src.renderer import draw_session_panel, draw_weekly_panel, draw_api_panel, draw_divider
from src import layout


@pytest.fixture
def mock_canvas():
    canvas = MagicMock()
    canvas.width = layout.TOTAL_WIDTH
    canvas.height = layout.TOTAL_HEIGHT
    return canvas


@pytest.fixture
def mock_graphics():
    gfx = MagicMock()
    gfx.Color = lambda r, g, b: (r, g, b)
    gfx.DrawText = MagicMock(return_value=0)
    gfx.DrawLine = MagicMock()
    return gfx


@pytest.fixture
def mock_fonts():
    return {"large": MagicMock(), "small": MagicMock()}


def test_draw_session_panel_draws_label(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_session_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    calls = mock_graphics.DrawText.call_args_list
    labels = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "SESSION" in labels


def test_draw_session_panel_draws_percentage(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_session_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "10%" in texts


def test_draw_session_panel_draws_bar(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_session_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    # Bar is drawn via SetPixel calls for filled portion and background
    assert mock_canvas.SetPixel.called


def test_draw_session_panel_draws_reset_time(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_session_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert any("7pm" in t for t in texts)


def test_draw_weekly_panel_draws_three_bars(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_weekly_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "WEEKLY" in texts
    assert "ALL" in texts
    assert "SNT" in texts
    assert "EXT" in texts


def test_draw_api_panel_draws_spend(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_api_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["api"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "$12.47" in texts


def test_draw_api_panel_draws_tokens(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_api_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["api"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "1.2M tk" in texts


def test_draw_divider(mock_canvas, mock_graphics):
    draw_divider(mock_canvas, mock_graphics)
    mock_graphics.DrawLine.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_renderer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.renderer'`

- [ ] **Step 3: Implement renderer.py with dashboard drawing functions**

```python
# src/renderer.py
import time
import logging

from src import layout

logger = logging.getLogger(__name__)


def _draw_bar(canvas, x, y, width, height, percentage, fg_color, bg_color):
    """Draw a progress bar with filled and background portions."""
    filled_width = layout.compute_bar_width(percentage, width)
    for row in range(height):
        for col in range(width):
            if col < filled_width:
                canvas.SetPixel(x + col, y + row, *fg_color)
            else:
                canvas.SetPixel(x + col, y + row, *bg_color)


def draw_session_panel(canvas, graphics, fonts, subscription):
    """Draw the session usage panel on Panel 1 (leftmost 64px)."""
    color_session = graphics.Color(*layout.COLOR_SESSION)
    color_gray = graphics.Color(*layout.COLOR_GRAY)

    # Label
    graphics.DrawText(
        canvas, fonts["small"],
        layout.SESSION_LABEL_X, layout.SESSION_LABEL_Y,
        color_session, "SESSION",
    )

    # Large percentage
    pct_text = f"{subscription['session_pct']}%"
    graphics.DrawText(
        canvas, fonts["large"],
        layout.SESSION_PCT_X, layout.SESSION_PCT_Y,
        color_session, pct_text,
    )

    # Progress bar
    _draw_bar(
        canvas,
        layout.SESSION_BAR_X, layout.SESSION_BAR_Y,
        layout.SESSION_BAR_WIDTH, layout.SESSION_BAR_HEIGHT,
        subscription["session_pct"],
        layout.COLOR_SESSION, layout.COLOR_BAR_BG,
    )

    # Reset time
    reset_text = f"~{subscription['session_reset']}"
    graphics.DrawText(
        canvas, fonts["small"],
        layout.SESSION_RESET_X, layout.SESSION_RESET_Y,
        color_gray, reset_text,
    )


def draw_weekly_panel(canvas, graphics, fonts, subscription):
    """Draw weekly usage bars on Panel 2 (middle 64px)."""
    color_all = graphics.Color(*layout.COLOR_WEEK_ALL)
    color_snt = graphics.Color(*layout.COLOR_WEEK_SONNET)
    color_ext = graphics.Color(*layout.COLOR_EXTRA)
    color_gray = graphics.Color(*layout.COLOR_GRAY)

    # Header
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_LABEL_X, layout.WEEKLY_LABEL_Y,
        color_all, "WEEKLY",
    )

    # ALL bar
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_BAR_LABEL_X, layout.WEEKLY_ROW_ALL_Y,
        color_all, "ALL",
    )
    _draw_bar(
        canvas,
        layout.WEEKLY_BAR_X, layout.WEEKLY_ROW_ALL_Y - 1,
        layout.WEEKLY_BAR_WIDTH, layout.WEEKLY_BAR_HEIGHT,
        subscription["week_all_pct"],
        layout.COLOR_WEEK_ALL, layout.COLOR_BAR_BG,
    )
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_PCT_X, layout.WEEKLY_ROW_ALL_Y,
        color_all, f"{subscription['week_all_pct']}%",
    )

    # SNT bar
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_BAR_LABEL_X, layout.WEEKLY_ROW_SNT_Y,
        color_snt, "SNT",
    )
    _draw_bar(
        canvas,
        layout.WEEKLY_BAR_X, layout.WEEKLY_ROW_SNT_Y - 1,
        layout.WEEKLY_BAR_WIDTH, layout.WEEKLY_BAR_HEIGHT,
        subscription["week_sonnet_pct"],
        layout.COLOR_WEEK_SONNET, layout.COLOR_BAR_BG,
    )
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_PCT_X, layout.WEEKLY_ROW_SNT_Y,
        color_snt, f"{subscription['week_sonnet_pct']}%",
    )

    # EXT bar
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_BAR_LABEL_X, layout.WEEKLY_ROW_EXT_Y,
        color_ext, "EXT",
    )
    _draw_bar(
        canvas,
        layout.WEEKLY_BAR_X, layout.WEEKLY_ROW_EXT_Y - 1,
        layout.WEEKLY_BAR_WIDTH, layout.WEEKLY_BAR_HEIGHT,
        subscription["extra_spent"] / max(subscription["extra_limit"], 1) * 100,
        layout.COLOR_EXTRA, layout.COLOR_BAR_BG,
    )
    ext_text = f"${subscription['extra_spent']:.0f}/${subscription['extra_limit']:.0f}"
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_PCT_X - 4, layout.WEEKLY_ROW_EXT_Y,
        color_ext, ext_text,
    )


def draw_api_panel(canvas, graphics, fonts, api_state):
    """Draw API total spend on Panel 3 (rightmost 64px)."""
    color_api = graphics.Color(*layout.COLOR_API)
    color_gray = graphics.Color(*layout.COLOR_GRAY)

    # Label
    graphics.DrawText(
        canvas, fonts["small"],
        layout.API_LABEL_X, layout.API_LABEL_Y,
        color_api, "API TOTAL",
    )

    # Large dollar amount
    spend_text = layout.format_dollars(api_state["total_spend"])
    graphics.DrawText(
        canvas, fonts["large"],
        layout.API_SPEND_X, layout.API_SPEND_Y,
        color_api, spend_text,
    )

    # Token count
    tokens_text = f"{layout.format_tokens(api_state['total_tokens'])} tk"
    graphics.DrawText(
        canvas, fonts["small"],
        layout.API_TOKENS_X, layout.API_TOKENS_Y,
        color_gray, tokens_text,
    )


def draw_divider(canvas, graphics):
    """Draw horizontal divider line between dashboard and ticker."""
    color = graphics.Color(*layout.COLOR_DIVIDER)
    graphics.DrawLine(
        canvas, 0, layout.DASHBOARD_BOTTOM - 1,
        layout.TOTAL_WIDTH - 1, layout.DASHBOARD_BOTTOM - 1,
        color,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_renderer.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: renderer top dashboard with session, weekly, and API panels"
```

---

### Task 8: Renderer — Bottom Ticker with Fade

**Files:**
- Modify: `src/renderer.py` (add ticker class)
- Modify: `tests/test_renderer.py` (add ticker tests)

- [ ] **Step 1: Write failing tests for the ticker**

Add to `tests/test_renderer.py`:

```python
from src.renderer import Ticker


def test_ticker_init():
    ticker = Ticker(cycle_seconds=4, fade_frames=15, projects_per_page=2)
    assert ticker.current_page == 0
    assert ticker.fade_progress is None


def test_ticker_page_cycling():
    ticker = Ticker(cycle_seconds=0.1, fade_frames=2, projects_per_page=2)
    projects = [
        {"name": "p1", "spend": 1.0, "tokens": 100},
        {"name": "p2", "spend": 2.0, "tokens": 200},
        {"name": "p3", "spend": 3.0, "tokens": 300},
        {"name": "p4", "spend": 4.0, "tokens": 400},
    ]
    pages = layout.ticker_pages(projects, per_page=2)

    # Start on page 0
    assert ticker.current_page == 0

    # After enough time, should advance
    ticker.last_cycle_time = time.time() - 1  # force cycle
    ticker.update(len(pages))
    # Should be fading or on next page
    assert ticker.fade_progress is not None or ticker.current_page == 1


def test_ticker_fade_brightness():
    ticker = Ticker(cycle_seconds=4, fade_frames=10, projects_per_page=2)
    # During fade-out (progress 0 to 0.5), brightness goes from 1.0 to 0.0
    assert ticker.get_brightness(0.0) == 1.0
    assert ticker.get_brightness(0.5) == 0.0
    # During fade-in (progress 0.5 to 1.0), brightness goes from 0.0 to 1.0
    assert ticker.get_brightness(1.0) == 1.0


def test_ticker_wraps_around():
    ticker = Ticker(cycle_seconds=0.1, fade_frames=2, projects_per_page=2)
    ticker.current_page = 2
    ticker.last_cycle_time = time.time() - 1
    ticker.update(total_pages=3)
    # After fading, should wrap to 0
    ticker.fade_progress = None
    ticker.current_page = 3
    ticker.update(total_pages=3)
    assert ticker.current_page == 0


def test_draw_ticker_page(mock_canvas, mock_graphics, mock_fonts, sample_state):
    from src.renderer import draw_ticker_page
    projects_page = sample_state["api"]["projects"][:2]
    draw_ticker_page(mock_canvas, mock_graphics, mock_fonts, projects_page, brightness=1.0)
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "tastytrade-bot" in texts
    assert "diy-helper" in texts


def test_draw_ticker_page_with_dim_brightness(mock_canvas, mock_graphics, mock_fonts, sample_state):
    from src.renderer import draw_ticker_page
    projects_page = sample_state["api"]["projects"][:2]
    draw_ticker_page(mock_canvas, mock_graphics, mock_fonts, projects_page, brightness=0.5)
    # Colors should be scaled down — check that Color was called with dimmed values
    color_calls = [c for c in mock_graphics.Color.call_args_list]
    # At least some colors should have values less than the full COLOR_API
    dimmed = any(
        c.args[0] < layout.COLOR_API[0] for c in color_calls
        if len(c.args) >= 1 and isinstance(c.args[0], int)
    )
    assert dimmed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_renderer.py -v -k "ticker"`
Expected: FAIL — `ImportError: cannot import name 'Ticker'`

- [ ] **Step 3: Implement Ticker class and draw_ticker_page**

Add to `src/renderer.py`:

```python
class Ticker:
    """Manages page cycling and fade transitions for the bottom ticker."""

    def __init__(self, cycle_seconds: float, fade_frames: int, projects_per_page: int):
        self.cycle_seconds = cycle_seconds
        self.fade_frames = fade_frames
        self.projects_per_page = projects_per_page
        self.current_page = 0
        self.fade_progress = None  # None = not fading, 0.0-1.0 = fading
        self.last_cycle_time = time.time()
        self._fade_frame = 0

    def update(self, total_pages: int):
        """Called each frame. Manages page cycling and fade state."""
        if total_pages == 0:
            return

        now = time.time()

        if self.fade_progress is not None:
            # Currently fading
            self._fade_frame += 1
            self.fade_progress = self._fade_frame / (self.fade_frames * 2)

            if self.fade_progress >= 0.5 and self.current_page == self._pre_fade_page:
                # Halfway through fade — swap page
                self.current_page = (self.current_page + 1) % total_pages

            if self.fade_progress >= 1.0:
                # Fade complete
                self.fade_progress = None
                self._fade_frame = 0
                self.last_cycle_time = now
        else:
            # Check if it's time to start a new cycle
            if now - self.last_cycle_time >= self.cycle_seconds:
                self.fade_progress = 0.0
                self._fade_frame = 0
                self._pre_fade_page = self.current_page

    def get_brightness(self, progress: float) -> float:
        """Get brightness factor (0.0-1.0) for a given fade progress.

        First half (0.0-0.5): fade out (1.0 -> 0.0)
        Second half (0.5-1.0): fade in (0.0 -> 1.0)
        """
        if progress <= 0.5:
            return 1.0 - (progress * 2)
        return (progress - 0.5) * 2


def draw_ticker_page(canvas, graphics, fonts, projects_page, brightness=1.0):
    """Draw a single page of projects in the ticker area."""
    if not projects_page:
        return

    col_width = layout.TOTAL_WIDTH // max(len(projects_page), 1)

    for i, project in enumerate(projects_page):
        x_offset = i * col_width
        center_x = x_offset + col_width // 2

        # Project name (centered-ish)
        name_color = layout.scale_color(layout.COLOR_API, brightness)
        color = graphics.Color(*name_color)
        name = project["name"]
        # Estimate text width (4px per char for small font)
        name_x = center_x - (len(name) * 4 // 2)
        graphics.DrawText(
            canvas, fonts["small"],
            name_x, layout.TICKER_PROJECT_Y_NAME,
            color, name,
        )

        # Spend + tokens
        detail_color = layout.scale_color(layout.COLOR_GRAY, brightness)
        color = graphics.Color(*detail_color)
        detail = f"{layout.format_dollars(project['spend'])} {layout.format_tokens(project['tokens'])} tk"
        detail_x = center_x - (len(detail) * 4 // 2)
        graphics.DrawText(
            canvas, fonts["small"],
            detail_x, layout.TICKER_PROJECT_Y_DETAIL,
            color, detail,
        )
```

- [ ] **Step 4: Run all renderer tests**

Run: `python -m pytest tests/test_renderer.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: bottom ticker with fade transitions and page cycling"
```

---

### Task 9: Main Entry Point

**Files:**
- Create: `src/main.py`

This wires everything together: config loading, matrix initialization, collector thread, and render loop. Since it depends on rgbmatrix hardware, it's tested manually on the Pi.

- [ ] **Step 1: Implement main.py**

```python
# src/main.py
import argparse
import copy
import json
import logging
import signal
import sys
import threading
import time

from src.config import load_config
from src.collector import CollectorThread
from src import layout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Initial empty state
_INITIAL_STATE = {
    "subscription": {
        "session_pct": 0,
        "session_reset": "--",
        "week_all_pct": 0,
        "week_all_reset": "--",
        "week_sonnet_pct": 0,
        "week_sonnet_reset": "--",
        "extra_spent": 0.0,
        "extra_limit": 0.0,
    },
    "api": {
        "total_spend": 0.0,
        "total_tokens": 0,
        "projects": [],
    },
    "last_updated": None,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Claude LED Matrix Status Bar")
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print state to console instead of driving LEDs (no rgbmatrix needed)",
    )
    return parser.parse_args()


def run_dry_mode(config, state, lock):
    """Print state to console periodically instead of rendering to LEDs."""
    logger.info("Running in dry-run mode (no LED output)")
    try:
        while True:
            with lock:
                snapshot = copy.deepcopy(state)
            print("\033[2J\033[H")  # Clear terminal
            print("=== Claude LED Status Bar (dry-run) ===\n")
            print(json.dumps(snapshot, indent=2, default=str))
            time.sleep(2)
    except KeyboardInterrupt:
        pass


def run_led_mode(config, state, lock):
    """Main render loop driving the LED matrix."""
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
    from src.renderer import (
        draw_session_panel, draw_weekly_panel, draw_api_panel,
        draw_divider, draw_ticker_page, Ticker,
    )

    # Configure matrix
    options = RGBMatrixOptions()
    options.rows = config["display"]["rows"]
    options.cols = config["display"]["cols_per_panel"]
    options.chain_length = config["display"]["panels"]
    options.parallel = 1
    options.hardware_mapping = config["display"]["gpio_mapping"]
    options.gpio_slowdown = config["display"]["gpio_slowdown"]
    options.brightness = config["display"]["brightness"]
    options.drop_privileges = False

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()

    # Load fonts
    fonts = {
        "large": graphics.Font(),
        "small": graphics.Font(),
    }
    fonts["large"].LoadFont("fonts/7x13.bdf")
    fonts["small"].LoadFont("fonts/4x6.bdf")

    # Initialize ticker
    ticker = Ticker(
        cycle_seconds=config["display"]["ticker_cycle_seconds"],
        fade_frames=config["display"]["ticker_fade_frames"],
        projects_per_page=config["display"]["ticker_projects_per_page"],
    )

    logger.info("LED matrix initialized. Starting render loop.")

    try:
        while True:
            canvas.Clear()

            # Get state snapshot
            with lock:
                snapshot = copy.deepcopy(state)

            # Draw top dashboard
            draw_session_panel(canvas, graphics, fonts, snapshot["subscription"])
            draw_weekly_panel(canvas, graphics, fonts, snapshot["subscription"])
            draw_api_panel(canvas, graphics, fonts, snapshot["api"])
            draw_divider(canvas, graphics)

            # Draw bottom ticker
            projects = snapshot["api"].get("projects", [])
            pages = layout.ticker_pages(projects, ticker.projects_per_page)
            ticker.update(len(pages))

            if pages:
                brightness = 1.0
                if ticker.fade_progress is not None:
                    brightness = ticker.get_brightness(ticker.fade_progress)

                current_projects = pages[ticker.current_page]
                draw_ticker_page(canvas, graphics, fonts, current_projects, brightness)

            # Swap buffer
            canvas = matrix.SwapOnVSync(canvas)

    except KeyboardInterrupt:
        logger.info("Shutting down LED matrix.")
        matrix.Clear()


def main():
    args = parse_args()

    # Load config
    config = load_config(args.config)
    logger.info(f"Config loaded from {args.config}")

    # Shared state
    state = copy.deepcopy(_INITIAL_STATE)
    lock = threading.Lock()

    # Start collector thread
    collector = CollectorThread(config, state, lock)
    collector.daemon = True
    collector.start()
    logger.info("Collector thread started.")

    # Handle shutdown
    def shutdown(signum, frame):
        logger.info("Received shutdown signal.")
        collector.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Run display
    if args.dry_run:
        run_dry_mode(config, state, lock)
    else:
        run_led_mode(config, state, lock)

    collector.stop()
    collector.join(timeout=10)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test dry-run mode locally**

Run: `python -m src.main --dry-run -c config.example.yaml`

You'll need to set the `ANTHROPIC_ADMIN_KEY` env var first (or temporarily hardcode a test key in config.example.yaml). The dry-run should print the JSON state to the terminal, updating every 2 seconds as the collector fetches data.

Expected: Terminal shows the state dict updating. Subscription data may show defaults if tmux/claude aren't available locally.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: main entry point with dry-run mode and LED render loop"
```

---

### Task 10: Deployment Files

**Files:**
- Create: `claude-status-bar.service`
- Create: `claude-status-bar.env.example`
- Create: `install.sh`

- [ ] **Step 1: Create systemd service file**

```ini
# claude-status-bar.service
[Unit]
Description=Claude LED Matrix Status Bar
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/claude-ledmatrix-status-bar
EnvironmentFile=/etc/claude-status-bar.env
ExecStart=/usr/bin/python3 -m src.main -c config.yaml
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create environment file template**

```bash
# claude-status-bar.env.example
# Copy to /etc/claude-status-bar.env and fill in values
ANTHROPIC_ADMIN_KEY=sk-ant-admin-your-key-here
```

- [ ] **Step 3: Create install script**

```bash
#!/usr/bin/env bash
# install.sh — Install Claude LED Matrix Status Bar on Raspberry Pi
set -euo pipefail

INSTALL_DIR="/opt/claude-ledmatrix-status-bar"
RPI_RGB_DIR="/opt/rpi-rgb-led-matrix"
SERVICE_NAME="claude-status-bar"

echo "=== Claude LED Matrix Status Bar Installer ==="
echo ""

# Check for root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (sudo ./install.sh)"
    exit 1
fi

# Install system dependencies
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-dev tmux git

# Check for claude CLI
if ! command -v claude &> /dev/null; then
    echo ""
    echo "WARNING: Claude Code CLI not found."
    echo "Install it before running the service:"
    echo "  npm install -g @anthropic-ai/claude-code"
    echo "  claude auth login"
    echo ""
fi

# Build rpi-rgb-led-matrix if not present
if [[ ! -d "$RPI_RGB_DIR" ]]; then
    echo "[2/7] Building rpi-rgb-led-matrix..."
    cd /opt
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd rpi-rgb-led-matrix
    make build-python PYTHON=$(which python3)
    make install-python PYTHON=$(which python3)
else
    echo "[2/7] rpi-rgb-led-matrix already installed, skipping."
fi

# Copy project files
echo "[3/7] Installing project files..."
mkdir -p "$INSTALL_DIR"
cp -r src/ "$INSTALL_DIR/"
cp requirements.txt config.example.yaml "$INSTALL_DIR/"

# Symlink fonts
echo "[4/7] Linking fonts..."
ln -sfn "$RPI_RGB_DIR/fonts" "$INSTALL_DIR/fonts"

# Install Python dependencies
echo "[5/7] Installing Python dependencies..."
pip3 install -r "$INSTALL_DIR/requirements.txt"

# Set up config
if [[ ! -f "$INSTALL_DIR/config.yaml" ]]; then
    echo "[6/7] Creating config..."
    cp "$INSTALL_DIR/config.example.yaml" "$INSTALL_DIR/config.yaml"
    echo "  Edit $INSTALL_DIR/config.yaml with your API project details."
else
    echo "[6/7] Config already exists, skipping."
fi

# Set up environment file
if [[ ! -f /etc/claude-status-bar.env ]]; then
    cp claude-status-bar.env.example /etc/claude-status-bar.env
    chmod 600 /etc/claude-status-bar.env
    echo ""
    echo "  IMPORTANT: Edit /etc/claude-status-bar.env with your Anthropic admin API key."
    echo ""
fi

# Install and enable systemd service
echo "[7/7] Installing systemd service..."
cp claude-status-bar.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /opt/claude-ledmatrix-status-bar/config.yaml"
echo "     - Set gpio_mapping to match your wiring"
echo "     - Add your API projects with api_key_ids"
echo "  2. Edit /etc/claude-status-bar.env"
echo "     - Set ANTHROPIC_ADMIN_KEY to your admin API key"
echo "  3. Make sure claude CLI is authenticated:"
echo "     - Run: claude auth login"
echo "  4. Start the service:"
echo "     - sudo systemctl start $SERVICE_NAME"
echo "  5. Check status:"
echo "     - sudo systemctl status $SERVICE_NAME"
echo "     - sudo journalctl -u $SERVICE_NAME -f"
```

- [ ] **Step 4: Make install script executable**

```bash
chmod +x install.sh
```

- [ ] **Step 5: Commit**

```bash
git add claude-status-bar.service claude-status-bar.env.example install.sh
git commit -m "feat: deployment files — systemd service, env template, install script"
```

---

## Post-Implementation Checklist

After all tasks are complete:

- [ ] Run full test suite: `python -m pytest tests/ -v`
- [ ] Test dry-run mode: `python -m src.main --dry-run -c config.example.yaml`
- [ ] Deploy to Pi: `sudo ./install.sh`
- [ ] Verify config.yaml matches your GPIO wiring (adjust `gpio_mapping` and `gpio_slowdown`)
- [ ] Verify fonts render at the right size (adjust layout constants in `layout.py` if needed)
- [ ] Verify ticker cycling and fade transitions look smooth
- [ ] Check `sudo journalctl -u claude-status-bar -f` for errors
