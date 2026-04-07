import argparse
import copy
import json
import logging
import signal
import sys
import threading
import time

from src.config import load_config
from src.collector import CollectorThread
from src.receiver import ReceiverThread
from src import layout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_INITIAL_STATE = {
    "subscription": {
        "session_pct": 0,
        "session_reset": "--",
        "week_all_pct": 0,
        "week_all_reset": "--",
        "week_sonnet_pct": 0,
        "week_sonnet_reset": "--",
        "extra_spent": 0.0,
        "extra_limit": 0.0,
    },
    "api": {
        "total_spend": 0.0,
        "total_tokens": 0,
        "projects": [],
    },
    "last_updated": None,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Claude LED Matrix Status Bar")
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print state to console instead of driving LEDs (no rgbmatrix needed)",
    )
    return parser.parse_args()


def run_dry_mode(config, state, lock):
    """Print state to console periodically instead of rendering to LEDs."""
    logger.info("Running in dry-run mode (no LED output)")
    try:
        while True:
            with lock:
                snapshot = copy.deepcopy(state)
            print("\033[2J\033[H")  # Clear terminal
            print("=== Claude LED Status Bar (dry-run) ===\n")
            print(json.dumps(snapshot, indent=2, default=str))
            time.sleep(2)
    except KeyboardInterrupt:
        pass


def run_led_mode(config, state, lock):
    """Main render loop driving the LED matrix."""
    from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
    from src.renderer import DisplayCycler, draw_screen

    options = RGBMatrixOptions()
    options.rows = config["display"]["rows"]
    options.cols = config["display"]["cols_per_panel"]
    options.chain_length = config["display"]["panels"]
    options.parallel = 1
    options.hardware_mapping = config["display"]["gpio_mapping"]
    options.gpio_slowdown = config["display"]["gpio_slowdown"]
    options.brightness = config["display"]["brightness"]
    options.disable_hardware_pulsing = config["display"].get("no_hardware_pulse", False)
    options.drop_privileges = False

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()

    font = graphics.Font()
    font.LoadFont("fonts/5x7.bdf")

    cycler = DisplayCycler(
        cycle_seconds=config["display"]["ticker_cycle_seconds"],
        fade_frames=config["display"]["ticker_fade_frames"],
    )

    logger.info("LED matrix initialized. Starting render loop.")

    try:
        while True:
            canvas.Clear()

            with lock:
                snapshot = copy.deepcopy(state)

            cycler.update()
            brightness = cycler.get_brightness()
            draw_screen(canvas, graphics, font, cycler.current_screen, snapshot, brightness)

            canvas = matrix.SwapOnVSync(canvas)

    except KeyboardInterrupt:
        logger.info("Shutting down LED matrix.")
        matrix.Clear()


def main():
    args = parse_args()

    config = load_config(args.config)
    logger.info(f"Config loaded from {args.config}")

    state = copy.deepcopy(_INITIAL_STATE)
    lock = threading.Lock()

    # Start HTTP receiver for subscription data pushes
    receiver = ReceiverThread(config, state, lock)
    receiver.start()
    logger.info(f"Receiver started on port {config['receiver']['port']}")

    # Start API collector thread
    collector = CollectorThread(config, state, lock)
    collector.daemon = True
    collector.start()
    logger.info("API collector thread started.")

    def shutdown(signum, frame):
        logger.info("Received shutdown signal.")
        collector.stop()
        receiver.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    if args.dry_run:
        run_dry_mode(config, state, lock)
    else:
        run_led_mode(config, state, lock)

    collector.stop()
    collector.join(timeout=10)
    receiver.stop()


if __name__ == "__main__":
    main()
