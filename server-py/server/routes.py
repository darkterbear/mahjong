"""HTTP routes: room creation, joining, session start."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.room import Room, Player
from server.protocol import ServerEvent


router = APIRouter()

BOT_NAMES = ["Tilesworth", "Honoraburu", "Whisperjack", "Pip Cheng"]


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


@router.post("/start_with_cpus")
async def start_with_cpus(body: StartSessionBody) -> dict:
    room = Room.get(body.code)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    if room.leader is None or room.leader.player_id != body.player_id:
        raise HTTPException(status_code=403, detail="only leader can start")
    if room.session is not None:
        raise HTTPException(status_code=400, detail="session already in progress")

    # Pick bot names that don't conflict with existing human usernames.
    existing_usernames = {p.username for p in room.players}
    available_bot_names = [n for n in BOT_NAMES if n not in existing_usernames]

    bot_index = 0
    while len(room.players) < 4:
        if bot_index >= len(available_bot_names):
            raise HTTPException(status_code=500, detail="ran out of bot names")
        bot_name = available_bot_names[bot_index]
        bot_index += 1
        bot_pid = f"bot_{room.code}_{len(room.players)}"
        bot_player = Player(player_id=bot_pid, username=bot_name, is_bot=True)
        room.players.append(bot_player)  # bypass add_player to skip the 4-player limit check mid-fill

    # Notify lobby clients of the updated roster before starting.
    await _emit_lobby_update(room)

    room.start_session()
    room.session.start_new_hand()

    from server.app import sio
    await sio.emit(ServerEvent.START_GAME.value, {"code": body.code}, room=body.code)

    bot_seat_list = [i for i, pid in enumerate(room.session.seats)
                     if any(p.player_id == pid and p.is_bot for p in room.players)]
    bot_names_by_seat = {
        str(i): next(p.username for p in room.players if p.player_id == room.session.seats[i])
        for i in bot_seat_list
    }
    return {"started": True, "bot_seats": bot_seat_list, "bot_names_by_seat": bot_names_by_seat}
