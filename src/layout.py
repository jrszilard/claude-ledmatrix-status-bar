import math

# Display dimensions
PANEL_WIDTH = 32
TOTAL_WIDTH = 96  # 3 panels x 32
TOTAL_HEIGHT = 16

# Colors (R, G, B)
COLOR_SESSION = (255, 107, 107)
COLOR_WEEK_ALL = (255, 217, 61)
COLOR_WEEK_SONNET = (107, 203, 119)
COLOR_EXTRA = (77, 150, 255)
COLOR_API = (201, 160, 255)
COLOR_GRAY = (128, 128, 128)
COLOR_BAR_BG = (51, 51, 51)
COLOR_DIVIDER = (68, 68, 68)

# Text positions (5x7 font)
CHAR_WIDTH = 5   # pixels per character
TEXT_Y = 8       # baseline for top text row
BAR_Y = 11       # top of progress bar
BAR_HEIGHT = 3   # bar thickness
BAR_X = 2        # left padding
BAR_WIDTH = 92   # nearly full width

# Ticker (bottom area when using split layout)
TICKER_PROJECT_Y_NAME = 7
TICKER_PROJECT_Y_DETAIL = 14


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


def ticker_pages(projects: list, per_page: int) -> list:
    """Split project list into pages of per_page items each."""
    if not projects:
        return []
    return [
        projects[i : i + per_page]
        for i in range(0, len(projects), per_page)
    ]


def scale_color(color: tuple, brightness: float) -> tuple:
    """Scale an RGB color tuple by a brightness factor (0.0 to 1.0)."""
    return tuple(int(c * brightness) for c in color)
