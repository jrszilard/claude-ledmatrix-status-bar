from src.layout import (
    TOTAL_WIDTH,
    TOTAL_HEIGHT,
    PANEL_WIDTH,
    BAR_X,
    BAR_Y,
    BAR_WIDTH,
    BAR_HEIGHT,
    BAR_BORDER_X,
    BAR_BORDER_Y,
    BAR_BORDER_W,
    BAR_BORDER_H,
    COLOR_SESSION,
    COLOR_WEEK_ALL,
    COLOR_WEEK_SONNET,
    COLOR_EXTRA,
    COLOR_API,
    COLOR_GRAY,
    COLOR_BAR_BG,
    format_tokens,
    format_dollars,
    compute_bar_width,
    ticker_pages,
    scale_color,
)


def test_display_dimensions():
    assert TOTAL_WIDTH == 96
    assert TOTAL_HEIGHT == 16
    assert PANEL_WIDTH == 32


def test_bar_border_contains_bar():
    """Border should surround the bar with 1px on each side."""
    assert BAR_BORDER_X == BAR_X - 1
    assert BAR_BORDER_Y == BAR_Y - 1
    assert BAR_BORDER_W == BAR_WIDTH + 2
    assert BAR_BORDER_H == BAR_HEIGHT + 2


def test_colors_are_rgb_tuples():
    for color in [COLOR_SESSION, COLOR_WEEK_ALL, COLOR_WEEK_SONNET,
                  COLOR_EXTRA, COLOR_API, COLOR_GRAY, COLOR_BAR_BG]:
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)


def test_format_tokens_millions():
    assert format_tokens(1_200_000) == "1.2M"
    assert format_tokens(2_500_000) == "2.5M"


def test_format_tokens_thousands():
    assert format_tokens(410_000) == "410K"
    assert format_tokens(1_500) == "2K"


def test_format_tokens_small():
    assert format_tokens(500) == "500"
    assert format_tokens(0) == "0"


def test_format_dollars():
    assert format_dollars(12.47) == "$12.47"
    assert format_dollars(3.20) == "$3.20"
    assert format_dollars(0.00) == "$0.00"
    assert format_dollars(100.5) == "$100"


def test_compute_bar_width():
    assert compute_bar_width(50, 100) == 50
    assert compute_bar_width(0, 100) == 0
    assert compute_bar_width(100, 100) == 100
    assert compute_bar_width(25, 200) == 50


def test_ticker_pages_even():
    projects = [{"name": f"p{i}"} for i in range(4)]
    pages = ticker_pages(projects, per_page=2)
    assert len(pages) == 2
    assert len(pages[0]) == 2
    assert len(pages[1]) == 2


def test_ticker_pages_odd():
    projects = [{"name": f"p{i}"} for i in range(7)]
    pages = ticker_pages(projects, per_page=2)
    assert len(pages) == 4
    assert len(pages[3]) == 1


def test_ticker_pages_empty():
    assert ticker_pages([], per_page=2) == []


def test_ticker_pages_three_per_page():
    projects = [{"name": f"p{i}"} for i in range(7)]
    pages = ticker_pages(projects, per_page=3)
    assert len(pages) == 3
    assert len(pages[2]) == 1


def test_scale_color():
    assert scale_color((255, 100, 50), 1.0) == (255, 100, 50)
    assert scale_color((255, 100, 50), 0.5) == (127, 50, 25)
    assert scale_color((255, 100, 50), 0.0) == (0, 0, 0)
