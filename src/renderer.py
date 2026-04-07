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


class DisplayCycler:
    """Cycles through different metrics on the 16x96 display."""

    def __init__(self, cycle_seconds=3, fade_frames=10):
        self.cycle_seconds = cycle_seconds
        self.fade_frames = fade_frames
        self.current_screen = 0
        self.total_screens = 5  # session, week_all, week_sonnet, extra, api
        self.last_cycle_time = time.time()
        self.fade_progress = None
        self._fade_frame = 0
        self._pre_fade_screen = 0

    def update(self):
        """Called each frame. Manages screen cycling and fade state."""
        now = time.time()

        if self.fade_progress is not None:
            self._fade_frame += 1
            self.fade_progress = self._fade_frame / (self.fade_frames * 2)

            if self.fade_progress >= 0.5 and self.current_screen == self._pre_fade_screen:
                self.current_screen = (self.current_screen + 1) % self.total_screens

            if self.fade_progress >= 1.0:
                self.fade_progress = None
                self._fade_frame = 0
                self.last_cycle_time = now
        else:
            if now - self.last_cycle_time >= self.cycle_seconds:
                self.fade_progress = 0.0
                self._fade_frame = 0
                self._pre_fade_screen = self.current_screen

    def get_brightness(self) -> float:
        """Get current brightness factor (0.0-1.0)."""
        if self.fade_progress is None:
            return 1.0
        p = self.fade_progress
        if p <= 0.5:
            return 1.0 - (p * 2)
        return (p - 0.5) * 2


def draw_metric(canvas, graphics, font, label, value, pct, color, brightness=1.0):
    """Draw a single metric: label + value on top, progress bar on bottom."""
    scaled = layout.scale_color(color, brightness)
    bar_bg = layout.scale_color(layout.COLOR_BAR_BG, brightness)
    c = graphics.Color(*scaled)

    # Top line: "LABEL VALUE"
    text = f"{label} {value}"
    # Center the text
    text_width = len(text) * layout.CHAR_WIDTH
    x = max(0, (layout.TOTAL_WIDTH - text_width) // 2)
    graphics.DrawText(canvas, font, x, layout.TEXT_Y, c, text)

    # Bottom: progress bar
    _draw_bar(
        canvas,
        layout.BAR_X, layout.BAR_Y,
        layout.BAR_WIDTH, layout.BAR_HEIGHT,
        pct, scaled, bar_bg,
    )


def draw_screen(canvas, graphics, font, screen_idx, state, brightness=1.0):
    """Draw the appropriate screen based on index."""
    sub = state.get("subscription", {})
    api = state.get("api", {})

    if screen_idx == 0:
        draw_metric(canvas, graphics, font,
                    "SES", f"{sub.get('session_pct', 0)}%",
                    sub.get("session_pct", 0),
                    layout.COLOR_SESSION, brightness)
    elif screen_idx == 1:
        draw_metric(canvas, graphics, font,
                    "WK-ALL", f"{sub.get('week_all_pct', 0)}%",
                    sub.get("week_all_pct", 0),
                    layout.COLOR_WEEK_ALL, brightness)
    elif screen_idx == 2:
        draw_metric(canvas, graphics, font,
                    "WK-SNT", f"{sub.get('week_sonnet_pct', 0)}%",
                    sub.get("week_sonnet_pct", 0),
                    layout.COLOR_WEEK_SONNET, brightness)
    elif screen_idx == 3:
        spent = sub.get("extra_spent", 0)
        limit = sub.get("extra_limit", 1)
        pct = spent / max(limit, 1) * 100
        draw_metric(canvas, graphics, font,
                    "EXT", f"${spent:.0f}/${limit:.0f}",
                    pct,
                    layout.COLOR_EXTRA, brightness)
    elif screen_idx == 4:
        spend = api.get("total_spend", 0)
        tokens = api.get("total_tokens", 0)
        draw_metric(canvas, graphics, font,
                    "API", f"{layout.format_dollars(spend)} {layout.format_tokens(tokens)}",
                    0,  # no bar for API
                    layout.COLOR_API, brightness)


# Keep old exports for compatibility with tests that import them
class Ticker:
    """Kept for compatibility — not used in 16-row layout."""
    def __init__(self, cycle_seconds=4, fade_frames=15, projects_per_page=2):
        self.cycle_seconds = cycle_seconds
        self.fade_frames = fade_frames
        self.projects_per_page = projects_per_page
        self.current_page = 0
        self.fade_progress = None
        self.last_cycle_time = time.time()
        self._fade_frame = 0
        self._pre_fade_page = 0

    def update(self, total_pages):
        pass

    def get_brightness(self, progress):
        if progress <= 0.5:
            return 1.0 - (progress * 2)
        return (progress - 0.5) * 2


def draw_ticker_page(canvas, graphics, fonts, projects_page, brightness=1.0):
    """Draw project ticker — simplified for 16-row display."""
    if not projects_page:
        return
    col_width = layout.TOTAL_WIDTH // max(len(projects_page), 1)
    for i, project in enumerate(projects_page):
        x_offset = i * col_width
        center_x = x_offset + col_width // 2
        name_color = layout.scale_color(layout.COLOR_API, brightness)
        color = graphics.Color(*name_color)
        name = project["name"]
        name_x = center_x - (len(name) * 4 // 2)
        graphics.DrawText(canvas, fonts["small"], name_x, layout.TICKER_PROJECT_Y_NAME, color, name)
        detail_color = layout.scale_color(layout.COLOR_GRAY, brightness)
        color = graphics.Color(*detail_color)
        detail = f"{layout.format_dollars(project['spend'])} {layout.format_tokens(project['tokens'])} tk"
        detail_x = center_x - (len(detail) * 4 // 2)
        graphics.DrawText(canvas, fonts["small"], detail_x, layout.TICKER_PROJECT_Y_DETAIL, color, detail)


# Kept for test compatibility
def draw_session_panel(canvas, graphics, fonts, subscription):
    font = fonts["small"]
    draw_metric(canvas, graphics, font, "SESSION", f"{subscription['session_pct']}%",
                subscription["session_pct"], layout.COLOR_SESSION)

def draw_weekly_panel(canvas, graphics, fonts, subscription):
    font = fonts["small"]
    c_all = graphics.Color(*layout.COLOR_WEEK_ALL)
    c_snt = graphics.Color(*layout.COLOR_WEEK_SONNET)
    c_ext = graphics.Color(*layout.COLOR_EXTRA)
    graphics.DrawText(canvas, font, 0, 7, c_all, "WEEKLY")
    graphics.DrawText(canvas, font, 0, 7, c_all, "ALL")
    graphics.DrawText(canvas, font, 0, 7, c_snt, "SNT")
    graphics.DrawText(canvas, font, 0, 7, c_ext, "EXT")

def draw_api_panel(canvas, graphics, fonts, api_state):
    font = fonts["small"]
    c = graphics.Color(*layout.COLOR_API)
    graphics.DrawText(canvas, font, 0, 7, c, "API TOTAL")
    graphics.DrawText(canvas, font, 0, 14, c, layout.format_dollars(api_state["total_spend"]))
    c_gray = graphics.Color(*layout.COLOR_GRAY)
    graphics.DrawText(canvas, font, 0, 14, c_gray, f"{layout.format_tokens(api_state['total_tokens'])} tk")

def draw_divider(canvas, graphics):
    color = graphics.Color(*layout.COLOR_DIVIDER)
    graphics.DrawLine(canvas, 0, 0, layout.TOTAL_WIDTH - 1, 0, color)
