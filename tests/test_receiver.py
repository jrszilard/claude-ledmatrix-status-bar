import json
import threading
import time
import pytest
import requests as req

from src.receiver import ReceiverThread


@pytest.fixture
def receiver_setup():
    """Start a receiver on a random port, yield state/lock/port, then stop."""
    state = {
        "subscription": {},
        "api": {},
    }
    lock = threading.Lock()
    config = {
        "receiver": {
            "port": 0,  # will be replaced with actual port
            "token": "test-secret-token",
        },
    }
    # Use a high port to avoid conflicts
    config["receiver"]["port"] = 18765
    thread = ReceiverThread(config, state, lock)
    thread.start()
    time.sleep(0.3)  # let server start
    yield state, lock, config["receiver"]["port"], config["receiver"]["token"]
    thread.stop()
    thread.join(timeout=5)


def test_post_usage_updates_state(receiver_setup):
    state, lock, port, token = receiver_setup
    data = {
        "session_pct": 42,
        "session_reset": "9pm",
        "week_all_pct": 55,
        "week_all_reset": "Apr 12",
        "week_sonnet_pct": 20,
        "week_sonnet_reset": "Apr 11",
        "extra_spent": 15.50,
        "extra_limit": 79.00,
    }
    resp = req.post(
        f"http://localhost:{port}/usage",
        json=data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    with lock:
        assert state["subscription"]["session_pct"] == 42
        assert state["subscription"]["session_reset"] == "9pm"
        assert state["subscription"]["week_all_pct"] == 55
        assert state["subscription"]["extra_spent"] == 15.50
        assert "last_updated" in state


def test_post_usage_rejects_bad_token(receiver_setup):
    state, lock, port, token = receiver_setup
    data = {
        "session_pct": 10, "session_reset": "7pm",
        "week_all_pct": 22, "week_all_reset": "Apr 10",
        "week_sonnet_pct": 9, "week_sonnet_reset": "Apr 9",
        "extra_spent": 7.0, "extra_limit": 79.0,
    }
    resp = req.post(
        f"http://localhost:{port}/usage",
        json=data,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


def test_post_usage_rejects_missing_fields(receiver_setup):
    state, lock, port, token = receiver_setup
    data = {"session_pct": 10}  # missing other fields
    resp = req.post(
        f"http://localhost:{port}/usage",
        json=data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_health_endpoint(receiver_setup):
    state, lock, port, token = receiver_setup
    resp = req.get(f"http://localhost:{port}/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_wrong_path_returns_404(receiver_setup):
    state, lock, port, token = receiver_setup
    resp = req.get(f"http://localhost:{port}/nonexistent")
    assert resp.status_code == 404
