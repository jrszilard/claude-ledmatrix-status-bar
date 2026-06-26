import os
import pytest
import tempfile
import yaml

from src.config import load_config, resolve_geometry


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
    assert config["polling"]["api_interval_seconds"] == 300
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
