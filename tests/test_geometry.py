import pytest

from src import layout


@pytest.fixture(autouse=True)
def restore_geometry():
    """Reset tile geometry to hardware defaults after each test."""
    yield
    layout.configure(rows=16, cols=32, parallel=3)


def test_default_tile_geometry():
    assert layout.TILE_WIDTH == 32
    assert layout.TILE_HEIGHT == 16
    assert layout.NUM_TILES == 3
    assert layout.TILE_Y_OFFSETS == [0, 16, 32]


def test_within_tile_element_positions():
    # text baseline and bar sit inside a 16px-tall tile
    assert 0 < layout.TILE_TEXT_Y < layout.TILE_HEIGHT
    assert layout.TILE_BAR_Y + layout.TILE_BAR_H <= layout.TILE_HEIGHT


def test_configure_derives_offsets_for_three_panels():
    layout.configure(rows=16, cols=32, parallel=3)
    assert layout.TILE_WIDTH == 32
    assert layout.TILE_HEIGHT == 16
    assert layout.NUM_TILES == 3
    assert layout.TILE_Y_OFFSETS == [0, 16, 32]


def test_configure_two_panels():
    layout.configure(rows=16, cols=32, parallel=2)
    assert layout.NUM_TILES == 2
    assert layout.TILE_Y_OFFSETS == [0, 16]


def test_configure_updates_total_dimensions():
    layout.configure(rows=16, cols=32, parallel=2)
    assert layout.TOTAL_WIDTH == 32
    assert layout.TOTAL_HEIGHT == 32   # 16 * 2
    layout.configure(rows=16, cols=32, parallel=3)
    assert layout.TOTAL_HEIGHT == 48   # 16 * 3
