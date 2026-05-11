from server.wall_view import flat_to_position, position_to_flat
from server.protocol import WallPosition


def test_flat_to_position_first_tile() -> None:
    assert flat_to_position(0) == WallPosition(seat=0, stack=0, layer=0)


def test_flat_to_position_seat_boundary() -> None:
    assert flat_to_position(36) == WallPosition(seat=1, stack=0, layer=0)
    assert flat_to_position(35) == WallPosition(seat=0, stack=17, layer=1)


def test_flat_to_position_last_tile() -> None:
    assert flat_to_position(143) == WallPosition(seat=3, stack=17, layer=1)


def test_round_trip() -> None:
    for i in range(144):
        assert position_to_flat(flat_to_position(i)) == i


def test_invalid_flat_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        flat_to_position(-1)
    with pytest.raises(ValueError):
        flat_to_position(144)
