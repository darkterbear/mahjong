import pytest

from server.room import Room, Player


def test_create_room_unique_code() -> None:
    Room.reset_registry()
    r1 = Room.create()
    r2 = Room.create()
    assert r1.code != r2.code
    assert len(r1.code) == 4


def test_join_room_until_full() -> None:
    Room.reset_registry()
    r = Room.create()
    p1 = Player(player_id="a", username="alice")
    p2 = Player(player_id="b", username="bob")
    p3 = Player(player_id="c", username="charlie")
    p4 = Player(player_id="d", username="dan")
    r.add_player(p1)
    r.add_player(p2)
    r.add_player(p3)
    r.add_player(p4)
    assert len(r.players) == 4

    p5 = Player(player_id="e", username="eve")
    with pytest.raises(ValueError):
        r.add_player(p5)


def test_remove_player() -> None:
    Room.reset_registry()
    r = Room.create()
    p1 = Player(player_id="a", username="alice")
    p2 = Player(player_id="b", username="bob")
    r.add_player(p1)
    r.add_player(p2)
    assert r.leader is p1
    r.remove_player("a")
    assert len(r.players) == 1
    assert r.leader is p2


def test_remove_last_destroys_room() -> None:
    Room.reset_registry()
    r = Room.create()
    p1 = Player(player_id="a", username="alice")
    r.add_player(p1)
    r.remove_player("a")
    assert Room.get(r.code) is None


def test_start_session_requires_4_players() -> None:
    Room.reset_registry()
    r = Room.create()
    p1 = Player(player_id="a", username="alice")
    r.add_player(p1)
    with pytest.raises(RuntimeError):
        r.start_session()


def test_start_session_creates_session_with_4_players() -> None:
    Room.reset_registry()
    r = Room.create()
    for x in "abcd":
        r.add_player(Player(player_id=x, username=x))
    r.start_session(seed=0)
    assert r.session is not None
    assert sorted(r.session.seats) == ["a", "b", "c", "d"]


def test_add_player_rejects_duplicate_player_id() -> None:
    Room.reset_registry()
    r = Room.create()
    p1 = Player(player_id="dup", username="alice")
    p2 = Player(player_id="dup", username="bob")  # same player_id
    r.add_player(p1)
    with pytest.raises(ValueError):
        r.add_player(p2)


def test_room_bot_seat_detection() -> None:
    Room.reset_registry()
    r = Room.create()
    r.add_player(Player(player_id="h1", username="alice"))
    r.add_player(Player(player_id="b1", username="Tilesworth", is_bot=True))
    r.add_player(Player(player_id="h2", username="bob"))
    r.add_player(Player(player_id="b2", username="Honoraburu", is_bot=True))
    r.start_session(seed=0)
    bots = set(r.bot_seats())
    humans = set(r.human_seats())
    assert len(bots) == 2 and len(humans) == 2
    assert bots.isdisjoint(humans)
    assert bots | humans == {0, 1, 2, 3}
    for seat in bots:
        assert r.is_bot_seat(seat) is True
    for seat in humans:
        assert r.is_bot_seat(seat) is False
