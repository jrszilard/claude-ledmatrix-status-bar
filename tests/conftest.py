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
            "api_interval_seconds": 300,
        },
        "receiver": {
            "port": 8765,
            "token": "test-secret-token",
        },
        "anthropic": {
            "admin_api_key": "sk-ant-admin-test-key",
            "api_projects": [
                {"name": "tastytrade-bot", "api_key_id": "apikey_01ABC"},
                {"name": "diy-helper", "api_key_id": "apikey_02DEF"},
            ],
        },
    }
