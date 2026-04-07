import time
import logging

from src import layout

logger = logging.getLogger(__name__)


def _draw_bar(canvas, x, y, width, height, percentage, fg_color, bg_color):
    """Draw a progress bar with filled and background portions."""
    filled_width = layout.compute_bar_width(percentage, width)
    for row in range(height):
        for col in range(width):
            if col < filled_width:
                canvas.SetPixel(x + col, y + row, *fg_color)
            else:
                canvas.SetPixel(x + col, y + row, *bg_color)


def draw_session_panel(canvas, graphics, fonts, subscription):
    """Draw the session usage panel on Panel 1 (leftmost 64px)."""
    color_session = graphics.Color(*layout.COLOR_SESSION)
    color_gray = graphics.Color(*layout.COLOR_GRAY)

    # Label
    graphics.DrawText(
        canvas, fonts["small"],
        layout.SESSION_LABEL_X, layout.SESSION_LABEL_Y,
        color_session, "SESSION",
    )

    # Large percentage
    pct_text = f"{subscription['session_pct']}%"
    graphics.DrawText(
        canvas, fonts["large"],
        layout.SESSION_PCT_X, layout.SESSION_PCT_Y,
        color_session, pct_text,
    )

    # Progress bar
    _draw_bar(
        canvas,
        layout.SESSION_BAR_X, layout.SESSION_BAR_Y,
        layout.SESSION_BAR_WIDTH, layout.SESSION_BAR_HEIGHT,
        subscription["session_pct"],
        layout.COLOR_SESSION, layout.COLOR_BAR_BG,
    )

    # Reset time
    reset_text = f"~{subscription['session_reset']}"
    graphics.DrawText(
        canvas, fonts["small"],
        layout.SESSION_RESET_X, layout.SESSION_RESET_Y,
        color_gray, reset_text,
    )


def draw_weekly_panel(canvas, graphics, fonts, subscription):
    """Draw weekly usage bars on Panel 2 (middle 64px)."""
    color_all = graphics.Color(*layout.COLOR_WEEK_ALL)
    color_snt = graphics.Color(*layout.COLOR_WEEK_SONNET)
    color_ext = graphics.Color(*layout.COLOR_EXTRA)

    # Header
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_LABEL_X, layout.WEEKLY_LABEL_Y,
        color_all, "WEEKLY",
    )

    # ALL bar
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_BAR_LABEL_X, layout.WEEKLY_ROW_ALL_Y,
        color_all, "ALL",
    )
    _draw_bar(
        canvas,
        layout.WEEKLY_BAR_X, layout.WEEKLY_ROW_ALL_Y - 1,
        layout.WEEKLY_BAR_WIDTH, layout.WEEKLY_BAR_HEIGHT,
        subscription["week_all_pct"],
        layout.COLOR_WEEK_ALL, layout.COLOR_BAR_BG,
    )
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_PCT_X, layout.WEEKLY_ROW_ALL_Y,
        color_all, f"{subscription['week_all_pct']}%",
    )

    # SNT bar
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_BAR_LABEL_X, layout.WEEKLY_ROW_SNT_Y,
        color_snt, "SNT",
    )
    _draw_bar(
        canvas,
        layout.WEEKLY_BAR_X, layout.WEEKLY_ROW_SNT_Y - 1,
        layout.WEEKLY_BAR_WIDTH, layout.WEEKLY_BAR_HEIGHT,
        subscription["week_sonnet_pct"],
        layout.COLOR_WEEK_SONNET, layout.COLOR_BAR_BG,
    )
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_PCT_X, layout.WEEKLY_ROW_SNT_Y,
        color_snt, f"{subscription['week_sonnet_pct']}%",
    )

    # EXT bar
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_BAR_LABEL_X, layout.WEEKLY_ROW_EXT_Y,
        color_ext, "EXT",
    )
    extra_pct = (
        subscription["extra_spent"] / max(subscription["extra_limit"], 1) * 100
    )
    _draw_bar(
        canvas,
        layout.WEEKLY_BAR_X, layout.WEEKLY_ROW_EXT_Y - 1,
        layout.WEEKLY_BAR_WIDTH, layout.WEEKLY_BAR_HEIGHT,
        extra_pct,
        layout.COLOR_EXTRA, layout.COLOR_BAR_BG,
    )
    ext_text = f"${subscription['extra_spent']:.0f}/${subscription['extra_limit']:.0f}"
    graphics.DrawText(
        canvas, fonts["small"],
        layout.WEEKLY_PCT_X - 4, layout.WEEKLY_ROW_EXT_Y,
        color_ext, ext_text,
    )


