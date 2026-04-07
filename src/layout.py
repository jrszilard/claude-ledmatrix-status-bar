import math

# Display dimensions
PANEL_WIDTH = 64
TOTAL_WIDTH = 192  # 3 panels x 64
TOTAL_HEIGHT = 32

# Region boundaries
DASHBOARD_BOTTOM = 22
TICKER_TOP = 22
TICKER_HEIGHT = TOTAL_HEIGHT - TICKER_TOP  # 10 rows

# Panel X offsets
PANEL1_X = 0
PANEL2_X = 64
PANEL3_X = 128

# Session panel (Panel 1) layout
SESSION_LABEL_X = 14
SESSION_LABEL_Y = 7
SESSION_PCT_X = 12
SESSION_PCT_Y = 17
SESSION_BAR_X = 4
SESSION_BAR_Y = 18
SESSION_BAR_WIDTH = 56
SESSION_BAR_HEIGHT = 2
SESSION_RESET_X = 4
SESSION_RESET_Y = 21

# Weekly panel (Panel 2) layout
WEEKLY_LABEL_X = PANEL2_X + 14
WEEKLY_LABEL_Y = 6
WEEKLY_BAR_LABEL_X = PANEL2_X + 2
WEEKLY_BAR_X = PANEL2_X + 16
WEEKLY_BAR_WIDTH = 32
WEEKLY_BAR_HEIGHT = 2
WEEKLY_PCT_X = PANEL2_X + 50
WEEKLY_ROW_ALL_Y = 10
WEEKLY_ROW_SNT_Y = 14
WEEKLY_ROW_EXT_Y = 18

# API panel (Panel 3) layout
API_LABEL_X = PANEL3_X + 12
API_LABEL_Y = 7
API_SPEND_X = PANEL3_X + 8
API_SPEND_Y = 15
API_TOKENS_X = PANEL3_X + 6
API_TOKENS_Y = 21

# Ticker layout
TICKER_PROJECT_Y_NAME = TICKER_TOP + 4
TICKER_PROJECT_Y_DETAIL = TICKER_TOP + 9
TICKER_DIVIDER_Y = TICKER_TOP
TICKER_COL_WIDTH = 96  # 192 / 2 projects

# Colors (R, G, B)
COLOR_SESSION = (255, 107, 107)
COLOR_WEEK_ALL = (255, 217, 61)
COLOR_WEEK_SONNET = (107, 203, 119)
COLOR_EXTRA = (77, 150, 255)
COLOR_API = (201, 160, 255)
COLOR_GRAY = (128, 128, 128)
COLOR_BAR_BG = (51, 51, 51)
COLOR_DIVIDER = (68, 68, 68)


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


def compute_bar_width(percentage: int, max_width: int) -> int:
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
