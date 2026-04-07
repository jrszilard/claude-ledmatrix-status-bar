import threading
import time
import pytest
from unittest.mock import patch, MagicMock

from src.collector import (
    parse_usage_output,
    fetch_api_usage,
    parse_usage_response,
    parse_cost_response,
    CollectorThread,
    _DEFAULT_SUBSCRIPTION,
    _DEFAULT_API,
)


# --- Subscription Usage Parsing Tests ---


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


# --- API Usage Tests ---


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


# --- Collector Thread Tests ---


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

    with patch("src.collector.fetch_subscription_usage", return_value=dict(_DEFAULT_SUBSCRIPTION)), \
         patch("src.collector.fetch_api_usage", return_value=dict(_DEFAULT_API)):
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