def draw_api_panel(canvas, graphics, fonts, api_state):
    """Draw API total spend on Panel 3 (rightmost 64px)."""
    color_api = graphics.Color(*layout.COLOR_API)
    color_gray = graphics.Color(*layout.COLOR_GRAY)

    # Label
    graphics.DrawText(
        canvas, fonts["small"],
        layout.API_LABEL_X, layout.API_LABEL_Y,
        color_api, "API TOTAL",
    )

    # Large dollar amount
    spend_text = layout.format_dollars(api_state["total_spend"])
    graphics.DrawText(
        canvas, fonts["large"],
        layout.API_SPEND_X, layout.API_SPEND_Y,
        color_api, spend_text,
    )

    # Token count
    tokens_text = f"{layout.format_tokens(api_state['total_tokens'])} tk"
    graphics.DrawText(
        canvas, fonts["small"],
        layout.API_TOKENS_X, layout.API_TOKENS_Y,
        color_gray, tokens_text,
    )


def draw_divider(canvas, graphics):
    """Draw horizontal divider line between dashboard and ticker."""
    color = graphics.Color(*layout.COLOR_DIVIDER)
    graphics.DrawLine(
        canvas, 0, layout.DASHBOARD_BOTTOM - 1,
        layout.TOTAL_WIDTH - 1, layout.DASHBOARD_BOTTOM - 1,
        color,
    )


# --- Bottom Ticker ---


class Ticker:
    """Manages page cycling and fade transitions for the bottom ticker."""

    def __init__(self, cycle_seconds: float, fade_frames: int, projects_per_page: int):
        self.cycle_seconds = cycle_seconds
        self.fade_frames = fade_frames
        self.projects_per_page = projects_per_page
        self.current_page = 0
        self.fade_progress = None  # None = not fading, 0.0-1.0 = fading
        self.last_cycle_time = time.time()
        self._fade_frame = 0
        self._pre_fade_page = 0

    def update(self, total_pages: int):
        """Called each frame. Manages page cycling and fade state."""
        if total_pages == 0:
            return

        # Wrap around if current page is beyond total
        if self.current_page >= total_pages:
            self.current_page = 0

        now = time.time()

        if self.fade_progress is not None:
            # Currently fading
            self._fade_frame += 1
            self.fade_progress = self._fade_frame / (self.fade_frames * 2)

            if self.fade_progress >= 0.5 and self.current_page == self._pre_fade_page:
                # Halfway through fade — swap page
                self.current_page = (self.current_page + 1) % total_pages

            if self.fade_progress >= 1.0:
                # Fade complete
                self.fade_progress = None
                self._fade_frame = 0
                self.last_cycle_time = now
        else:
            # Check if it's time to start a new cycle
            if now - self.last_cycle_time >= self.cycle_seconds:
                self.fade_progress = 0.0
                self._fade_frame = 0
                self._pre_fade_page = self.current_page

    def get_brightness(self, progress: float) -> float:
        """Get brightness factor (0.0-1.0) for a given fade progress.

        First half (0.0-0.5): fade out (1.0 -> 0.0)
        Second half (0.5-1.0): fade in (0.0 -> 1.0)
        """
        if progress <= 0.5:
            return 1.0 - (progress * 2)
        return (progress - 0.5) * 2


def draw_ticker_page(canvas, graphics, fonts, projects_page, brightness=1.0):
    """Draw a single page of projects in the ticker area."""
    if not projects_page:
        return

    col_width = layout.TOTAL_WIDTH // max(len(projects_page), 1)

    for i, project in enumerate(projects_page):
        x_offset = i * col_width
        center_x = x_offset + col_width // 2

        # Project name (centered-ish)
        name_color = layout.scale_color(layout.COLOR_API, brightness)
        color = graphics.Color(*name_color)
        name = project["name"]
        # Estimate text width (4px per char for small font)
        name_x = center_x - (len(name) * 4 // 2)
        graphics.DrawText(
            canvas, fonts["small"],
            name_x, layout.TICKER_PROJECT_Y_NAME,
            color, name,
        )

        # Spend + tokens
        detail_color = layout.scale_color(layout.COLOR_GRAY, brightness)
        color = graphics.Color(*detail_color)
        detail = f"{layout.format_dollars(project['spend'])} {layout.format_tokens(project['tokens'])} tk"
        detail_x = center_x - (len(detail) * 4 // 2)
        graphics.DrawText(
            canvas, fonts["small"],
            detail_x, layout.TICKER_PROJECT_Y_DETAIL,
            color, detail,
        )
