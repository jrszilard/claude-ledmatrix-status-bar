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


def test_format_value_quota_clamps_100_to_three_chars():
    # "100%" is 4 chars and overflows a 32px tile -> drop the % at 100.
    m = registry.Metric("WK", "quota", "subscription.week_all_pct", layout.COLOR_WEEK_ALL)
    state = {"subscription": {"week_all_pct": 100}}
    assert dashboard.format_value(m, state) == "100"
    # still shows % below 100
    state["subscription"]["week_all_pct"] = 99
    assert dashboard.format_value(m, state) == "99%"


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
    # value "45%" is 3 chars * TILE_CHAR_WIDTH(4) = 12px -> x = 32 - 12 = 20
    value_call = next(c for c in gfx.DrawText.call_args_list if c.args[5] == "45%")
    assert value_call.args[2] == 20


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


def test_format_countdown_caps_at_three_chars():
    # Countdown shares a 32px tile with the label, so it must stay <= 3 chars
    # (largest unit only): "3d", "2h", "45m" -- never "2h30m".
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for d in (timedelta(days=3, hours=5), timedelta(hours=2, minutes=30),
              timedelta(minutes=45), timedelta(hours=12)):
        cd = dashboard.format_countdown((now + d).isoformat())
        assert len(cd) <= 3, f"{cd!r} exceeds 3 chars"
    assert dashboard.format_countdown(
        (now + timedelta(hours=2, minutes=30)).isoformat()) == "2h"
    assert dashboard.format_countdown(
        (now + timedelta(days=3, hours=5)).isoformat()) == "3d"


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


def _claude():
    return next(p for p in registry.PROVIDERS if p.id == "anthropic")


def _opencode():
    return next(p for p in registry.PROVIDERS if p.id == "opencode")


def test_draw_accent_paints_left_column(gfx, canvas):
    dashboard.draw_accent(canvas, _claude())
    xs = {c.args[0] for c in canvas.SetPixel.call_args_list}
    assert xs == {0}                          # only column 0
    ys = {c.args[1] for c in canvas.SetPixel.call_args_list}
    assert ys == set(range(48))               # full 3*16 height


def test_draw_page_tiles_draws_fixed_labels(gfx, canvas):
    cy = dashboard.Cycler(total=3)
    dashboard.draw_page(canvas, gfx, {"main": MagicMock(), "small": MagicMock()},
                        _claude(), STATE, cy, now=0)
    drawn = texts(gfx)
    assert "SES" in drawn and "WK" in drawn   # both fixed tiles
    assert "SNT" in drawn                      # rotating tile (cycler.current == 0)


def test_draw_page_tiles_rotating_advances(gfx, canvas):
    cy = dashboard.Cycler(total=3)
    cy.current = 1                             # EXT is rotating[1]
    dashboard.draw_page(canvas, gfx, {"main": MagicMock(), "small": MagicMock()},
                        _claude(), STATE, cy, now=0)
    assert "EXT" in texts(gfx)
    assert "SNT" not in texts(gfx)


def test_draw_page_hero_draws_provider_label_and_spend(gfx, canvas):
    cy = dashboard.Cycler(total=1)
    dashboard.draw_page(canvas, gfx, {"main": MagicMock(), "small": MagicMock()},
                        _opencode(), STATE, cy, now=0)
    drawn = texts(gfx)
    assert "OPENCODE" in drawn
    assert "$18.40" in drawn


def test_dashboard_uses_only_enabled_providers():
    dash = dashboard.Dashboard()
    assert [p.id for p in dash.providers] == ["anthropic"]


def test_dashboard_single_provider_does_not_rotate():
    dash = dashboard.Dashboard(page_dwell_seconds=4)
    dash.update(now=100)
    dash.update(now=200)
    assert dash.provider_cycler.current == 0   # only one provider -> no advance


def test_dashboard_draw_renders_claude_page(gfx, canvas):
    dash = dashboard.Dashboard()
    dash.draw(canvas, gfx, {"main": MagicMock(), "small": MagicMock()}, STATE, now=0)
    drawn = texts(gfx)
    assert "SES" in drawn and "WK" in drawn


def test_dashboard_draw_noop_when_no_providers(gfx, canvas, monkeypatch):
    monkeypatch.setattr(registry, "enabled_providers", lambda: [])
    dash = dashboard.Dashboard()
    dash.draw(canvas, gfx, {"main": MagicMock(), "small": MagicMock()}, STATE, now=0)
    assert not gfx.DrawText.called


def test_hero_sub_line_is_truncated(gfx, canvas):
    state = {"opencode": {"spent_period": 18.40,
                          "autoreload": "auto-reload @ $100.00 every hour"}}
    cy = dashboard.Cycler(total=1)
    dashboard.draw_page(canvas, gfx, {"main": MagicMock(), "small": MagicMock()},
                        _opencode(), state, cy, now=0)
    # the sub-line is the only drawn text that is neither the label nor the dollar value
    drawn = [t for t in texts(gfx) if t not in ("OPENCODE", "$18.40")]
    assert drawn, "expected a sub-line to be drawn"
    assert all(len(t) <= 8 for t in drawn)
