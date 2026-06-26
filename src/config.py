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


def resolve_geometry(display: dict) -> dict:
    """Resolve panel geometry from the [display] config.

    Prefers explicit chain_length/parallel. Falls back to the legacy `panels`
    key (treated as a parallel-chain count for the triple bonnet). Defaults to a
    single panel.
    """
    parallel = display.get("parallel")
    if parallel is None:
        parallel = display.get("panels", 1)
    return {
        "rows": display["rows"],
        "cols": display["cols_per_panel"],
        "chain_length": display.get("chain_length", 1),
        "parallel": parallel,
    }


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
