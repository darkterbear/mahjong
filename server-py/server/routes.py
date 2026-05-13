"""HTTP routes: room creation, joining, session start."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.room import Room, Player
from server.protocol import ServerEvent


router = APIRouter()


async def _emit_lobby_update(room: Room) -> None:
    # Deferred import to avoid circular dependency (app.py imports routes.py).
    from server.app import sio
    payload = {
        "players": [p.username for p in room.players],
        "leader": room.leader.username if room.leader else None,
    }
    await sio.emit(ServerEvent.LOBBY_UPDATE.value, payload, room=room.code)


class CreateRoomBody(BaseModel):
    player_id: str
    username: str


class JoinRoomBody(BaseModel):
    player_id: str
    username: str
    code: str


class StartSessionBody(BaseModel):
    player_id: str
    code: str


@router.post("/create_room")
async def create_room(body: CreateRoomBody) -> dict:
    room = Room.create()
    room.add_player(Player(player_id=body.player_id, username=body.username))
    await _emit_lobby_update(room)
    return {"code": room.code}


@router.post("/join_room")
async def join_room(body: JoinRoomBody) -> dict:
    room = Room.get(body.code)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    try:
        room.add_player(Player(player_id=body.player_id, username=body.username))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _emit_lobby_update(room)
    return {
        "players": [p.username for p in room.players],
        "leader": room.leader.username if room.leader else None,
    }


@router.post("/start_session")
async def start_session(body: StartSessionBody) -> dict:
    room = Room.get(body.code)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    if room.leader is None or room.leader.player_id != body.player_id:
        raise HTTPException(status_code=403, detail="only leader can start")
    try:
        room.start_session()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Create the first Hand (PRE_DICE) so clients have state to render once
    # they auth on the GamePage. Otherwise they sit at "Connecting…".
    room.session.start_new_hand()
    # Tell every socket in the room to navigate to the game page.
    from server.app import sio
    await sio.emit(ServerEvent.START_GAME.value, {"code": body.code}, room=body.code)
    return {"started": True}
