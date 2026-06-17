import time
from datetime import datetime, timezone

from src import layout, registry


COUNTDOWN_PHASE_SECONDS = 7   # ~5s value, then ~2s countdown


class Cycler:
    """Advance through `total` items on a timer, with a fade across each swap.

    update(now) is frame-driven; pass an explicit `now` in tests for determinism.
    """

    def __init__(self, total, cycle_seconds=4, fade_frames=15):
        self.total = max(1, total)
        self.cycle_seconds = cycle_seconds
        self.fade_frames = fade_frames
        self.current = 0
        self.last_cycle_time = time.time()
        self.fade_progress = None
        self._fade_frame = 0
        self._pre = 0

    def update(self, now=None):
        now = time.time() if now is None else now
        if self.total <= 1:
            return
        if self.fade_progress is not None:
            self._fade_frame += 1
            self.fade_progress = self._fade_frame / (self.fade_frames * 2)
            if self.fade_progress >= 0.5 and self.current == self._pre:
                self.current = (self.current + 1) % self.total
            if self.fade_progress >= 1.0:
                self.fade_progress = None
                self._fade_frame = 0
                self.last_cycle_time = now
        elif now - self.last_cycle_time >= self.cycle_seconds:
            self.fade_progress = 0.0
            self._fade_frame = 0
            self._pre = self.current

    def brightness(self) -> float:
        if self.fade_progress is None:
            return 1.0
        p = self.fade_progress
        return 1.0 - (p * 2) if p <= 0.5 else (p - 0.5) * 2


def format_countdown(reset_utc) -> str:
    """UTC ISO timestamp -> compact countdown like '2h30m' or '3d5h'. '' if past/invalid."""
    if not reset_utc:
        return ""
    try:
        reset_dt = datetime.fromisoformat(reset_utc)
        delta = reset_dt - datetime.now(timezone.utc)
        total = int(delta.total_seconds())
        if total <= 0:
            return ""
        days, hours, minutes = total // 86400, (total % 86400) // 3600, (total % 3600) // 60
        if days > 0:
            return f"{days}d{hours}h"
        if hours > 0:
            return f"{hours}h{minutes:02d}m"
        return f"{minutes}m"
    except (ValueError, TypeError):
        return ""


def tile_value(metric, state, now=None, show_countdown=True) -> str:
    """The value string for a tile, alternating quota%/countdown over time."""
    now = time.time() if now is None else now
    base = format_value(metric, state)
    if not show_countdown or metric.shape != "quota" or not metric.reset_key:
        return base
    cd = format_countdown(registry.resolve(metric.reset_key, state))
    if not cd:
        return base
    return cd if (now % COUNTDOWN_PHASE_SECONDS) >= 5 else base


def format_value(metric, state) -> str:
    """Short, tile-width-friendly value string for a metric."""
    raw = registry.resolve(metric.key, state)
    if metric.shape == "quota":
        return f"{int(raw or 0)}%"
    if metric.shape == "capped":
        return f"${float(raw or 0):.0f}"
    if metric.shape in ("spend", "balance"):
        return layout.format_dollars(float(raw or 0))
    return ""


def metric_pct(metric, state):
    """Bar fill percentage for a metric, or None if the shape has no bar."""
    if metric.shape == "quota":
        return float(registry.resolve(metric.key, state) or 0)
    if metric.shape == "capped":
        spent = float(registry.resolve(metric.key, state) or 0)
        limit = float(registry.resolve(metric.limit_key, state) or 0)
        return (spent / limit * 100) if limit > 0 else 0.0
    return None  # spend / balance: no in-tile bar


def _draw_bar(canvas, x, y, width, height, percentage, fg_color, bg_color):
    filled = layout.compute_bar_width(percentage, width)
    for row in range(height):
        for col in range(width):
            color = fg_color if col < filled else bg_color
            canvas.SetPixel(x + col, y + row, *color)


def draw_tile(canvas, gfx, font, y_offset, metric, state, brightness=1.0, now=None,
              show_countdown=True):
    """Draw one metric in a 32x16 tile at the given vertical offset.

    Justified layout: label hugs the left, value hugs the right, bar (if any) below.
    """
    color = layout.scale_color(metric.color, brightness)
    c = gfx.Color(*color)

    value = tile_value(metric, state, now=now, show_countdown=show_countdown)
    text_y = y_offset + layout.TILE_TEXT_Y

    # Label left, value right-aligned.
    gfx.DrawText(canvas, font, layout.TILE_BAR_X, text_y, c, metric.label)
    value_x = max(layout.TILE_BAR_X, layout.TILE_WIDTH - len(value) * layout.CHAR_WIDTH)
    gfx.DrawText(canvas, font, value_x, text_y, c, value)

    pct = metric_pct(metric, state)
    if pct is not None:
        bg = layout.scale_color(layout.COLOR_BAR_BG, brightness)
        bar_w = layout.TILE_WIDTH - 2 * layout.TILE_BAR_X
        _draw_bar(canvas, layout.TILE_BAR_X, y_offset + layout.TILE_BAR_Y,
                  bar_w, layout.TILE_BAR_H, pct, color, bg)


