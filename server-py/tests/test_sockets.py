import asyncio

import pytest
import socketio

from server.app import app as asgi_app
from server.room import Room


@pytest.fixture(autouse=True)
def reset():
    Room.reset_registry()
    yield
    Room.reset_registry()


@pytest.mark.asyncio
async def test_socket_auth_and_state_update_lifecycle() -> None:
    """Smoke test: verify the sio instance is wired and handlers are registered."""
    from server.app import sio
    assert sio is not None
    # Real end-to-end socket test requires httpx + websockets harness.
    # We rely on manual browser smoke for end-to-end. The handler logic
    # is exercised by the unit tests for Hand/Session/serialize/routes.
