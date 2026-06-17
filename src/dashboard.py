import time

from src import layout, registry


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


def draw_tile(canvas, gfx, font, y_offset, metric, state, brightness=1.0, now=None):
    """Draw one metric in a 32x16 tile at the given vertical offset.

    Justified layout: label hugs the left, value hugs the right, bar (if any) below.
    """
    color = layout.scale_color(metric.color, brightness)
    c = gfx.Color(*color)

    value = format_value(metric, state)
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
