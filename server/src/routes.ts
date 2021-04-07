import { Application } from 'express';
import Player from '@game/Player';
import Room from '@game/Room';

export default function routes(
  app: Application, 
  players: Map<string, Player>, 
  rooms: Map<string, Room>): void {

  app.post('/create_room', (req, res) => {
    console.log(req.sessionID);
    // const { id, username } = req.body;
    // const player = new Player(socket.id, username);
    // players.set(socket.id, player);
    // rooms.set(socket.id, new Room(player));
    res.status(200).end();
  });
  
}