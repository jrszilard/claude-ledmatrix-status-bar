import time
import pytest
from unittest.mock import MagicMock

from src.renderer import (
    draw_session_panel,
    draw_weekly_panel,
    draw_api_panel,
    draw_divider,
    draw_ticker_page,
    Ticker,
)
from src import layout


@pytest.fixture
def mock_canvas():
    canvas = MagicMock()
    canvas.width = layout.TOTAL_WIDTH
    canvas.height = layout.TOTAL_HEIGHT
    return canvas


@pytest.fixture
def mock_graphics():
    gfx = MagicMock()
    gfx.Color = lambda r, g, b: (r, g, b)
    gfx.DrawText = MagicMock(return_value=0)
    gfx.DrawLine = MagicMock()
    return gfx


@pytest.fixture
def mock_fonts():
    return {"large": MagicMock(), "small": MagicMock()}


# --- Top Dashboard Tests ---


def test_draw_session_panel_draws_label(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_session_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    calls = mock_graphics.DrawText.call_args_list
    labels = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "SESSION" in labels


def test_draw_session_panel_draws_percentage(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_session_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "10%" in texts


def test_draw_session_panel_draws_bar(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_session_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    # Bar is drawn via SetPixel calls for filled portion and background
    assert mock_canvas.SetPixel.called


def test_draw_session_panel_draws_reset_time(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_session_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert any("7pm" in t for t in texts)


def test_draw_weekly_panel_draws_three_bars(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_weekly_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["subscription"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "WEEKLY" in texts
    assert "ALL" in texts
    assert "SNT" in texts
    assert "EXT" in texts


def test_draw_api_panel_draws_spend(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_api_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["api"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "$12.47" in texts


def test_draw_api_panel_draws_tokens(mock_canvas, mock_graphics, mock_fonts, sample_state):
    draw_api_panel(mock_canvas, mock_graphics, mock_fonts, sample_state["api"])
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "1.2M tk" in texts


def test_draw_divider(mock_canvas, mock_graphics):
    draw_divider(mock_canvas, mock_graphics)
    mock_graphics.DrawLine.assert_called_once()


# --- Ticker Tests ---


def test_ticker_init():
    ticker = Ticker(cycle_seconds=4, fade_frames=15, projects_per_page=2)
    assert ticker.current_page == 0
    assert ticker.fade_progress is None


def test_ticker_page_cycling():
    ticker = Ticker(cycle_seconds=0.1, fade_frames=2, projects_per_page=2)
    projects = [
        {"name": "p1", "spend": 1.0, "tokens": 100},
        {"name": "p2", "spend": 2.0, "tokens": 200},
        {"name": "p3", "spend": 3.0, "tokens": 300},
        {"name": "p4", "spend": 4.0, "tokens": 400},
    ]
    pages = layout.ticker_pages(projects, per_page=2)

    # Start on page 0
    assert ticker.current_page == 0

    # After enough time, should advance
    ticker.last_cycle_time = time.time() - 1  # force cycle
    ticker.update(len(pages))
    # Should be fading or on next page
    assert ticker.fade_progress is not None or ticker.current_page == 1


def test_ticker_fade_brightness():
    ticker = Ticker(cycle_seconds=4, fade_frames=10, projects_per_page=2)
    # During fade-out (progress 0 to 0.5), brightness goes from 1.0 to 0.0
    assert ticker.get_brightness(0.0) == 1.0
    assert ticker.get_brightness(0.5) == 0.0
    # During fade-in (progress 0.5 to 1.0), brightness goes from 0.0 to 1.0
    assert ticker.get_brightness(1.0) == 1.0


def test_ticker_wraps_around():
    ticker = Ticker(cycle_seconds=0.1, fade_frames=2, projects_per_page=2)
    ticker.current_page = 2
    ticker.last_cycle_time = time.time() - 1
    ticker.update(total_pages=3)
    # After fading, should wrap to 0
    ticker.fade_progress = None
    ticker.current_page = 3
    ticker.update(total_pages=3)
    assert ticker.current_page == 0


def test_draw_ticker_page(mock_canvas, mock_graphics, mock_fonts, sample_state):
    projects_page = sample_state["api"]["projects"][:2]
    draw_ticker_page(mock_canvas, mock_graphics, mock_fonts, projects_page, brightness=1.0)
    calls = mock_graphics.DrawText.call_args_list
    texts = [c.args[5] if len(c.args) > 5 else c[0][5] for c in calls]
    assert "tastytrade-bot" in texts
    assert "diy-helper" in texts


def test_draw_ticker_page_with_dim_brightness(mock_canvas, mock_graphics, mock_fonts, sample_state):
    projects_page = sample_state["api"]["projects"][:2]
    draw_ticker_page(mock_canvas, mock_graphics, mock_fonts, projects_page, brightness=0.5)
    # Colors should be scaled down — check that DrawText received dimmed color tuples
    draw_calls = mock_graphics.DrawText.call_args_list
    colors_used = [c.args[4] if len(c.args) > 4 else c[0][4] for c in draw_calls]
    # At brightness 0.5, the API purple (201, 160, 255) should become (100, 80, 127)
    expected_dimmed = layout.scale_color(layout.COLOR_API, 0.5)
    assert expected_dimmed in colors_used
