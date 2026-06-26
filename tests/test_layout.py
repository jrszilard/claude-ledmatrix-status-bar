from src.layout import (
    COLOR_SESSION, COLOR_WEEK_ALL, COLOR_WEEK_SONNET,
    COLOR_EXTRA, COLOR_API, COLOR_GRAY, COLOR_BAR_BG,
    format_tokens, format_dollars, compute_bar_width, scale_color,
)


def test_colors_are_rgb_tuples():
    for color in [COLOR_SESSION, COLOR_WEEK_ALL, COLOR_WEEK_SONNET,
                  COLOR_EXTRA, COLOR_API, COLOR_GRAY, COLOR_BAR_BG]:
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)


def test_format_tokens():
    assert format_tokens(1_200_000) == "1.2M"
    assert format_tokens(410_000) == "410K"
    assert format_tokens(500) == "500"


def test_format_dollars():
    assert format_dollars(12.47) == "$12.47"
    assert format_dollars(100.5) == "$100"


def test_compute_bar_width():
    assert compute_bar_width(50, 100) == 50
    assert compute_bar_width(0, 100) == 0
    assert compute_bar_width(25, 200) == 50


def test_scale_color():
    assert scale_color((255, 100, 50), 1.0) == (255, 100, 50)
    assert scale_color((255, 100, 50), 0.5) == (127, 50, 25)
    assert scale_color((255, 100, 50), 0.0) == (0, 0, 0)