def draw_accent(canvas, provider, brightness=1.0):
    """Persistent provider identity: a 1px accent column down the left edge."""
    color = layout.scale_color(provider.color, brightness)
    height = layout.NUM_TILES * layout.TILE_HEIGHT
    for y in range(height):
        canvas.SetPixel(0, y, *color)


def draw_hero(canvas, gfx, fonts, provider, state, brightness=1.0):
    """Full-stack hero readout for a single-metric (balance) provider."""
    metric = provider.page.metric
    accent = layout.scale_color(provider.color, brightness)
    c = gfx.Color(*accent)

    # Provider name across the top (small font).
    gfx.DrawText(canvas, fonts["small"], layout.TILE_BAR_X, layout.TILE_TEXT_Y, c,
                 provider.label)

    # Hero number (spent this period) centered in the main font.
    value = layout.format_dollars(float(registry.resolve(metric.key, state) or 0))
    value_x = max(0, (layout.TILE_WIDTH - len(value) * layout.CHAR_WIDTH) // 2)
    mid_y = (layout.NUM_TILES * layout.TILE_HEIGHT) // 2 + 4
    gfx.DrawText(canvas, fonts["main"], value_x, mid_y, c, value)

    # Optional sub-line (auto-reload note), small font, dimmed.
    sub = registry.resolve(metric.sub_key, state) if metric.sub_key else None
    if sub:
        sc = gfx.Color(*layout.scale_color(layout.COLOR_GRAY, brightness))
        sub = str(sub)[:layout.TILE_WIDTH // 4]  # 4px/char in the small font; clip to tile width
        sub_x = max(0, (layout.TILE_WIDTH - len(sub) * 4) // 2)
        gfx.DrawText(canvas, fonts["small"], sub_x, mid_y + 9, sc, sub)


def draw_page(canvas, gfx, fonts, provider, state, page_cycler, now=None,
              show_countdown=True):
    """Render a provider's page. Outer caller picks which provider."""
    now = time.time() if now is None else now
    draw_accent(canvas, provider)

    page = provider.page
    if isinstance(page, registry.HeroPage):
        draw_hero(canvas, gfx, fonts, provider, state)
        return

    offsets = layout.TILE_Y_OFFSETS
    idx = 0
    for metric in page.fixed:
        if idx >= len(offsets):
            break
        draw_tile(canvas, gfx, fonts["main"], offsets[idx], metric, state,
                  brightness=1.0, now=now, show_countdown=show_countdown)
        idx += 1

    if page.rotating and idx < len(offsets):
        cur = page.rotating[page_cycler.current % len(page.rotating)]
        draw_tile(canvas, gfx, fonts["main"], offsets[idx], cur, state,
                  brightness=page_cycler.brightness(), now=now,
                  show_countdown=show_countdown)


class Dashboard:
    """Top-level: cycles enabled provider pages and draws the current one."""

    def __init__(self, cycle_seconds=4, fade_frames=15, page_dwell_seconds=8,
                 show_countdown=True):
        self.show_countdown = show_countdown
        self.providers = registry.enabled_providers()
        self.provider_cycler = Cycler(len(self.providers), page_dwell_seconds, fade_frames)
        self.page_cyclers = {}
        for p in self.providers:
            n = len(p.page.rotating) if isinstance(p.page, registry.TilesPage) else 1
            self.page_cyclers[p.id] = Cycler(n, cycle_seconds, fade_frames)

    def update(self, now=None):
        now = time.time() if now is None else now
        self.provider_cycler.update(now)
        for cy in self.page_cyclers.values():
            cy.update(now)

    def draw(self, canvas, gfx, fonts, state, now=None):
        if not self.providers:
            return
        now = time.time() if now is None else now
        provider = self.providers[self.provider_cycler.current % len(self.providers)]
        draw_page(canvas, gfx, fonts, provider, state, self.page_cyclers[provider.id],
                  now=now, show_countdown=self.show_countdown)
