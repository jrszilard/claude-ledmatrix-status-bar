"""Tests for the client-side push_usage parsing logic."""

import sys
import os

# Add client directory to path for importing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "client"))

from push_usage import parse_usage_output, strip_ansi


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


def test_strip_ansi():
    assert strip_ansi("\x1b[33mhello\x1b[0m") == "hello"
    assert strip_ansi("no codes") == "no codes"
