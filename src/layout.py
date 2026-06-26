import math

# Colors (R, G, B)
COLOR_SESSION = (255, 107, 107)
COLOR_WEEK_ALL = (255, 217, 61)
COLOR_WEEK_SONNET = (107, 203, 119)
COLOR_EXTRA = (77, 150, 255)
COLOR_API = (201, 160, 255)
COLOR_GRAY = (128, 128, 128)
COLOR_BAR_BG = (51, 51, 51)
COLOR_DIVIDER = (68, 68, 68)

# Text layout (5x7 font)
CHAR_WIDTH = 5   # pixels per character


def format_tokens(tokens: int) -> str:
    """Format token count for display: 1200000 -> '1.2M', 410000 -> '410K'."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{math.ceil(tokens / 1_000)}K"
    return str(tokens)


def format_dollars(amount: float) -> str:
    """Format dollar amount: 12.47 -> '$12.47', 100.5 -> '$101'."""
    if amount >= 100:
        return f"${amount:.0f}"
    return f"${amount:.2f}"


def compute_bar_width(percentage, max_width: int) -> int:
    """Compute pixel width of a progress bar given percentage and max width."""
    return int(max_width * percentage / 100)


def scale_color(color: tuple, brightness: float) -> tuple:
    """Scale an RGB color tuple by a brightness factor (0.0 to 1.0)."""
    return tuple(int(c * brightness) for c in color)


# --- Vertical tile geometry (triple-bonnet parallel stack) -------------------
# Three stacked 32x16 tiles -> a 32x48 framebuffer. Defaults match the current
# hardware so tests and dry-run work without calling configure().
TILE_WIDTH = 32
TILE_HEIGHT = 16
NUM_TILES = 3
TILE_Y_OFFSETS = [0, 16, 32]

# Element positions WITHIN a single tile, relative to the tile's top row.
TILE_TEXT_Y = 8       # text baseline inside the tile
TILE_BAR_Y = 11       # bar top inside the tile
TILE_BAR_H = 3        # bar thickness
TILE_BAR_X = 1        # left inset for the bar (leaves col 0 for the accent)
TILE_TEXT_X = 1       # text starts right after the accent column (tight 5x7 layout)


def configure(rows: int, cols: int, parallel: int) -> None:
    """Derive tile geometry from hardware config. Call once at startup.

    rows/cols are a single panel's dimensions; parallel is the number of
    stacked panels (parallel chains on the bonnet).
    """
    global TILE_WIDTH, TILE_HEIGHT, NUM_TILES, TILE_Y_OFFSETS, TOTAL_WIDTH, TOTAL_HEIGHT
    TILE_WIDTH = cols
    TILE_HEIGHT = rows
    NUM_TILES = parallel
    TILE_Y_OFFSETS = [i * rows for i in range(parallel)]
    TOTAL_WIDTH = TILE_WIDTH
    TOTAL_HEIGHT = TILE_HEIGHT * NUM_TILES


# Canonical full-canvas dimensions (derived from tile geometry).
TOTAL_WIDTH = TILE_WIDTH
TOTAL_HEIGHT = TILE_HEIGHT * NUM_TILES
