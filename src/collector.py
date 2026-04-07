import threading
import time
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_DEFAULT_API = {
    "total_spend": 0.0,
    "total_tokens": 0,
    "projects": [],
}

_ANTHROPIC_API_BASE = "https://api.anthropic.com/v1/organizations"


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
    """Background thread that periodically fetches API usage data."""

    def __init__(self, config: dict, state: dict, lock: threading.Lock):
        super().__init__(name="collector")
        self.config = config
        self.state = state
        self.lock = lock
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        api_interval = self.config["polling"]["api_interval_seconds"]
        last_api_fetch = 0.0

        while not self._stop_event.is_set():
            now = time.time()

            if now - last_api_fetch >= api_interval or last_api_fetch == 0:
                logger.info("Fetching API usage...")
                api_data = fetch_api_usage(self.config["anthropic"])
                last_api_fetch = now

                with self.lock:
                    self.state["api"] = api_data
                    self.state["last_updated"] = datetime.now().isoformat()

            self._stop_event.wait(timeout=5)
