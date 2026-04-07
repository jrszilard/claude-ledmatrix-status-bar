import threading
import time
import pytest
from unittest.mock import patch, MagicMock

from src.collector import (
    fetch_api_usage,
    parse_usage_response,
    parse_cost_response,
    CollectorThread,
    _DEFAULT_API,
)


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
    state = {"subscription": {}, "api": {}}
    lock = threading.Lock()

    api_data = {
        "total_spend": 5.0,
        "total_tokens": 500_000,
        "projects": [{"name": "test", "spend": 5.0, "tokens": 500_000}],
    }

    with patch("src.collector.fetch_api_usage", return_value=api_data):
        config = {
            "polling": {"api_interval_seconds": 300},
            "anthropic": {"admin_api_key": "test", "api_projects": []},
        }
        thread = CollectorThread(config, state, lock)
        thread.daemon = True
        thread.start()
        time.sleep(1)
        thread.stop()
        thread.join(timeout=5)

    with lock:
        assert state["api"]["total_spend"] == 5.0
        assert "last_updated" in state


def test_collector_thread_stops_cleanly():
    state = {"subscription": {}, "api": {}}
    lock = threading.Lock()

    with patch("src.collector.fetch_api_usage", return_value=dict(_DEFAULT_API)):
        config = {
            "polling": {"api_interval_seconds": 300},
            "anthropic": {"admin_api_key": "test", "api_projects": []},
        }
        thread = CollectorThread(config, state, lock)
        thread.daemon = True
        thread.start()
        time.sleep(0.5)
        thread.stop()
        thread.join(timeout=5)

    assert not thread.is_alive()
