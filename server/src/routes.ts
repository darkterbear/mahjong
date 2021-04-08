import { Application } from 'express';
import Player from '@game/Player';
import Room from '@game/Room';

export default function routes(app: Application): void {
  app.post('/create_room', (req, res) => {
    const { username } = req.body;
    const id = req.sessionID;

    const player = new Player(id, username);
    const room = new Room();
    player.joinRoom(room);

    res.json({ code: room.code });
  });

  app.post('/join_room', (req, res) => {
    const { username, code } = req.body;
    const id = req.sessionID;

    const room = Room.getRoom(code);
    if (!room) {
      return res.status(404).end();
    }

    if (room.players.length >= 4) {
      return res.status(400).end();
    }

    if (room.inGame()) {
      return res.status(400).end();
    }

    const player = new Player(id, username);
    player.joinRoom(room);

    res.json(room.players.map(p => p.username));
  });
  
}