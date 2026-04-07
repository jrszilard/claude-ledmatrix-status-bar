import re
import subprocess
import threading
import time
import logging
from datetime import datetime, timezone

import requests

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

_DEFAULT_API = {
    "total_spend": 0.0,
    "total_tokens": 0,
    "projects": [],
}

_ANTHROPIC_API_BASE = "https://api.anthropic.com/v1/organizations"


# --- Subscription Usage (Claude Code CLI via tmux) ---


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

    # Parse "$X.XX / $Y.YY spent"
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


# --- API Usage (Anthropic Admin API) ---


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


# --- Thread Manager ---


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
