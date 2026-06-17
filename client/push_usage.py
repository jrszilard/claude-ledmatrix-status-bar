#!/usr/bin/env python3
"""Push Claude Code subscription usage to the LED matrix Pi.

Self-contained script to run on your personal machine (where Claude Code
is installed). Spawns a headless tmux session, captures /usage output,
parses it, and POSTs the data to the Pi's HTTP receiver.

Usage:
    # One-shot push:
    python push_usage.py --host 192.168.1.100

    # Run continuously (push every 3 minutes):
    python push_usage.py --host 192.168.1.100 --loop --interval 180

    # With cron (every 3 minutes):
    */3 * * * * /usr/bin/python3 /path/to/push_usage.py --host 192.168.1.100 --token YOUR_TOKEN

Environment variables:
    PUSH_TOKEN  - shared secret token (or use --token flag)
    PI_HOST     - Pi hostname/IP (or use --host flag)
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [push_usage] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_DEFAULT_SUBSCRIPTION = {
    "session_pct": 0,
    "session_reset": "--",
    "session_reset_utc": None,
    "week_all_pct": 0,
    "week_all_reset": "--",
    "week_all_reset_utc": None,
    "week_sonnet_pct": 0,
    "week_sonnet_reset": "--",
    "week_sonnet_reset_utc": None,
    "extra_spent": 0.0,
    "extra_limit": 0.0,
}


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def parse_reset_to_utc(reset_str: str, tz_name: str = "America/New_York") -> str | None:
    """Convert a reset time string like '1pm' or 'Apr 10, 10am' to UTC ISO format.

    Formats seen from /usage:
      - "1pm"           → today at 1:00 PM in the given timezone
      - "Apr 10, 10am"  → April 10 at 10:00 AM
      - "May 1"         → May 1 at midnight
    """
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)

        # Try "Apr 10, 10am" format
        m = re.match(r"([A-Z][a-z]+)\s+(\d+),?\s+(\d+)(am|pm)", reset_str)
        if m:
            month_str, day, hour, ampm = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            dt = datetime.strptime(month_str, "%b").replace(
                year=now.year, day=day, hour=hour, minute=0, second=0,
                tzinfo=tz,
            )
            if dt < now - timedelta(days=1):
                dt = dt.replace(year=now.year + 1)
            return dt.astimezone(ZoneInfo("UTC")).isoformat()

        # Try "1pm" / "10am" format (today)
        m = re.match(r"(\d+)(am|pm)$", reset_str)
        if m:
            hour, ampm = int(m.group(1)), m.group(2)
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            dt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if dt < now:
                dt += timedelta(days=1)
            return dt.astimezone(ZoneInfo("UTC")).isoformat()

        # Try "May 1" format (date only, midnight)
        m = re.match(r"([A-Z][a-z]+)\s+(\d+)$", reset_str)
        if m:
            month_str, day = m.group(1), int(m.group(2))
            dt = datetime.strptime(month_str, "%b").replace(
                year=now.year, day=day, hour=0, minute=0, second=0,
                tzinfo=tz,
            )
            if dt < now - timedelta(days=1):
                dt = dt.replace(year=now.year + 1)
            return dt.astimezone(ZoneInfo("UTC")).isoformat()

    except Exception as e:
        logger.warning(f"Could not parse reset time '{reset_str}': {e}")
    return None


def parse_usage_output(raw_text: str) -> dict:
    """Parse Claude Code /usage TUI output into a structured dict."""
    text = strip_ansi(raw_text)
    result = dict(_DEFAULT_SUBSCRIPTION)

    # Detect timezone from output (e.g. "America/New_York")
    tz_match = re.search(r"\(([A-Za-z]+/[A-Za-z_]+)\)", text)
    tz_name = tz_match.group(1) if tz_match else "America/New_York"

    m = re.search(r"Current session.*?(\d+)%\s+used", text, re.DOTALL)
    if m:
        result["session_pct"] = int(m.group(1))

    m = re.search(r"Current session.*?Resets\s+(.+?)\s*\(", text, re.DOTALL)
    if m:
        result["session_reset"] = m.group(1).strip()
        result["session_reset_utc"] = parse_reset_to_utc(result["session_reset"], tz_name)

    m = re.search(r"Current week \(all models\).*?(\d+)%\s+used", text, re.DOTALL)
    if m:
        result["week_all_pct"] = int(m.group(1))

    m = re.search(
        r"Current week \(all models\).*?Resets\s+(.+?)\s*\(", text, re.DOTALL
    )
    if m:
        result["week_all_reset"] = m.group(1).strip()
        result["week_all_reset_utc"] = parse_reset_to_utc(result["week_all_reset"], tz_name)

    m = re.search(r"Current week \(Sonnet only\).*?(\d+)%\s+used", text, re.DOTALL)
    if m:
        result["week_sonnet_pct"] = int(m.group(1))

    m = re.search(
        r"Current week \(Sonnet only\).*?Resets\s+(.+?)\s*\(", text, re.DOTALL
    )
    if m:
        result["week_sonnet_reset"] = m.group(1).strip()
        result["week_sonnet_reset_utc"] = parse_reset_to_utc(result["week_sonnet_reset"], tz_name)

    m = re.search(r"\$(\d+\.?\d*)\s*/\s*\$(\d+\.?\d*)\s+spent", text)
    if m:
        result["extra_spent"] = float(m.group(1))
        result["extra_limit"] = float(m.group(2))

    return result


def capture_usage() -> dict:
    """Spawn tmux + Claude Code, capture /usage output, parse and return."""
    session_name = f"push_usage_{int(time.time())}"
    # Launch from a trusted project directory to avoid the workspace trust prompt
    # that blocks Claude Code's TUI when launching from $HOME (cron default).
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-x", "200", "-y", "50"],
            check=True, timeout=5,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name,
             f"cd {script_dir} && claude", "Enter"],
            check=True, timeout=5,
        )

        logger.info("Waiting for Claude Code to initialize...")
        time.sleep(12)

        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "/usage"],
            check=True, timeout=5,
        )
        time.sleep(2)
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, "Enter"],
            check=True, timeout=5,
        )

        logger.info("Waiting for /usage to render...")
        time.sleep(10)

        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-"],
            capture_output=True, text=True, timeout=5,
        )

        parsed = parse_usage_output(result.stdout)
        logger.info(f"Parsed: session={parsed['session_pct']}%, "
                     f"week_all={parsed['week_all_pct']}%, "
                     f"extra=${parsed['extra_spent']}/{parsed['extra_limit']}")
        return parsed

    except Exception as e:
        logger.error(f"Failed to capture usage: {e}")
        return dict(_DEFAULT_SUBSCRIPTION)

    finally:
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            capture_output=True, timeout=5,
        )


def push_to_pi(data: dict, host: str, port: int, token: str) -> bool:
    """POST usage data to the Pi's HTTP receiver."""
    url = f"http://{host}:{port}/usage"
    try:
        resp = requests.post(
            url,
            json=data,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Pushed to {host}:{port} successfully")
            return True
        else:
            logger.error(f"Push failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Push failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Push Claude Code usage to LED matrix Pi")
    parser.add_argument("--host", default=os.environ.get("PI_HOST", "localhost"),
                        help="Pi hostname or IP (default: $PI_HOST or localhost)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Pi receiver port (default: 8765)")
    parser.add_argument("--token", default=os.environ.get("PUSH_TOKEN", ""),
                        help="Shared secret token (default: $PUSH_TOKEN)")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously instead of one-shot")
    parser.add_argument("--interval", type=int, default=180,
                        help="Seconds between pushes in loop mode (default: 180)")
    args = parser.parse_args()

    if not args.token:
        logger.error("Token required. Set PUSH_TOKEN env var or use --token flag.")
        sys.exit(1)

    while True:
        data = capture_usage()
        push_to_pi(data, args.host, args.port, args.token)

        if not args.loop:
            break
        logger.info(f"Sleeping {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
