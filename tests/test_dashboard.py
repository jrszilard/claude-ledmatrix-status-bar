import pytest
from unittest.mock import MagicMock

from src import layout, registry, dashboard


@pytest.fixture(autouse=True)
def restore_geometry():
    yield
    layout.configure(rows=16, cols=32, parallel=3)


@pytest.fixture
def gfx():
    g = MagicMock()
    g.Color = lambda r, g_, b: (r, g_, b)
    g.DrawText = MagicMock(return_value=0)
    return g


@pytest.fixture
def canvas():
    return MagicMock()


def texts(gfx):
    return [c.args[5] for c in gfx.DrawText.call_args_list]


STATE = {
    "subscription": {"session_pct": 45, "week_all_pct": 62, "week_sonnet_pct": 38,
                     "extra_spent": 12.0, "extra_limit": 50.0},
    "api": {"total_spend": 4.20, "total_tokens": 1_200_000},
    "opencode": {"spent_period": 18.40, "autoreload": "auto @ $5"},
}

SES = registry.Metric("SES", "quota", "subscription.session_pct", layout.COLOR_SESSION)
EXT = registry.Metric("EXT", "capped", "subscription.extra_spent", layout.COLOR_EXTRA,
                      limit_key="subscription.extra_limit")
API = registry.Metric("API", "spend", "api.total_spend", layout.COLOR_API)


def test_format_value_quota():
    assert dashboard.format_value(SES, STATE) == "45%"


def test_format_value_capped_shows_spent_dollars():
    assert dashboard.format_value(EXT, STATE) == "$12"


def test_format_value_spend():
    assert dashboard.format_value(API, STATE) == "$4.20"


def test_metric_pct_quota_is_the_percentage():
    assert dashboard.metric_pct(SES, STATE) == 45.0


def test_metric_pct_capped_is_spent_over_limit():
    assert dashboard.metric_pct(EXT, STATE) == pytest.approx(24.0)


def test_metric_pct_spend_has_no_bar():
    assert dashboard.metric_pct(API, STATE) is None


def test_draw_tile_draws_label_and_value(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 0, SES, STATE, now=0)
    assert "SES" in texts(gfx)
    assert "45%" in texts(gfx)


def test_draw_tile_value_is_right_aligned(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 0, SES, STATE, now=0)
    # value "45%" is 3 chars * CHAR_WIDTH(5) = 15px -> x = 32 - 15 = 17
    value_call = next(c for c in gfx.DrawText.call_args_list if c.args[5] == "45%")
    assert value_call.args[2] == 17


def test_draw_tile_quota_draws_bar(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 0, SES, STATE, now=0)
    assert canvas.SetPixel.called


def test_draw_tile_spend_draws_no_bar(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 0, API, STATE, now=0)
    assert not canvas.SetPixel.called


def test_draw_tile_applies_vertical_offset(gfx, canvas):
    dashboard.draw_tile(canvas, gfx, MagicMock(), 16, SES, STATE, now=0)
    # label baseline = y_offset + TILE_TEXT_Y = 16 + 8 = 24
    label_call = next(c for c in gfx.DrawText.call_args_list if c.args[5] == "SES")
    assert label_call.args[3] == 24


def test_cycler_single_item_never_advances():
    cy = dashboard.Cycler(total=1, cycle_seconds=1, fade_frames=2)
    cy.update(now=1000)
    cy.update(now=2000)
    assert cy.current == 0
    assert cy.brightness() == 1.0


def test_cycler_enters_fade_after_cycle_seconds():
    cy = dashboard.Cycler(total=3, cycle_seconds=4, fade_frames=2)
    cy.last_cycle_time = 100.0
    cy.update(now=105.0)            # 5s elapsed > 4s -> start fade
    assert cy.fade_progress is not None


def test_cycler_advances_through_fade():
    cy = dashboard.Cycler(total=3, cycle_seconds=4, fade_frames=2)
    cy.last_cycle_time = 100.0
    cy.update(now=105.0)           # start fade
    for _ in range(10):            # pump frames to finish the fade
        cy.update(now=105.0)
    assert cy.current == 1


def test_cycler_brightness_dips_at_midpoint():
    cy = dashboard.Cycler(total=2, cycle_seconds=1, fade_frames=10)
    cy.fade_progress = 0.5
    assert cy.brightness() == pytest.approx(0.0)
    cy.fade_progress = 0.0
    assert cy.brightness() == pytest.approx(1.0)


def test_format_countdown_hours():
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=30)).isoformat()
    assert dashboard.format_countdown(future).endswith("m")


def test_tile_value_alternates_to_countdown():
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    state = {"subscription": {"session_pct": 45, "session_reset_utc": future}}
    m = registry.Metric("SES", "quota", "subscription.session_pct", layout.COLOR_SESSION,
                        reset_key="subscription.session_reset_utc")
    # phase 0..5 shows the percentage, 5..7 shows the countdown
    assert dashboard.tile_value(m, state, now=0, show_countdown=True) == "45%"
    assert dashboard.tile_value(m, state, now=6, show_countdown=True) != "45%"


def test_tile_value_no_countdown_when_disabled():
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    state = {"subscription": {"session_pct": 45, "session_reset_utc": future}}
    m = registry.Metric("SES", "quota", "subscription.session_pct", layout.COLOR_SESSION,
                        reset_key="subscription.session_reset_utc")
    assert dashboard.tile_value(m, state, now=6, show_countdown=False) == "45%"
