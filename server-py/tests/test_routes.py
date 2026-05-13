import pytest
from fastapi.testclient import TestClient

from server.app import fastapi_app
from server.room import Room


@pytest.fixture(autouse=True)
def reset_rooms():
    Room.reset_registry()
    yield
    Room.reset_registry()


def test_create_room() -> None:
    client = TestClient(fastapi_app)
    r = client.post("/create_room", json={"player_id": "p1", "username": "alice"})
    assert r.status_code == 200
    body = r.json()
    assert "code" in body
    assert len(body["code"]) == 4


def test_join_room_not_found() -> None:
    client = TestClient(fastapi_app)
    r = client.post("/join_room", json={"player_id": "p2", "username": "bob", "code": "ZZZZ"})
    assert r.status_code == 404


def test_join_room_full() -> None:
    client = TestClient(fastapi_app)
    r = client.post("/create_room", json={"player_id": "p1", "username": "a"})
    code = r.json()["code"]
    for i in range(2, 5):
        r2 = client.post("/join_room", json={"player_id": f"p{i}", "username": str(i), "code": code})
        assert r2.status_code == 200
    r3 = client.post("/join_room", json={"player_id": "p99", "username": "x", "code": code})
    assert r3.status_code == 400


def test_start_session_requires_4() -> None:
    client = TestClient(fastapi_app)
    r = client.post("/create_room", json={"player_id": "p1", "username": "a"})
    code = r.json()["code"]
    r_start = client.post("/start_session", json={"player_id": "p1", "code": code})
    assert r_start.status_code == 400
